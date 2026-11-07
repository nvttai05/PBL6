"""Byte-transport MCU emulator for software tests; never opens hardware."""
from collections import OrderedDict
import json
import threading
import time
import uuid

from .config import Config
from .simulated import SimDevice
from .state import StateMachine
from .usb_protocol import CHANNEL_MAP, FIRMWARE, PROFILE_ID, PROTOCOL
from .schema import SCHEMA


class EmulatedTransport:
    def __init__(self,clock,split_size=4096):
        self.clock=clock; self.config=Config(); self.state=StateMachine(self.config)
        self.sim=SimDevice(self.config,'emulator',clock)
        self.boot_id='emulated-boot-1'; self.session_id=''
        self.begin_ticket=uuid.uuid4().hex
        self.rx=bytearray(b'ESP-ROM: boot chatter (EMULATED)\r\n'); self.lock=threading.RLock()
        self.split_size=split_size; self.closed=False; self.writes=[]
        self.cache=OrderedDict(); self.highest_request=0; self.heartbeat=clock.now(); self.next_sample=clock.now()
        self.cache_session=''
        self.drop_ack_verbs=set(); self.drop_first_ack=set(); self.hello_changes={}
        self.sample_errors={}; self.latched=False; self.samples_enabled=True

    def _common(self,kind):
        return {'type':kind,'protocol':PROTOCOL,'schema':SCHEMA,'mode':'HARDWARE',
                'boot_id':self.boot_id,'session_id':self.session_id,'device_ms':round(self.clock.now()*1000)}

    def context(self):
        return {**self.state.context(self.clock.now()),'device_ms':round(self.clock.now()*1000),
            'phase_started_ms':round(self.state.phase_started*1000),
            'deadline_ms':None if self.state.deadline is None else round(self.state.deadline*1000),
            'trial_index':self.state.trial_count,'trial_status':self.state.trial.status if self.state.trial else 'ACTIVE'}

    def hello(self):
        return {**self._common('hello'),**self.context(),'firmware_version':FIRMWARE,
            'firmware_kind':'robonose_dataset_s3','device_id':'EMULATED-NOT-A-BOARD','channel_map':CHANNEL_MAP,
            'begin_ticket':self.begin_ticket,
            'ads_fsr_v':6.144,'ads_lsb_v':.0001875,'divider_factor':1,'ads_data_rate_sps':128,
            'ads_mode':'single_shot_single_ended','ads_vdd_requested_v':5,'ads_address':72,
            'ads_sda':10,'ads_scl':11,'bme_sda':8,'bme_scl':9,'bme_address':119,
            'i2c_hz':100000,'i2c_timeout_ms':50,'profile_id':PROFILE_ID,'heater_requested_c':300,
            'heater_requested_ms':100,'os_t_requested':2,'os_h_requested':2,'os_p_requested':4,
            'os_t_applied':2,'os_h_applied':2,'os_p_applied':4,'heater_applied_ms':100,
            'heater_res_heat_readback':110,'heater_gas_wait_readback':89,'heater_idac_readback':0,
            'bme_chip_id':97,'bme_variant_id':1,'profile_readback_ok':True,'production_profile':None,
            'sensors_initialized':True,'sensors_ready':True,'output_ready':True,'fault_latched':self.latched,
            'pump_pin':5,'valve_pin':4,'pump_pwm_hz':1000,'pump_pwm_bits':10,
            'valve_off_air_path':'FILTERED_AIR','valve_on_air_path':'SAMPLE',
            'sample_interval_ms':1000,'lease_ms':15000,'reset_reason':'EMULATED',**self.hello_changes}

    def inject(self,packet):
        with self.lock:
            self.rx.extend(packet if isinstance(packet,bytes) else json.dumps(packet,allow_nan=False).encode()+b'\n')

    def _transitions(self,before):
        for event in self.state.drain_events():
            if event['event']=='phase_change':
                packet={**self._common('event'),**self.context(),
                    **{key:event[key] for key in ('phase','context_epoch','segment_id','trial_id','pump_pwm_pct','valve_energized','air_path_commanded')},
                    'event':'phase_change','previous_phase':event['details']['previous'],
                    'previous_trial_id':before.get('trial_id'),'effective_ms':round(event['effective_mono_s']*1000),
                    'processed_ms':round(event['processed_mono_s']*1000),'barrier_seq':self.sim.seq}
                if packet['phase']=='WAIT_NAME':
                    packet['trial_status']=self.state.trial.status
                self.inject(packet)

    def _tick(self):
        now=self.clock.now(); before=self.context()
        if self.state.pwm and now-self.heartbeat>=15:
            self.latched=True; self.state.stop(now,fault='lease_expired')
        else:
            self.state.advance(now)
        self._transitions(before)
        if self.samples_enabled and now>=self.next_sample:
            row=self.sim.read(now,self.state.context(now),errors=self.sample_errors)
            row.update(self._common('sample')); row.update(self.context())
            row['boot_id']=self.boot_id; row['profile_id']=PROFILE_ID
            self.inject(row)
            self.next_sample=now+1

    def _command(self,line):
        if line=='HELLO':
            if self.state.phase in ('OFF','CLOSED') and not self.latched:
                self.begin_ticket=uuid.uuid4().hex
            self.inject(self.hello()); return
        if line=='ALL_OFF':
            tokens=['@0',self.boot_id,self.session_id or 'unbound','FAULT']
        else:
            tokens=line.split()
        if len(tokens) not in (4,5) or not tokens[0].startswith('@'):
            self.inject({**self._common('parser_event'),'reason':'invalid_command'}); return
        try:
            request_id=int(tokens[0][1:])
        except ValueError:
            return
        _,boot,session,verb=tokens[:4]; argument=tokens[4] if len(tokens)==5 else ''
        if (boot==self.boot_id and verb=='BEGIN' and self.state.phase in ('OFF','CLOSED')
            and self.begin_ticket and argument==self.begin_ticket and session!=self.session_id
            and session!=self.cache_session and not self.latched):
            self.cache.clear(); self.highest_request=0
            self.cache_session=session
        before=self.context(); accepted=False; reason='wrong_state_or_arguments'; now=self.clock.now()
        if verb in ('OFF','FAULT'):
            self.latched|=verb=='FAULT'; self.state.stop(now,fault='host_fault' if verb=='FAULT' else None)
            accepted=True; reason='commanded_off'
        elif boot!=self.boot_id:
            reason='boot_mismatch'
        elif request_id in self.cache:
            original,ack=self.cache[request_id]
            if original==line:
                if verb not in self.drop_ack_verbs:
                    self.inject(ack)
                return
            reason='request_id_reuse'
        elif request_id<=self.highest_request:
            reason='request_id_expired'
        elif self.latched:
            reason='fault_latched_reset_required'
        elif (verb=='BEGIN' and self.begin_ticket and argument==self.begin_ticket
              and self.state.phase in ('OFF','CLOSED') and session!=self.session_id):
            self.session_id=session
            self.begin_ticket=''
            self.state.phase='OFF'; self.state.start_session(now); self.heartbeat=now
            accepted=True; reason='accepted'
        elif session!=self.session_id:
            reason='session_mismatch'
        elif verb=='PING' and self.state.pwm==80:
            self.heartbeat=now; accepted=True; reason='accepted'
        elif verb=='STATUS':
            accepted=True; reason='accepted'
        elif verb=='MARK':
            accepted=True; reason='accepted'
        else:
            command=verb.lower()
            if verb=='START':
                result=self.state.command('start',now)
                if result['accepted']:
                    old=self.state.trial.trial_id; self.state.trial.trial_id=argument
                    for event in self.state.events:
                        if event.get('trial_id')==old:
                            event['trial_id']=argument
            elif verb=='EXTEND':
                try:
                    result=self.state.command(f'extend {int(argument)/1000}',now)
                except ValueError:
                    result={'accepted':False,'reason':'extend_out_of_bounds'}
            else:
                result=self.state.command(command,now)
            accepted=result['accepted']; reason='accepted' if accepted else result['reason']
        self.highest_request=max(self.highest_request,request_id)
        self._transitions(before)
        ack={**self._common('ack'),**self.context(),'request_id':request_id,'accepted':accepted,
             'reason':reason,'applied_ms':round(now*1000),'barrier_seq':self.sim.seq}
        if verb not in ('OFF','FAULT'):
            self.cache[request_id]=(line,ack)
            if len(self.cache)>16:
                self.cache.popitem(last=False)
        if verb in self.drop_first_ack:
            self.drop_first_ack.remove(verb)
        elif verb not in self.drop_ack_verbs:
            self.inject(ack)

    def write(self,data):
        with self.lock:
            self.writes.append(data)
            for line in data.decode('ascii').splitlines():
                self._command(line)
        return len(data)

    def read(self,size):
        with self.lock:
            if self.closed:
                return b''
            self._tick()
            if self.rx:
                count=min(size,self.split_size,len(self.rx)); data=bytes(self.rx[:count]); del self.rx[:count]
                return data
        time.sleep(.005)
        return b''

    def close(self):
        self.closed=True
