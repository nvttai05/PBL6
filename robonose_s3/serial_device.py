"""One transport owner. This module itself never imports serial or opens a COM port."""
from collections import deque
from dataclasses import dataclass, field
import queue
import threading
import time

from .usb_protocol import (PROTOCOL, Framer, ProtocolError,
                           validate_ack, validate_context, validate_hello, validate_sample)
from .schema import SCHEMA


@dataclass
class Pending:
    request_id: int
    verb: str
    argument: str
    expected_phase: str | None
    packet: bytes=b''
    sent_at: float=0
    attempts: int=0
    result: dict | None=None
    error: str | None=None
    done: threading.Event=field(default_factory=threading.Event)


def open_serial_transport(options):
    # Deferred until the explicitly selected hardware backend starts its owner thread.
    import serial
    transport=serial.Serial(port=None,baudrate=options.baud,timeout=.02,write_timeout=.2)
    transport.dtr=False
    transport.rts=False
    transport.port=options.port
    transport.open()
    return transport


class SerialDevice:
    def __init__(self,options,session_id,clock,wire_sink,health,transport_factory=None):
        self.options,self.session_id,self.clock=options,session_id,clock
        self.wire_sink,self.health=wire_sink,health
        self.factory=transport_factory or (lambda:open_serial_transport(options))
        self.incoming=queue.Queue(256)
        self.outgoing=queue.Queue(32)
        self.framer=Framer()
        self.ready=threading.Event(); self.stopping=threading.Event(); self.off_requested=threading.Event()
        self.closed=threading.Event()
        self.hello=None; self.boot_id=None; self.error=None; self.off_acknowledged=False
        self.last_sample_at=None; self.last_seq=0; self.gaps=0; self.dropped=0
        self.begun_epoch=None; self.off_barrier=0
        self.tx_resync_required=False; self.emergency_attempted=False
        self.off_started=None; self.off_next_send=0; self.off_attempts=0
        self.pending=None; self.off_pending=None; self.next_id=1; self.id_lock=threading.Lock()
        self.recent=deque(maxlen=128)
        self.thread=threading.Thread(target=self._run,name='serial-owner',daemon=True)

    def start(self):
        self.thread.start()

    def request(self,verb,argument='',expected_phase=None):
        with self.id_lock:
            request=Pending(self.next_id,verb,argument,expected_phase)
            self.next_id+=1
        if self.error or self.stopping.is_set():
            raise ProtocolError(self.error or 'Serial device closing')
        try:
            self.outgoing.put_nowait(request)
        except queue.Full:
            self.fault('Command transport queue full')
            raise ProtocolError(self.error)
        return request

    def priority_off(self,fault=False):
        self.off_is_fault=fault or bool(self.error)
        self.off_requested.set()

    def fault(self,reason):
        self.error=self.error or str(reason)
        self.priority_off(True)

    def close(self):
        self.priority_off(bool(self.error))
        self.stopping.set()
        self.thread.join(self.options.off_timeout_s+1)
        return self.off_acknowledged

    def _publish(self,packet):
        try:
            self.incoming.put_nowait(packet)
        except queue.Full:
            self.fault('Telemetry queue full')

    def _parser_event(self,reason,**details):
        self._publish({'type':'parser_event','reason':reason,**details})

    def _write(self,transport,data,priority=False):
        # Send OFF even when persistence has failed/full queues cannot record it.
        try:
            sent=transport.write(data)
        except Exception as error:
            self.tx_resync_required=True
            self._write_failure(data,None,str(error))
            raise
        if sent!=len(data):
            self.tx_resync_required=True
            reason=f'Short serial write on {self.options.port}: {sent}/{len(data)} bytes'
            self._write_failure(data,sent,reason)
            raise ProtocolError(reason)
        try:
            self.wire_sink({'direction':'tx','host_mono_s':self.clock.now(),'bytes_hex':data.hex()})
        except Exception:
            if not priority:
                raise

    def _write_failure(self,data,sent,reason):
        # Keep attempted bytes distinct from the prefix accepted by the driver.
        # A write exception can leave that accepted count unknown. Logging must
        # remain best effort so recorder failure cannot prevent emergency OFF.
        known=type(sent) is int and 0<=sent<=len(data)
        try:
            self.wire_sink({'direction':'tx','host_mono_s':self.clock.now(),
                'bytes_hex':data[:sent].hex() if known else '',
                'attempted_bytes_hex':data.hex(),'accepted_bytes':sent if known else None,
                'requested_bytes':len(data),'write_outcome':'short_write' if known else 'exception_or_unknown',
                'error':reason})
        except Exception:
            pass

    def _send_request(self,transport,request):
        if not self.boot_id:
            raise ProtocolError('No dataset handshake')
        request.packet=(f'@{request.request_id} {self.boot_id} {self.session_id} {request.verb}'
                        +(f' {request.argument}' if request.argument else '')+'\n').encode('ascii')
        if len(request.packet)>=192:
            raise ProtocolError('Wire command too long')
        self._write(transport,request.packet)
        request.sent_at=self.clock.now(); request.attempts+=1

    def _accept(self,packet):
        kind=packet.get('type')
        if kind=='device_fault' and packet.get('source')=='usb_plain_text':
            self.fault(f"MCU {packet['reason']}: {packet['detail']}")
            self._publish(packet)
            return
        if kind=='parser_event':
            self._publish(packet); return
        if packet.get('protocol')!=PROTOCOL or packet.get('schema')!=SCHEMA:
            raise ProtocolError('Legacy/unknown firmware protocol/schema; refusing BEGIN')
        if self.boot_id and packet.get('boot_id')!=self.boot_id:
            raise ProtocolError('Device reboot/boot_id changed; no automatic resume')
        if kind=='hello':
            ready=validate_hello(packet,initial=not self.ready.is_set())
            self.boot_id=packet['boot_id']; self.hello=packet
            if ready:
                self.ready.set()
            self._publish(packet); return
        if not self.boot_id:
            self._parser_event('frame_before_handshake'); return
        request=None
        if kind=='ack':
            candidate=self.off_pending if self.off_pending and packet.get('request_id')==self.off_pending.request_id else self.pending
            if candidate and packet.get('request_id')==candidate.request_id:
                request=candidate
        require_sid=packet.get('session_id')
        if not isinstance(require_sid,str):
            raise ProtocolError('Missing/invalid session_id')
        if require_sid!=self.session_id:
            epoch=packet.get('context_epoch')
            idle_context=(packet.get('phase') in ('OFF','CLOSED') and type(epoch) is int
                          and (self.begun_epoch is None or epoch<self.begun_epoch))
            idle_frame=idle_context and (kind in ('sample','event') or (kind=='ack' and request is None))
            correlated_off=kind=='ack' and self.off_pending is not None and request is self.off_pending
            terminal_off_event=(kind=='event' and self.off_pending is not None
                                and packet.get('phase') in ('CLOSED','ERROR'))
            if not (idle_frame or correlated_off or terminal_off_event):
                raise ProtocolError('Foreign session telemetry/ACK')
        if kind=='sample':
            validate_sample(packet)
            seq=packet['seq']
            if seq<=self.last_seq:
                self.dropped+=1; self._parser_event('duplicate_or_reordered_sample',seq=seq); return
            if self.last_seq and seq>self.last_seq+1:
                self.gaps+=seq-self.last_seq-1
                self._parser_event('sequence_gap',previous=self.last_seq,seq=seq)
            self.last_seq=seq; self.last_sample_at=self.clock.now()
        elif kind in ('ack','event'):
            validate_context(packet)
            if kind=='ack':
                if request is None:
                    self._parser_event('old_or_unsolicited_ack',request_id=packet.get('request_id')); return
                validate_ack(packet)
                if request is self.off_pending:
                    self.off_acknowledged=(packet['accepted'] and packet['pump_pwm_pct']==0 and packet['valve_energized'] is False)
                    self.off_barrier=packet.get('barrier_seq',0)
                    if not self.off_acknowledged:
                        raise ProtocolError('OFF ACK did not confirm commanded OFF')
                elif packet['accepted'] and request.expected_phase and packet['phase']!=request.expected_phase:
                    raise ProtocolError(f'ACK state mismatch for {request.verb}: {packet["phase"]}')
                if packet['accepted'] and request.verb=='START' and packet.get('trial_id')!=request.argument:
                    raise ProtocolError('ACK trial UUID mismatch')
                if packet['accepted'] and request.verb=='BEGIN':
                    self.begun_epoch=packet['context_epoch']
                request.result=packet; request.done.set()
                if request is self.pending:
                    self.pending=None
        else:
            raise ProtocolError(f'Unknown frame type: {kind}')
        self._publish(packet)

    def _off_step(self,transport):
        """Bounded OFF-only traffic on the existing handle; never reopen/resume."""
        now=time.monotonic()
        if self.off_pending is None:
            with self.id_lock:
                self.off_pending=Pending(self.next_id,'FAULT' if getattr(self,'off_is_fault',False) else 'OFF','',None)
                self.next_id+=1
            self.off_started=now
            if self.pending:
                self.pending.error=self.error or 'Cancelled by priority OFF'
                self.pending.done.set(); self.pending=None
        if ((self.off_acknowledged and self.last_seq>=self.off_barrier)
            or now-self.off_started>=self.options.off_timeout_s):
            return True
        if self.tx_resync_required and not self.emergency_attempted:
            self.emergency_attempted=True
            try:
                # Invalidate the residual line before LF. Plain LF could finish
                # a BEGIN whose only missing byte was its newline, turning ON
                # after the host had already faulted.
                self._write(transport,b'!\nALL_OFF\n',priority=True)
            except Exception as error:
                self.fault(error)
        if (not self.off_acknowledged and self.off_attempts<3
            and now>=self.off_next_send and time.monotonic()-self.off_started<self.options.off_timeout_s):
            request=self.off_pending
            if self.error:
                request.verb='FAULT'
            prefix='!\n' if self.tx_resync_required else ''
            request.packet=(f'{prefix}@{request.request_id} {self.boot_id} {self.session_id} {request.verb}\n'.encode('ascii')
                            if self.boot_id else b'!\nALL_OFF\n')
            self.off_attempts+=1; self.off_next_send=now+.1
            try:
                self._write(transport,request.packet,priority=True)
            except Exception as error:
                self.fault(error)
        return False

    def _run(self):
        transport=None; started=self.clock.now(); last_hello=-100.0; last_ping=started
        try:
            transport=self.factory()
            while True:
                try:
                    now=self.clock.now()
                    if self.off_requested.is_set():
                        if self._off_step(transport):
                            break
                    elif not self.error:
                        if not self.ready.is_set():
                            if now-started>=self.options.handshake_timeout_s:
                                raise ProtocolError('Handshake timeout; output not enabled')
                            if now-last_hello>=.5:
                                self._write(transport,b'HELLO\n'); last_hello=now
                        else:
                            if self.pending is None:
                                try:
                                    self.pending=self.outgoing.get_nowait()
                                except queue.Empty:
                                    pass
                                if self.pending:
                                    self._send_request(transport,self.pending)
                            elif now-self.pending.sent_at>=self.options.ack_timeout_s:
                                if self.pending.attempts<=self.options.retries:
                                    self._write(transport,self.pending.packet)
                                    self.pending.attempts+=1; self.pending.sent_at=now
                                else:
                                    raise ProtocolError(f'ACK timeout for {self.pending.verb}')
                            if self.last_sample_at is not None and now-self.last_sample_at>self.options.receive_timeout_s:
                                raise ProtocolError('Sensor/receive stream stale')
                            if not self.pending and now-last_ping>=2 and self.health():
                                self.request('PING'); last_ping=now
                    data=transport.read(4096)
                    if data:
                        try:
                            self.wire_sink({'direction':'rx','host_mono_s':now,'bytes_hex':data.hex()})
                        except Exception as error:
                            self.fault(error)
                        for packet in self.framer.feed(data):
                            try:
                                self._accept(packet)
                            except Exception as error:
                                self.fault(error)
                    if self.stopping.is_set() and not self.off_requested.is_set():
                        self.priority_off(bool(self.error))
                except Exception as error:
                    # Keep the same port open only for bounded emergency OFF,
                    # ACK and in-flight samples. No ordinary requests after fault.
                    self.fault(error)
                    time.sleep(.002)
        except Exception as error:
            self.error=self.error or str(error)
        finally:
            if self.pending:
                self.pending.error=self.error or 'Serial device closed'; self.pending.done.set()
            try:
                if transport:
                    transport.close()
            finally:
                self.closed.set()
