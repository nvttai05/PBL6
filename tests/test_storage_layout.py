import csv
import json
from pathlib import Path
import uuid
import pytest

from robonose_s3.clock import FakeClock
from robonose_s3.config import Config
from robonose_s3.layout_migration import apply_layout, digest, plan_layout, rollback_layout, translated
from robonose_s3.recorder import Recorder
from robonose_s3.sample_catalog import find_samples
from robonose_s3.schema import SCHEMA
from robonose_s3.storage_layout import (DatasetLease, available_folder, readable_folder,
    resolve_session_path, safe_label, trial_directory)
from conftest import drain


@pytest.mark.parametrize('name,expected',[
    ('Tai','Tai'), ('  Tài cà phê  ','Tài_cà_phê'), ('../A:B\\C?*<>|"','A_B_C'),
    ('CON','Mau_CON'), ('nul','Mau_nul'), ('   ','Chua_dat_ten'), ('A'*80,'A'*32)])
def test_windows_safe_name_keeps_vietnamese_and_bounds_length(name,expected):
    assert safe_label(name)==expected


def test_short_id_collision_extends_suffix_without_overwriting(tmp_path):
    first='12345678-1234-4000-8000-000000000001'
    second='12345678-1234-4000-8000-000000000002'
    stamp='2026-11-06T13:35:29+00:00'
    folder=available_folder(tmp_path,'Tai',stamp,first); folder.mkdir()
    assert folder.name=='Tai_203529_2026-11-06_123456781234'
    # Exercise both short-prefix collisions before falling back to full hex.
    (tmp_path/readable_folder('Tai',stamp,first,20)).mkdir()
    longer=available_folder(tmp_path,'Tai',stamp,second)
    assert longer!=folder and longer.name.endswith(uuid.UUID(second).hex)
    assert folder.is_dir()


def test_live_name_and_rename_keep_rows_identity_and_summary(engine):
    assert engine.recorder.path.name.startswith('Phien_090000_2026-11-06_')
    engine.command('start'); engine.step(); drain(engine)
    identifier=engine.state.trial.trial_id
    temporary=trial_directory(engine.recorder.path,identifier)
    assert temporary.name.startswith('Chua_dat_ten_090000_2026-11-06_')
    engine.command('abort'); engine.command('name Tài cà phê'); drain(engine)
    named=trial_directory(engine.recorder.path,identifier)
    assert named.name.startswith('Tài_cà_phê_090000_2026-11-06_') and not temporary.exists()
    engine.clock.advance(1); engine.step(); drain(engine)
    before=(named/'raw.csv').read_bytes()
    engine.command('name Tai'); drain(engine)
    final=trial_directory(engine.recorder.path,identifier)
    assert final.name.startswith('Tai_090000_2026-11-06_') and not named.exists()
    assert (final/'raw.csv').read_bytes()==before
    engine.clock.advance(1); engine.step(); drain(engine)
    engine.command('next'); drain(engine); engine.shutdown()
    metadata=json.loads((final/'metadata.json').read_text(encoding='utf-8'))
    assert metadata['trial_id']==identifier and metadata['name']=='Tai'
    assert metadata['folder']==final.name and metadata['storage_layout_version']==2
    with (final/'raw.csv').open(encoding='utf-8',newline='') as handle:
        rows=list(csv.DictReader(handle))
    assert len(rows)==3 and all(row['trial_id']==identifier for row in rows)
    assert (final/'summary.json').is_file()
    assert engine.state.pump_start_count==1 and engine.device.init_count==1
    assert find_samples(engine.recorder.path.parents[2],'Tai').matches[0].folder==final


def test_windows_folder_lock_defers_rename_and_keeps_acquisition(engine,monkeypatch):
    engine.command('start'); engine.step(); drain(engine)
    identifier=engine.state.trial.trial_id
    original_folder=trial_directory(engine.recorder.path,identifier)
    engine.command('abort'); drain(engine)
    original_rename=Path.rename
    failed=False
    def locked_once(path,destination):
        nonlocal failed
        if path==original_folder and not failed:
            failed=True
            raise PermissionError('injected folder lock')
        return original_rename(path,destination)
    monkeypatch.setattr(Path,'rename',locked_once)
    engine.command('name Tai'); drain(engine)
    assert original_folder.is_dir() and not engine.recorder.fault_reason
    engine.clock.advance(1); engine.step(); drain(engine)
    assert engine.state.pwm==80
    engine.command('notes retry folder rename'); drain(engine)
    folder=trial_directory(engine.recorder.path,identifier)
    assert folder.name.startswith('Tai_') and not original_folder.exists()
    engine.shutdown()
    events=(engine.recorder.path/'session/events.jsonl').read_text(encoding='utf-8')
    assert 'trial_folder_rename_deferred' in events and (folder/'summary.json').is_file()


def test_hardware_folder_time_uses_mcu_to_host_clock_mapping(tmp_path):
    clock=FakeClock(); recorder=Recorder(tmp_path/'hardware',Config(),clock,mode='HARDWARE')
    identifier=str(uuid.uuid4())
    trial={'trial_id':identifier,'index':1,'name':'Tai','status':'ABORTED',
           'started_mono_s':3605,'finished_mono_s':3605,'notes':None,
           'intervals':[{'phase':'BASELINE','segment_id':1,'start_mono_s':3605,'end_mono_s':3605}]}
    try:
        recorder.submit('session_metadata',{'clock_mapping':{'offset_s':3600}})
        recorder.submit('trial',{'trial':trial,'finalize':True})
    finally:
        assert recorder.close()
    folder=trial_directory(recorder.path,identifier)
    assert folder.name.startswith('Tai_090005_2026-11-06_')


def test_transport_fault_finalize_does_not_mix_host_uptime_and_mcu_boot_time(tmp_path):
    clock=FakeClock(); recorder=Recorder(tmp_path/'hardware',Config(),clock,mode='HARDWARE')
    identifier=str(uuid.uuid4())
    trial={'trial_id':identifier,'index':1,'name':None,'status':'ACTIVE',
           'started_mono_s':3600,'finished_mono_s':None,'notes':None,
           'intervals':[{'phase':'WAIT_RECOVERY','segment_id':1,'start_mono_s':3600,'end_mono_s':None}]}
    recorder.submit('session_metadata',{'clock_mapping':{'offset_s':3600}})
    recorder.submit('trial',{'trial':trial})
    clock.advance(4)
    recorder.fail('injected USB loss')
    recorder.close()
    metadata=json.loads((trial_directory(recorder.path,identifier)/'metadata.json').read_text(encoding='utf-8'))
    assert metadata['status']=='ERROR' and metadata['finished_mono_s']==3604
    assert metadata['intervals'][-1]['end_mono_s']==3604
    assert metadata['finished_time_source']=='host_shutdown_clock_estimate'


def historical(data, status='CLOSED', name='Tai'):
    session_id=str(uuid.uuid4()); trial_id=str(uuid.uuid4())
    session=data/'hardware'/'2026-11-06'/session_id
    (session/'session').mkdir(parents=True)
    trial=session/'trials'/trial_id; trial.mkdir(parents=True)
    metadata={'schema':SCHEMA,'mode':'HARDWARE','session_id':session_id,'status':status,
              'started_at':'2026-11-06T20:07:07+07:00'}
    (session/'session/metadata.json').write_text(json.dumps(metadata),encoding='utf-8')
    raw='timestamp,mono_s\n2026-11-06T20:35:30+07:00,1710\n'
    (session/'session/raw.csv').write_text(raw,encoding='utf-8')
    trial_meta={'schema':SCHEMA,'mode':'HARDWARE','session_id':session_id,'trial_id':trial_id,
                'name':name,'status':'COMPLETE','started_mono_s':1709,'index':1}
    (trial/'metadata.json').write_text(json.dumps(trial_meta,ensure_ascii=False),encoding='utf-8')
    (trial/'raw.csv').write_text(raw,encoding='utf-8')
    (trial/'summary.json').write_text('{"quality":"UNCONFIGURED"}',encoding='utf-8')
    return session,trial_id


def test_migration_renames_parent_and_child_preserves_every_byte_and_can_rollback(tmp_path):
    data=tmp_path/'data'; old,identifier=historical(data)
    before={p.relative_to(data).as_posix():digest(p) for p in old.rglob('*') if p.is_file()}
    plan=plan_layout(data)
    assert len(plan['operations'])==2
    report=apply_layout(plan,tmp_path/'journal.json')
    assert report['status']=='APPLIED' and report['all_file_contents_unchanged']
    new=resolve_session_path(old)
    assert new.name.startswith('Phien_200707_2026-11-06_')
    trial=trial_directory(new,identifier)
    assert trial.name.startswith('Tai_203529_2026-11-06_')
    assert find_samples(data,'Tai').matches[0].folder==trial
    for relative,expected in before.items():
        assert digest(data/translated(relative,plan['operations']))==expected
    assert not plan_layout(data)['operations']
    rollback_layout(tmp_path/'journal.json')
    assert old.is_dir()
    for relative,expected in before.items():
        assert digest(data/relative)==expected


def test_active_or_partial_dataset_is_not_moved(tmp_path):
    data=tmp_path/'data'; old,_=historical(data,status='PARTIAL')
    plan=plan_layout(data)
    assert not plan['operations'] and len(plan['skipped'])==1 and old.is_dir()
    data2=tmp_path/'data2'; old,_=historical(data2)
    plan=plan_layout(data2)
    with DatasetLease(data2/'hardware'):
        with pytest.raises(RuntimeError,match='in use'):
            apply_layout(plan,tmp_path/'journal.json')
    assert old.is_dir()


def test_migration_detects_changed_files_and_rolls_back_failed_rename(tmp_path,monkeypatch):
    import robonose_s3.layout_migration as migration
    data=tmp_path/'data'; old,identifier=historical(data)
    plan=plan_layout(data)
    raw=old/'session/raw.csv'; original=raw.read_bytes(); raw.write_bytes(original+b'changed')
    with pytest.raises(RuntimeError,match='changed since planning'):
        apply_layout(plan,tmp_path/'journal.json')
    raw.write_bytes(original)
    rename=migration.rename_directory
    calls=0
    def fail_parent(root,source,destination):
        nonlocal calls
        calls+=1
        if calls==2:
            raise PermissionError('injected Windows folder lock')
        return rename(root,source,destination)
    monkeypatch.setattr(migration,'rename_directory',fail_parent)
    with pytest.raises(PermissionError):
        apply_layout(plan,tmp_path/'journal.json')
    assert json.loads((tmp_path/'journal.json').read_text())['status']=='ROLLED_BACK'
    assert (old/'trials'/identifier/'raw.csv').is_file() and raw.read_bytes()==original


def test_migration_refuses_path_escape_and_existing_destination(tmp_path):
    from robonose_s3.layout_migration import checked_path
    with pytest.raises(ValueError,match='escapes'):
        checked_path(tmp_path,'../outside')
    data=tmp_path/'data'; old,_=historical(data)
    plan=plan_layout(data)
    (data/plan['operations'][0]['destination']).mkdir()
    with pytest.raises(FileExistsError):
        apply_layout(plan,tmp_path/'journal.json')
    assert old.is_dir()
