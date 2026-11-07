"""Record two virtual-time trials through byte transport, SerialDevice and Qt snapshots."""
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from robonose_s3.clock import FakeClock
from robonose_s3.config import Config
from robonose_s3.emulator import EmulatedTransport
from robonose_s3.hardware import HardwareEngine
from robonose_s3.session import Session
from robonose_s3.storage_layout import trial_directory
from robonose_s3.usb_protocol import SerialOptions


def main():
    configured=json.loads((ROOT/'configs/paths.local.json').read_text(encoding='utf-8'))['python_exe']
    if Path(configured).resolve()!=Path(sys.executable).resolve():
        raise SystemExit('Use python_exe from paths.local.json')
    clock=FakeClock(); transport=EmulatedTransport(clock,split_size=257)
    session=Session(ROOT/'data/emulation',clock=clock,config=Config(checkpoint_s=.02),mode='EMULATED',
        engine_factory=lambda c,k,r:HardwareEngine(c,k,r,SerialOptions('EMULATOR','emulated'),lambda:transport))
    session.start(); ids=[]
    def wait(predicate):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            session.snapshot()
            if session.finished.is_set() and session.engine.fault_reason:
                raise RuntimeError(session.engine.fault_reason)
            if predicate():
                return
            time.sleep(.005)
        raise RuntimeError('Fixture timed out')
    def command(text,phase=None):
        assert session.post(text)
        wait(lambda:session.commands.unfinished_tasks==0 and session.engine.pending is None
             and (phase is None or session.snapshot()['phase']==phase))
    def seconds(count):
        for _ in range(count):
            clock.advance(1); target=transport.sim.seq+1
            wait(lambda:session.snapshot()['sample_count']>=target)
            time.sleep(.003)
    window=None
    try:
        wait(lambda:session.engine.startup=='ACTIVE')
        seconds(3)
        for number in (1,2):
            command('start','BASELINE'); ids.append(session.snapshot()['trial_id'])
            seconds(60); wait(lambda:session.snapshot()['phase']=='WAIT_EXPOSURE')
            if number==1:
                transport.sample_errors={'tgs2602':'ERROR','bme688':'STALE'}; seconds(1); transport.sample_errors={}
            seconds(2); command('mark thao tác mẫu EMULATED'); command('expose','EXPOSURE')
            seconds(120); wait(lambda:session.snapshot()['phase']=='WAIT_RECOVERY')
            seconds(2); command('recover','RECOVERY'); seconds(60)
            wait(lambda:session.snapshot()['phase']=='WAIT_FINISH'); seconds(2)
            if number==2:
                command('extend 10','RECOVERY'); seconds(10)
                wait(lambda:session.snapshot()['phase']=='WAIT_FINISH'); seconds(2)
            command('finish','WAIT_NAME'); command('name Mẫu USB trùng tên'); command('notes EMULATED — không phải dữ liệu cảm biến thật')
            seconds(2)
            if number==1:
                command('next','MONITOR'); seconds(2)
        os.environ['QT_QPA_PLATFORM']='offscreen'
        from PySide6 import QtWidgets
        from robonose_s3.dashboard import Dashboard,configure_qt_font
        app=QtWidgets.QApplication([]); configure_qt_font(app)
        window=Dashboard(session); window.window_combo.setCurrentIndex(1); window.show()
        app.processEvents(); window.refresh()
        assert window.grab().save(str(ROOT/'runtime/stage03/EMULATED_DASHBOARD.png'))
        command('next','MONITOR'); seconds(2); command('quit')
        wait(lambda:session.finished.is_set())
    finally:
        session.request_stop('fixture cleanup'); session.finished.wait(5)
        if window:
            window.close()
    if session.engine.fault_reason or session.engine.recorder.fault_reason:
        raise RuntimeError(session.engine.fault_reason or session.engine.recorder.fault_reason)
    folder=session.engine.recorder.path
    with (folder/'session/raw.csv').open(encoding='utf-8',newline='') as handle:
        rows=list(csv.DictReader(handle))
    summaries=[]
    for trial_id in ids:
        trial=trial_directory(folder,trial_id)
        summary=json.loads((trial/'summary.json').read_text(encoding='utf-8'))
        assert summary['mode']=='EMULATED' and summary['raw_sha256']==hashlib.sha256((trial/'raw.csv').read_bytes()).hexdigest()
        summaries.append({'trial_id':trial_id,'folder':trial.name,'process_status':summary['process_status'],'quality':summary['quality']})
    report={'mode':'EMULATED','physical_hardware_used':False,'clock':'FakeClock, virtual MCU time',
        'session_path':str(folder),'rows':len(rows),'trials':summaries,'split_transport_bytes':257,
        'preflight_synced_before_begin':True,'fixture_checkpoint_s':.02,'user_checkpoint_default_s':5,
        'shutdown_off_acknowledged':session.snapshot()['off_confirmed'],'pump_start_count':transport.state.pump_start_count,
        'sensor_init_count':transport.sim.init_count,'null_tgs_rows':sum(not row['tgs2602_voltage_v'] for row in rows),
        'raw_sha256':hashlib.sha256((folder/'session/raw.csv').read_bytes()).hexdigest(),
        'wire_sha256':hashlib.sha256((folder/'session/wire.jsonl').read_bytes()).hexdigest()}
    (ROOT/'runtime/stage03/EMULATED_FIXTURE.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
