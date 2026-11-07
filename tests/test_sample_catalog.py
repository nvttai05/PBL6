import builtins
import csv
import hashlib
import io
import json
from pathlib import Path
import uuid
import pytest

from robonose_s3.sample_catalog import find_samples, format_results
from robonose_s3.schema import SCHEMA


def record(data_root,index,name='Tai',mode='hardware',timestamp=None,notes=None):
    trial_id=str(uuid.uuid4())
    folder=data_root/mode/'2026-11-06'/'session-one'/'trials'/trial_id
    folder.mkdir(parents=True)
    metadata={'schema':SCHEMA,'mode':{'hardware':'HARDWARE','simulation':'SIMULATED'}[mode],
              'session_id':'session-one','trial_id':trial_id,'name':name,'index':index,
              'status':'COMPLETE','notes':notes,'export_finalized':True}
    (folder/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf-8')
    with (folder/'raw.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,['timestamp','mono_s'])
        writer.writeheader()
        if timestamp:
            writer.writerow({'timestamp':timestamp,'mono_s':index})
    return folder


def test_three_same_names_return_separate_ordered_uuids_and_paths_without_changes(tmp_path):
    data=tmp_path/'data'
    folders=[record(data,index,timestamp=f'2026-11-06T20:{30+index}:00+07:00',notes=f'lượt {index}') for index in (3,1,2)]
    before={path:hashlib.sha256(path.read_bytes()).hexdigest() for folder in folders for path in folder.iterdir()}
    result=find_samples(data,'tai')
    assert len(result.matches)==3 and not result.warnings
    assert [match.index for match in result.matches]==[1,2,3]
    assert len({match.trial_id for match in result.matches})==3
    assert {match.folder for match in result.matches}==set(folders)
    text=format_results('Tai',result)
    for match in result.matches:
        assert match.trial_id in text and str(match.folder) in text and match.notes in text
    assert before=={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in before}


def test_unicode_exact_names_and_modes_remain_distinct(tmp_path):
    record(tmp_path,1,name='Tài',mode='hardware')
    record(tmp_path,2,name='Ta\u0300i',mode='simulation')
    record(tmp_path,3,name='Tai')
    result=find_samples(tmp_path,' TÀI ')
    assert {match.mode for match in result.matches}=={'HARDWARE','SIMULATED'}
    assert len(result.matches)==2
    assert len(find_samples(tmp_path,'Tai').matches)==1


def test_corrupt_metadata_and_missing_measurement_do_not_hide_good_results(tmp_path):
    folder=record(tmp_path,1)
    bad=record(tmp_path,2)
    (bad/'metadata.json').write_text('{bad json',encoding='utf-8')
    result=find_samples(tmp_path,'Tai')
    assert len(result.matches)==1 and result.matches[0].first_sample_at is None
    assert result.matches[0].folder==folder and len(result.warnings)==1
    assert not find_samples(tmp_path/'missing','Tai').matches
    with pytest.raises(ValueError):
        find_samples(tmp_path,'  ')


def test_cli_lookup_returns_before_qt_or_serial_import(tmp_path,monkeypatch,capsys):
    import robonose_s3.sample_catalog as catalog
    from robonose_s3.__main__ import main
    folder=record(tmp_path,1,timestamp='2026-11-06T13:35:30+00:00')
    original_find=catalog.find_samples
    monkeypatch.setattr(catalog,'find_samples',lambda root,name:original_find(tmp_path,name))
    original_import=builtins.__import__
    def guard(name,*args,**kwargs):
        if name.startswith(('PySide6','pyqtgraph','serial')):
            raise AssertionError('Read-only lookup tried to load GUI/COM')
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guard)
    assert main(['--find-sample','Tai'])==0
    output=capsys.readouterr().out
    assert str(folder) in output and '20:35:30' in output


def test_lookup_cannot_select_hardware_backend_at_the_same_time():
    from robonose_s3.__main__ import main
    with pytest.raises(SystemExit) as stopped:
        main(['--find-sample','Tai','--port','COM_UNVERIFIED'])
    assert stopped.value.code==2


def test_lookup_prints_vietnamese_on_windows_redirected_stream(tmp_path,monkeypatch):
    import sys
    import robonose_s3.sample_catalog as catalog
    from robonose_s3.__main__ import main
    folder=record(tmp_path,1,name='Tài')
    original_find=catalog.find_samples
    monkeypatch.setattr(catalog,'find_samples',lambda root,name:original_find(tmp_path,name))
    output=io.BytesIO()
    stdout=io.TextIOWrapper(output,encoding='cp1252')
    monkeypatch.setattr(sys,'stdout',stdout)
    assert main(['--find-sample','Tài'])==0
    stdout.flush()
    text=output.getvalue().decode('utf-8')
    assert 'Tài' in text and str(folder) in text
