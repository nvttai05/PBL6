import csv
import json
from pathlib import Path
import time
import pytest

from robonose_s3.clock import Clock, FakeClock
from robonose_s3.config import Config, PROFILE
from robonose_s3.emulator import EmulatedTransport
from robonose_s3.hardware import HardwareEngine
from robonose_s3.session import Session
from robonose_s3.storage_layout import trial_directory
from robonose_s3.usb_protocol import SerialOptions
from conftest import wait_until
from test_usb_protocol import sample


def make_session(tmp_path,clock=None,options=None,transport=None):
    clock=clock or Clock(); transport=transport or EmulatedTransport(clock,257)
    options=options or SerialOptions('EMULATED','emulated',ack_timeout_s=.05,off_timeout_s=.15)
    session=Session(tmp_path/'emulation',clock=clock,config=Config(checkpoint_s=.02),mode='EMULATED',
        engine_factory=lambda config,host_clock,recorder:HardwareEngine(config,host_clock,recorder,options,lambda:transport))
    session.start()
    return session,transport


def ready(session,pump=None):
    def predicate():
        session.snapshot()
        if session.finished.is_set():
            raise AssertionError(session.engine.fault_reason)
        return session.engine.startup=='ACTIVE'
    wait_until(predicate,pump=pump)


def test_automatic_begin_follows_persisted_preflight_no_serial_import(tmp_path,monkeypatch):
    import builtins
    original=builtins.__import__
    def guarded(name,*args,**kwargs):
        assert name!='serial' and not name.startswith('serial.')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded)
    session,transport=make_session(tmp_path)
    try:
        ready(session)
        assert session.snapshot()['pump_pwm_pct']==80
        assert session.snapshot()['air_path_commanded']=='SAMPLE'
        assert session.engine.recorder.synced_seq>=session.engine.preflight_seq
        assert any(b' BEGIN ' in command for command in transport.writes)
        assert PROFILE['id']=='s3_bringup_simulated'
    finally:
        session.request_stop('test'); assert session.finished.wait(4)
    assert session.snapshot()['off_confirmed']
    metadata=json.loads((session.engine.recorder.path/'session/metadata.json').read_text(encoding='utf-8'))
    assert metadata['mode']=='EMULATED' and metadata['phase_owner']=='EMULATED_MCU'
    wire=[json.loads(line) for line in (session.engine.recorder.path/'session/wire.jsonl').read_text(encoding='utf-8').splitlines()]
    received=b''.join(bytes.fromhex(item['bytes_hex']) for item in wire if item['direction']=='rx')
    assert received.startswith(b'ESP-ROM: boot chatter')
    assert any(p['direction']=='tx' and b' OFF\n' in bytes.fromhex(p['bytes_hex']) for p in wire)


def test_retry_same_request_does_not_create_second_trial(tmp_path):
    session,transport=make_session(tmp_path)
    try:
        ready(session); transport.drop_first_ack.add('START')
        session.post('start')
        wait_until(lambda: session.engine.pending is None and transport.state.trial_count==1)
        requests=[command for command in transport.writes if b' START ' in command]
        assert len(requests)==2 and requests[0]==requests[1]
        assert transport.state.trial_count==1
    finally:
        session.request_stop('test'); assert session.finished.wait(4)


def test_ack_timeout_latches_off_no_reconnect_or_simulation(tmp_path):
    session,transport=make_session(tmp_path)
    ready(session); transport.drop_ack_verbs.add('START')
    session.post('start')
    assert session.finished.wait(4)
    assert session.snapshot()['writer']['status']=='ERROR'
    assert 'ACK timeout' in session.engine.fault_reason
    assert transport.state.pwm==0 and transport.latched
    assert len([w for w in transport.writes if b' BEGIN ' in w])==1


@pytest.mark.parametrize('reason',[None,'usb_task_stalled_or_queue_full'])
def test_mcu_fault_retains_original_reason_in_log_and_shutdown(tmp_path,reason):
    session,transport=make_session(tmp_path)
    try:
        ready(session)
        with transport.lock:
            before=transport.context()
            transport.latched=True
            transport.state.stop(transport.clock.now(),fault=reason or 'old_firmware')
            packet={**transport._common('event'),**transport.context(),
                'event':'phase_change','previous_phase':before['phase'],
                'previous_trial_id':before.get('trial_id'),
                'effective_ms':round(transport.clock.now()*1000),
                'processed_ms':round(transport.clock.now()*1000),'barrier_seq':transport.sim.seq}
            if reason is not None:
                packet['fault_reason']=reason
            transport.inject(packet)
        assert session.finished.wait(4)
        root=session.engine.recorder.path
        metadata=json.loads((root/'session/metadata.json').read_text(encoding='utf-8'))
        expected='MCU reported latched ERROR'+(f': {reason}' if reason else '')
        assert metadata['fault_reason']==expected and metadata['status']=='ERROR'
        assert metadata['shutdown_off_acknowledged']
        events=[json.loads(line) for line in (root/'session/events.jsonl').read_text(encoding='utf-8').splitlines()]
        error=next(event for event in events if event['event']=='phase_change' and event['details']['next']=='ERROR')
        assert error['details']['fault_reason']==reason
        assert len([w for w in transport.writes if b' BEGIN ' in w])==1
    finally:
        session.request_stop('test cleanup')
        session.finished.wait(4)


def test_shutdown_without_ack_reports_unconfirmed_not_physical_stop(tmp_path):
    session,transport=make_session(tmp_path)
    ready(session); transport.drop_ack_verbs.add('OFF')
    session.request_stop('GUI-close')
    assert session.finished.wait(4)
    snap=session.snapshot()
    assert not snap['off_confirmed'] and snap['writer']['status']=='ERROR'
    metadata=json.loads((session.engine.recorder.path/'session/metadata.json').read_text(encoding='utf-8'))
    assert metadata['shutdown_off_acknowledged'] is False
    assert metadata['shutdown_off_is_command_state_only']


def test_old_inflight_sample_after_begin_cannot_rewind_snapshot(tmp_path):
    session,transport=make_session(tmp_path)
    try:
        ready(session)
        old=sample(transport,session.engine.device.last_seq+1)
        old.update(phase='OFF',context_epoch=0,segment_id=0,trial_id=None,phase_started_ms=0,
                   deadline_ms=None,pump_pwm_pct=0,valve_energized=False,air_path_commanded='FILTERED_AIR',session_id='')
        transport.inject(old)
        wait_until(lambda: session.snapshot()['sample_count']==old['seq'])
        assert session.snapshot()['phase']=='MONITOR' and session.snapshot()['pump_pwm_pct']==80
        assert session.engine.history[-1]['phase']=='OFF' and session.engine.history[-1]['pump_pwm_pct']==0
    finally:
        session.request_stop('test'); assert session.finished.wait(4)


def test_reset_and_handshake_failures_never_auto_restart(tmp_path):
    session,transport=make_session(tmp_path)
    ready(session)
    reboot=transport.hello(); reboot['boot_id']='rebooted'
    transport.inject(reboot)
    assert session.finished.wait(4)
    assert session.snapshot()['writer']['status']=='ERROR' and transport.state.pwm==0
    assert len([w for w in transport.writes if b' BEGIN ' in w])==1
    second_clock=Clock(); bad=EmulatedTransport(second_clock); bad.hello_changes['ads_fsr_v']=4.096
    second,_=make_session(tmp_path/'bad',clock=second_clock,transport=bad)
    assert second.finished.wait(4)
    assert not any(b' BEGIN ' in w for w in bad.writes)


def test_health_requires_ui_receive_write_and_sync(tmp_path,monkeypatch):
    session,transport=make_session(tmp_path)
    try:
        ready(session)
        wait_until(lambda: session.engine.healthy())
        session.engine.last_ui_read=-100
        assert not session.engine.healthy()
        session.engine.note_ui_read()
        health=session.engine.recorder.health()
        monkeypatch.setattr(session.engine.recorder,'health',lambda:{**health,'last_sync_mono_s':-100})
        assert not session.engine.healthy()
    finally:
        session.request_stop('test'); assert session.finished.wait(4)


def test_emulated_two_trials_feed_existing_qt_and_recorder(qapp,tmp_path):
    from robonose_s3.dashboard import Dashboard
    clock=FakeClock(); session,transport=make_session(tmp_path,clock)
    window=Dashboard(session); window.show()
    pump=qapp.processEvents
    def wait(predicate):
        wait_until(predicate,timeout=4,pump=pump)
    def command(text,phase=None):
        assert session.post(text)
        wait(lambda: session.commands.unfinished_tasks==0 and session.engine.pending is None and (phase is None or session.snapshot()['phase']==phase))
    def seconds(count):
        for _ in range(count):
            clock.advance(1)
            target=transport.sim.seq+1
            wait(lambda: session.snapshot()['sample_count']>=target or session.finished.is_set())
            assert not session.finished.is_set(), session.engine.fault_reason
            # Let the fixture's short checkpoint interval sync without changing user defaults.
            time.sleep(.003)
            session.snapshot()
    try:
        ready(session,pump)
        ids=[]
        for _ in range(2):
            command('start','BASELINE'); ids.append(session.snapshot()['trial_id'])
            seconds(60); wait(lambda: session.snapshot()['phase']=='WAIT_EXPOSURE')
            seconds(2); command('expose','EXPOSURE')
            seconds(120); wait(lambda: session.snapshot()['phase']=='WAIT_RECOVERY')
            assert session.snapshot()['air_path_commanded']=='SAMPLE'
            command('recover','RECOVERY'); seconds(60)
            wait(lambda: session.snapshot()['phase']=='WAIT_FINISH')
            command('finish','WAIT_NAME'); command('name Mẫu USB trùng tên'); command('notes chỉ là emulator')
            window.toggle_pause(); window.resize(1100,800); window.plots[0].setXRange(0,20)
            seconds(2); window.toggle_pause(); window.refresh()
            command('next','MONITOR')
        assert ids[0]!=ids[1] and transport.state.pump_start_count==1 and transport.sim.init_count==1
        assert not any(b' NAME ' in w or b' NOTES ' in w for w in transport.writes)
        assert window.grab().save(str(tmp_path/'emulator_qt.png'))
    finally:
        window.close(); assert session.finished.wait(4)
    with (session.engine.recorder.path/'session/raw.csv').open(encoding='utf-8',newline='') as handle:
        rows=list(csv.DictReader(handle))
    assert {r['phase'] for r in rows}>={'WAIT_EXPOSURE','WAIT_RECOVERY','WAIT_NAME'}
    for trial_id in ids:
        folder=trial_directory(session.engine.recorder.path,trial_id)
        metadata=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
        assert metadata['status']=='COMPLETE' and metadata['name']=='Mẫu USB trùng tên'
        assert (folder/'summary.json').is_file()


def test_hardware_adapter_writer_fault_still_parses_priority_off_ack(tmp_path):
    clock=FakeClock(); session,transport=make_session(tmp_path,clock)
    ready(session)
    def fail(_):
        raise OSError('injected host disk failure')
    session.engine.recorder.io_hook=fail
    clock.advance(1)
    assert session.finished.wait(4)
    assert transport.state.pwm==0 and transport.latched
    assert session.snapshot()['writer']['status']=='ERROR'
    assert session.snapshot()['off_confirmed']


def test_quit_during_handshake_cannot_wait_for_or_enable_begin(tmp_path):
    clock=Clock(); transport=EmulatedTransport(clock); transport.hello_changes['sensors_initialized']=False
    session,_=make_session(tmp_path,clock=clock,transport=transport)
    assert session.post('quit')
    assert session.finished.wait(4)
    assert not any(b' BEGIN ' in data for data in transport.writes)
    assert transport.state.pwm==0


def test_bad_frame_before_off_ack_in_same_chunk_does_not_discard_ack(tmp_path):
    class CorruptOffTransport(EmulatedTransport):
        def write(self,data):
            result=super().write(data)
            if b' OFF\n' in data:
                corrupt=json.dumps({'type':'event','protocol':'BROKEN','schema':'robonose.dataset.v1'}).encode()+b'\n'
                with self.lock:
                    self.rx[:0]=corrupt
            return result
    clock=Clock(); transport=CorruptOffTransport(clock,split_size=4096)
    session,_=make_session(tmp_path,clock=clock,transport=transport)
    ready(session)
    session.request_stop('test mixed chunk shutdown')
    assert session.finished.wait(4)
    assert session.snapshot()['writer']['status']=='ERROR'
    assert session.snapshot()['off_confirmed'] and transport.state.pwm==0
