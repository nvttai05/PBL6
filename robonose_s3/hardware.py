"""Host projection of MCU state: no host phase clock or simulated sensor fallback."""
from collections import deque
from copy import deepcopy
import hashlib
import json
import queue
import uuid

from .config import CHANNELS, PROFILE
from .quality import evaluate
from .schema import COLUMNS, SCHEMA, DEVICES
from .serial_device import SerialDevice
from .state import HELP
from .usb_protocol import ProtocolError, SAMPLE_PHASES


class DeviceState:
    def __init__(self):
        self.phase='OFF'

    @property
    def closed(self):
        return self.phase in ('CLOSED','ERROR')


class HardwareEngine:
    def __init__(self,config,clock,recorder,options,transport_factory=None):
        self.config,self.clock,self.recorder=config,clock,recorder
        if (config.baseline_s,config.exposure_s,config.recovery_s,config.sampling_hz)!=(60,120,60,1):
            raise ValueError('Hardware firmware v1 requires the approved 60/120/60 s, 1 Hz profile')
        self.mode=recorder.mode
        self.state=DeviceState()
        self.context={'phase':'OFF','context_epoch':0,'segment_id':0,'trial_id':None,
            'pump_pwm_pct':0,'valve_energized':False,'air_path_commanded':'FILTERED_AIR',
            'device_ms':0,'phase_started_ms':0,'deadline_ms':None}
        self.history=deque(maxlen=config.history_size)
        self.events=deque(maxlen=100)
        self.messages=deque(maxlen=128)
        self.trials={}; self.finalizations={}
        self.last_event_epoch=0; self.highest_ingested=0; self.anchor=None
        self.hardware_config_hash=None; self.pending=None; self.pending_text=''
        self.startup='HANDSHAKE'; self.preflight_seq=None; self.started=clock.now()
        self.fault_reason=None; self.shutdown_count=0; self.quit_requested=False
        self.bad_scans=0; self.errors=0; self.stale=0
        self.skipped_cycles=0
        self.last_ui_read=clock.now(); self.last_control_tick=clock.now()
        self.quality=evaluate([],0,config)
        self.device=SerialDevice(options,recorder.session_id,clock,
            lambda payload:recorder.submit('wire',payload),self.healthy,transport_factory)
        self.device.start()

    @property
    def command_ready(self):
        return self.startup=='ACTIVE' and self.pending is None and not self.quit_requested

    def healthy(self):
        now=self.clock.now(); health=self.recorder.health()
        return bool(self.device.last_sample_at is not None and now-self.device.last_sample_at<3
            and health['last_written_seq'] is not None and health['last_written_seq']>=self.device.last_seq-1
            and health['last_sync_mono_s'] is not None and now-health['last_sync_mono_s']<=max(3,self.config.checkpoint_s*2)
            and now-self.last_control_tick<1 and now-self.last_ui_read<3
            and not self.fault_reason and self.startup=='ACTIVE')

    def _event(self,event,effective_mono_s=None,**details):
        processed=self.device_now(); now=processed if effective_mono_s is None else effective_mono_s
        packet={'event':event,'mode':self.mode,'effective_mono_s':now,'processed_mono_s':processed,
                'timestamp':self.wall_at_device(now),'details':details}
        self.events.append(packet); self.recorder.submit('event',packet)

    def device_now(self):
        return self.clock.now()+self.anchor['offset_s'] if self.anchor else 0

    def wall_at_device(self,value):
        return self.clock.timestamp(value-self.anchor['offset_s']) if self.anchor else None

    def _on_hello(self,packet):
        if self.anchor is None:
            host=self.clock.now(); device=packet['device_ms']/1000
            self.anchor={'host_mono_s':host,'device_mono_s':device,'offset_s':device-host,
                         'method':'hello_receive_anchor','uncertainty':'USB/queue delay unmeasured; not sensor gas-arrival time'}
            self.last_event_epoch=packet['context_epoch']
        if self.hardware_config_hash is None and packet.get('profile_readback_ok'):
            config=deepcopy(self.config.snapshot()); config.pop('bme_applied_simulated',None)
            config['bme_requested']={**PROFILE,'id':packet['profile_id']}
            fields=('channel_map','ads_fsr_v','ads_lsb_v','divider_factor','ads_data_rate_sps','ads_mode',
                    'ads_vdd_requested_v','ads_address','ads_sda','ads_scl','bme_sda','bme_scl','bme_address',
                    'i2c_hz','i2c_timeout_ms','profile_id','heater_requested_c','heater_requested_ms',
                    'os_t_requested','os_h_requested','os_p_requested','os_t_applied','os_h_applied','os_p_applied',
                    'heater_res_heat_readback','heater_gas_wait_readback','heater_idac_readback','heater_applied_ms',
                    'bme_chip_id','bme_variant_id','pump_pin','valve_pin','pump_pwm_hz','pump_pwm_bits',
                    'sample_interval_ms','lease_ms')
            config['device_configuration']={key:packet.get(key) for key in fields}
            self.hardware_config_hash=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
            self.recorder.submit('session_metadata',{'device_hello':packet,'config':config,
                'config_hash':self.hardware_config_hash,'clock_mapping':self.anchor,
                'serial_options':self.device.options.__dict__,
                'time_bases':{'mono_s':'MCU boot seconds','received_mono_s':'host process monotonic seconds'},
                'hardware_validated':False,'profile_applied_is_simulated':self.mode=='EMULATED'})
        self._update_context(packet)

    def _update_context(self,packet):
        key=(packet.get('context_epoch',0),packet.get('device_ms',0))
        current=(self.context['context_epoch'],self.context['device_ms'])
        if key>=current:
            self.context=dict(packet)
            if not self.fault_reason:
                self.state.phase=packet['phase']
            if packet['phase']=='ERROR':
                reason=packet.get('fault_reason')
                self.fault('MCU reported latched ERROR'+(f': {reason}' if reason else ''))

    def _save_trial(self,trial,finalize=False):
        self.recorder.submit('trial',{'trial':trial,'finalize':finalize})

    def _on_transition(self,packet):
        epoch=packet['context_epoch']
        if epoch<=self.last_event_epoch:
            self._event('old_or_duplicate_phase_event',context_epoch=epoch); return
        if epoch!=self.last_event_epoch+1:
            raise ProtocolError('MCU phase event/context epoch gap')
        self.last_event_epoch=epoch
        phase=packet['phase']; previous=packet.get('previous_phase')
        effective=packet['effective_ms']/1000
        previous_trial=packet.get('previous_trial_id')
        if previous_trial in self.trials and previous!='MONITOR':
            trial=self.trials[previous_trial]
            if trial['intervals'] and trial['intervals'][-1]['end_mono_s'] is None:
                trial['intervals'][-1]['end_mono_s']=effective
            if phase in ('CLOSED','ERROR'):
                if trial['status']=='ACTIVE':
                    trial['status']='ERROR' if phase=='ERROR' else 'ABORTED'
                    trial['finished_mono_s']=effective
            if phase in ('MONITOR','CLOSED','ERROR'):
                self.finalizations[previous_trial]=packet.get('barrier_seq',0)
                self._save_trial(trial)
        trial_id=packet.get('trial_id')
        if trial_id and phase not in ('OFF','CLOSED','ERROR','MONITOR'):
            if trial_id not in self.trials:
                if phase!='BASELINE':
                    raise ProtocolError('Trial context appeared without a baseline transition')
                self.trials[trial_id]={'trial_id':trial_id,'index':packet['trial_index'],
                    'started_mono_s':effective,'status':'ACTIVE','name':None,'notes':None,
                    'finished_mono_s':None,'intervals':[]}
            trial=self.trials[trial_id]
            trial['status']=packet['trial_status']
            if phase=='WAIT_NAME':
                trial['finished_mono_s']=effective
            deadline=packet.get('deadline_ms')
            trial['intervals'].append({'phase':phase,'segment_id':packet['segment_id'],
                'start_mono_s':effective,'end_mono_s':None,
                'planned_s':None if deadline is None else deadline/1000-effective,
                'air_path_commanded':packet['air_path_commanded']})
            self._save_trial(trial)
        event={'event':'phase_change','mode':self.mode,'effective_mono_s':effective,
               'processed_mono_s':packet['processed_ms']/1000,'timestamp':self.wall_at_device(effective),
               'details':{'previous':previous,'next':phase,'barrier_seq':packet.get('barrier_seq',0),
                          'fault_reason':packet.get('fault_reason')}}
        self.events.append(event); self.recorder.submit('event',event)
        self._update_context(packet)
        if phase=='ERROR':
            self.fault('MCU reported latched ERROR')

    def _on_sample(self,packet):
        if not self.hardware_config_hash:
            return  # Wire is retained; startup hello readback is still incomplete.
        if packet['context_epoch']>self.last_event_epoch:
            raise ProtocolError('Sample context missing its MCU phase event')
        trial_id=packet.get('trial_id')
        if trial_id and trial_id not in self.trials:
            raise ProtocolError('Unknown/finalized trial in incoming sample')
        row={key:packet.get(key) for key in COLUMNS}
        row.update(schema=SCHEMA,mode=self.mode,session_id=self.recorder.session_id,
                   timestamp=self.wall_at_device(packet['mono_s']),received_at=self.clock.timestamp(),
                   received_mono_s=self.clock.now(),config_hash=self.hardware_config_hash)
        self.recorder.submit('sample',row)
        self.highest_ingested=packet['seq']
        self.skipped_cycles+=packet.get('skipped_cycles',0)
        self.history.append(row)
        self.quality=evaluate(self.history,max(packet['mono_s'],self.device_now()),self.config)
        self.errors+=sum(packet[f'{sensor}_status']=='ERROR' for sensor in DEVICES)
        self.stale+=sum(packet[f'{sensor}_status']=='STALE' for sensor in DEVICES)
        scan_healthy=all(packet[f'{sensor}_fresh'] and packet[f'{sensor}_valid'] for sensor in DEVICES)
        self.bad_scans=0 if scan_healthy else self.bad_scans+1
        if self.startup=='PREFLIGHT' and self.preflight_seq is None and scan_healthy:
            self.preflight_seq=packet['seq']; self.recorder.submit('sync',{})
        if self.startup=='ACTIVE' and self.bad_scans>=3:
            raise ProtocolError('Required sensors failed/stale for three consecutive scans')
        self._update_context(packet)

    def _consume(self,packet):
        kind=packet.get('type')
        if kind=='device_fault':
            self._event('mcu_fault_text',frame=packet)
            self.fault(self.device.error or packet.get('detail','MCU fault text'))
        elif kind=='hello':
            self._on_hello(packet)
            if self.device.ready.is_set() and self.startup=='HANDSHAKE':
                self.startup='PREFLIGHT'
        elif kind=='sample':
            self._on_sample(packet)
        elif kind=='event' and packet.get('event')=='phase_change':
            self._on_transition(packet)
        elif kind=='ack':
            self._event('mcu_ack',frame=packet)
            self._update_context(packet)
            if packet['phase']=='ERROR':
                self.fault('MCU ACK reports latched ERROR')
        else:
            self._event('parser_or_device_event',frame=packet)

    def _drain(self):
        for _ in range(256):
            try:
                packet=self.device.incoming.get_nowait()
            except queue.Empty:
                break
            self._consume(packet)
            self.device.incoming.task_done()
        for trial_id,barrier in list(self.finalizations.items()):
            if self.highest_ingested>=barrier:
                self._save_trial(self.trials.pop(trial_id),finalize=True)
                del self.finalizations[trial_id]

    def step(self):
        self.last_control_tick=self.clock.now()
        try:
            if self.device.error and not self.fault_reason:
                self.fault(self.device.error)
            self._drain()
            if self.recorder.fault_reason or self.device.error:
                raise ProtocolError(self.recorder.fault_reason or self.device.error)
            if self.startup!='ACTIVE' and self.clock.now()-self.started>self.device.options.handshake_timeout_s+5:
                raise ProtocolError('Startup preflight/log sync timeout; BEGIN not permitted')
            if self.startup=='PREFLIGHT' and self.preflight_seq is not None:
                health=self.recorder.health()
                if health['synced_seq'] is not None and health['synced_seq']>=self.preflight_seq:
                    self.pending=self.device.request('BEGIN',self.device.hello['begin_ticket'],expected_phase='MONITOR')
                    self.pending_text='BEGIN'; self.startup='BEGIN_PENDING'
            if self.pending and self.pending.done.is_set():
                if self.pending.error:
                    raise ProtocolError(self.pending.error)
                result=self.pending.result
                if self.pending.verb=='BEGIN':
                    if not result['accepted']:
                        raise ProtocolError('BEGIN rejected: '+result['reason'])
                    self.startup='ACTIVE'
                if result['accepted'] and self.pending.verb=='MARK':
                    self._event('marker',effective_mono_s=result['applied_ms']/1000,
                                text=self.pending_text.partition(' ')[2],request_id=self.pending.request_id)
                if result['accepted'] and self.pending.verb=='START' and self.quality['overall']!='STABLE':
                    self._event('baseline_started_without_stability',effective_mono_s=result['applied_ms']/1000,quality=self.quality)
                self.messages.append(f"ACK {self.pending_text}: {result['accepted']} {result['reason']}")
                self.pending=None
            if self.quit_requested and self.device.closed.is_set() and not self.device.off_acknowledged:
                raise ProtocolError('Shutdown OFF ACK not confirmed')
        except Exception as error:
            self.fault(error)

    def fault(self,reason):
        if not self.fault_reason:
            self.fault_reason=str(reason)
            self.device.fault(reason)  # Priority route, independent of recorder queues.
            try:
                self._event('host_session_fault',reason=self.fault_reason)
            except Exception:
                pass
        self.state.phase='ERROR'

    def command(self,text,request_id=None,received_mono=None):
        command,_,argument=text.strip().partition(' '); command=command.lower(); argument=argument.strip()
        result={'accepted':False,'reason':'Invalid command or arguments','phase':self.state.phase}
        try:
            if len(text)>2048:
                return {**result,'reason':'Command exceeds 2048 characters'}
            self._event('host_command_received',text=text,request_id=request_id,
                received_mono_s=self.clock.now() if received_mono is None else received_mono)
            if command in ('help','info','status','durations') and not argument:
                if command=='info':
                    hello=self.device.hello or {}
                    reason=str({key:hello.get(key) for key in
                        ('firmware_version','firmware_revision','serial_transport','serial_ready','serial_init_error',
                         'serial_irq_enabled_before','serial_irq_pending_before','serial_irq_enabled_after_init','serial_irq_owned_mask')})
                    reason+=f' | port={self.device.options.port} kind={self.device.options.kind} | state={self.context}'
                else:
                    reason=HELP if command=='help' else str(self.context) if command!='durations' else 'baseline=60s exposure=120s recovery=60s'
                return {**result,'accepted':True,'reason':reason}
            if command in ('name','notes') and argument:
                trial=self.trials.get(self.context.get('trial_id'))
                if self.state.phase=='WAIT_NAME' and trial:
                    trial[command]=argument; self._save_trial(trial)
                    return {**result,'accepted':True,'reason':'host metadata updated; MCU state unchanged'}
                return {**result,'reason':'Name/notes require MCU WAIT_NAME'}
            if command=='quit' and not argument:
                self.quit_requested=True; self.device.priority_off()
                return {**result,'accepted':None,'reason':'priority OFF requested; awaiting MCU confirmation'}
            verbs={'start':'BASELINE','expose':'EXPOSURE','recover':'RECOVERY','finish':'WAIT_NAME',
                   'abort':'WAIT_NAME','next':'MONITOR','extend':'RECOVERY','mark':None}
            if command not in verbs or (command not in ('extend','mark') and argument):
                return result
            wire_argument=''
            if command=='start':
                wire_argument=str(uuid.uuid4())
            elif command=='extend':
                import math
                try:
                    seconds=float(argument)
                    if not math.isfinite(seconds) or not 0<seconds<=self.config.max_extend_s:
                        raise ValueError()
                    wire_argument=str(round(seconds*1000))
                    if int(wire_argument)<1:
                        raise ValueError()
                except ValueError:
                    return {**result,'reason':'extend needs finite positive seconds <= 3600'}
            elif command=='mark' and not argument:
                return result
            self.pending=self.device.request(command.upper(),wire_argument,verbs[command])
            self.pending_text=text
            return {**result,'accepted':None,'reason':f'queued request {self.pending.request_id}; awaiting MCU ACK'}
        except Exception as error:
            self.fault(error)
            return {**result,'reason':str(error)}

    def drain_messages(self):
        messages=list(self.messages); self.messages.clear(); return messages

    def snapshot(self):
        packet=self.context; now=self.device_now()
        trial=self.trials.get(packet.get('trial_id'))
        deadline=packet.get('deadline_ms')
        return {'mode':self.mode,'now':now,'phase':self.state.phase,'context_epoch':packet['context_epoch'],
            'segment_id':packet['segment_id'],'trial_id':packet.get('trial_id'),
            'phase_elapsed_s':max(0,now-packet['phase_started_ms']/1000),
            'pump_pwm_pct':packet['pump_pwm_pct'],'valve_energized':packet['valve_energized'],
            'air_path_commanded':packet['air_path_commanded'],
            'remaining_s':None if deadline is None else max(0,deadline/1000-now),
            'trial':deepcopy(trial),'latest':self.history[-1] if self.history else None,
            'history':tuple(self.history),'events':tuple(self.events),'quality':self.quality,
            'writer':self.recorder.health(),'sample_count':self.highest_ingested,'gaps':self.device.gaps+self.skipped_cycles,
            'errors':self.errors,'stale':self.stale,'heartbeat_healthy':self.healthy(),
            'simulated_heartbeat_healthy':False,'startup':self.startup,
            'off_confirmed':self.device.off_acknowledged,'fault':self.fault_reason}

    def note_ui_read(self):
        self.last_ui_read=self.clock.now()

    def shutdown(self,reason='quit'):
        if self.shutdown_count:
            return
        self.shutdown_count+=1
        self.device.close()
        if self.device.error:
            self.fault(self.device.error)
        try:
            self._drain()
            if self.device.off_acknowledged and self.device.off_pending.result:
                self._update_context(self.device.off_pending.result)
        except Exception as error:
            self.fault_reason=self.fault_reason or str(error)
        if not self.device.off_acknowledged or self.highest_ingested<self.device.off_barrier:
            self.fault_reason=self.fault_reason or 'Commanded OFF/drain not confirmed within shutdown deadline'
        if self.fault_reason:
            self.state.phase='ERROR'; self.recorder.fail(self.fault_reason)
        self.recorder.close(reason,final_details={'shutdown_off_acknowledged':self.device.off_acknowledged,
            'shutdown_off_is_command_state_only':True,'shutdown_drain_complete':self.highest_ingested>=self.device.off_barrier,
            'fault_reason':self.fault_reason})
        if self.recorder.fault_reason:
            self.state.phase='ERROR'
