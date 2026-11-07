import json
import time
import pytest

from robonose_s3.clock import Clock
from robonose_s3.emulator import EmulatedTransport
from test_serial_session import make_session, ready


class InterruptedWriteTransport(EmulatedTransport):
    """Model a real receiver retaining a command prefix until the next LF."""
    def __init__(self,clock,accepted=0,permanent=False):
        super().__init__(clock)
        self.accepted=accepted; self.armed=False; self.permanent=permanent
        self.command_buffer=bytearray(); self.failed=False; self.chunks=[]

    def write(self,data):
        self.chunks.append(data)
        if self.armed and (self.permanent or (not self.failed and b' PING\n' in data)):
            self.failed=True
            if self.accepted is None:
                raise OSError('injected USB write cancellation')
            self.command_buffer.extend(data[:self.accepted])
            return self.accepted
        self.command_buffer.extend(data)
        while b'\n' in self.command_buffer:
            line,_,rest=self.command_buffer.partition(b'\n')
            self.command_buffer=bytearray(rest)
            if line:
                super().write(bytes(line)+b'\n')
        return len(data)


@pytest.mark.parametrize('accepted',[0,12,None])
def test_short_write_enters_bounded_off_and_reads_ack_without_reopening(tmp_path,accepted):
    clock=Clock(); transport=InterruptedWriteTransport(clock,accepted)
    session,_=make_session(tmp_path,clock=clock,transport=transport)
    try:
        ready(session); transport.armed=True
        session.engine.device.request('PING')
        assert session.finished.wait(4)
        snapshot=session.snapshot()
        assert snapshot['writer']['status']=='ERROR'
        assert snapshot['off_confirmed'],session.engine.fault_reason
        assert transport.state.pwm==0 and transport.latched
        expected='USB write cancellation' if accepted is None else 'Short serial write'
        assert expected in session.engine.fault_reason
        assert sum(b' BEGIN ' in packet for packet in transport.writes)==1
        assert any(b' FAULT\n' in packet for packet in transport.writes)
        metadata=json.loads((session.engine.recorder.path/'session/metadata.json').read_text(encoding='utf-8'))
        assert metadata['shutdown_off_acknowledged']
    finally:
        session.request_stop('test cleanup'); session.finished.wait(4)


def test_permanent_disconnect_stays_unconfirmed_and_closes_within_deadline(tmp_path):
    clock=Clock(); transport=InterruptedWriteTransport(clock,0,permanent=True)
    session,_=make_session(tmp_path,clock=clock,transport=transport)
    try:
        ready(session); transport.armed=True; started=time.monotonic()
        session.engine.device.request('PING')
        assert session.finished.wait(3)
        assert time.monotonic()-started<2
        assert session.snapshot()['writer']['status']=='ERROR'
        assert not session.snapshot()['off_confirmed']
        assert sum(b' BEGIN ' in packet for packet in transport.writes)==1
        assert 'Short serial write' in session.engine.fault_reason
    finally:
        session.request_stop('test cleanup'); session.finished.wait(4)


def test_lost_first_clean_off_ack_retries_same_id_and_keeps_clean_shutdown(tmp_path):
    session,transport=make_session(tmp_path)
    ready(session); transport.drop_first_ack.add('OFF')
    session.request_stop('test lost OFF ACK')
    assert session.finished.wait(4)
    assert session.snapshot()['off_confirmed']
    assert session.snapshot()['writer']['status']=='CLOSED'
    requests=[packet for packet in transport.writes if b' OFF\n' in packet]
    assert len(requests)>=2 and len(set(requests))==1


def test_info_exposes_actual_firmware_revision_and_transport(tmp_path):
    clock=Clock(); transport=EmulatedTransport(clock)
    transport.hello_changes.update(firmware_revision='usb_idf_stream_off_ack.v2',
                                   serial_transport='idf_usb_serial_jtag',serial_ready=True,serial_init_error=0)
    session,_=make_session(tmp_path,clock=clock,transport=transport)
    try:
        ready(session)
        result=session.engine.command('info')
        assert result['accepted']
        assert 'usb_idf_stream_off_ack.v2' in result['reason'] and 'idf_usb_serial_jtag' in result['reason']
        assert session.snapshot()['pump_pwm_pct']==80 and transport.state.pump_start_count==1
    finally:
        session.request_stop('test info'); assert session.finished.wait(4)


def test_failed_begin_missing_only_lf_is_invalidated_before_emergency_off(tmp_path):
    class PartialBeginTransport(InterruptedWriteTransport):
        interrupted=False
        def write(self,data):
            if b' BEGIN ' in data and not self.interrupted:
                self.interrupted=True
                self.command_buffer.extend(data[:-1])
                return len(data)-1
            return super().write(data)
    clock=Clock(); transport=PartialBeginTransport(clock)
    session,_=make_session(tmp_path,clock=clock,transport=transport)
    try:
        assert session.finished.wait(4)
        assert transport.interrupted
        # Completing this partial BEGIN with plain LF would turn the pump ON
        # after the host already faulted. Invalidate the line before framing OFF.
        assert transport.state.pump_start_count==0
        assert transport.state.pwm==0 and session.snapshot()['writer']['status']=='ERROR'
        assert session.snapshot()['off_confirmed']
    finally:
        session.request_stop('test partial BEGIN'); session.finished.wait(4)
