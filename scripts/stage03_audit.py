"""Read-only artifact/source audit, plus readiness/validation reports in runtime."""
from collections import Counter
import argparse
from datetime import datetime,timedelta,timezone
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from robonose_s3.schema import COLUMNS
from robonose_s3.storage_layout import resolve_session_path, trial_directory


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def rows(path):
    with path.open(encoding='utf-8',newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-results',type=Path,default=ROOT/'runtime/STAGE03_TEST_RESULTS.xml')
    args=parser.parse_args()
    paths=load(ROOT/'configs/paths.local.json')
    if Path(sys.executable).resolve()!=Path(paths['python_exe']).resolve():
        raise SystemExit('Use configured python_exe')
    firmware=ROOT/'firmware/RoboNose_Dataset_S3'; stage=ROOT/'runtime/stage03'
    profiles=[]
    for name in ('cdc_on','cdc_off'):
        profile=load(stage/f'profile_{name}.json')
        assert profile['exit_code']==0 and profile['build_result']=='LINK_PASS'
        assert profile['status']=='PROVISIONAL_COMPILE_ONLY' and not profile['upload']
        assert not any(arg in ('--port','--upload','-u') for arg in profile['command'])
        for file,expected in profile['firmware_source_sha256'].items():
            assert digest(firmware/file)==expected,file
        log=(stage/f'build_{name}.log').read_text(encoding='utf-8')
        flash=re.search(r'Sketch uses (\d+) bytes',log)
        ram=re.search(r'Global variables use (\d+) bytes',log)
        assert flash and ram
        artifacts=[]
        for file in sorted((stage/'artifacts'/name).iterdir()):
            if file.is_file():
                artifacts.append({'file':str(file.relative_to(ROOT)),'bytes':file.stat().st_size,'sha256':digest(file)})
        assert any(a['file'].endswith('.elf') for a in artifacts)
        assert any(a['file'].endswith('.bin') for a in artifacts)
        profiles.append({'profile':name,'status':profile['status'],'fqbn':profile['fqbn'],
                         'flash_program_bytes':int(flash.group(1)),'static_ram_bytes':int(ram.group(1)),
                         'elapsed_s':profile['elapsed_s'],'artifacts':artifacts})
    manifests=[]
    for base in (ROOT/'stage03_input',ROOT/'stage03_input/reference_s3/RoboNose_ControlTest_v2_1'):
        manifest=load(base/'SHA256SUMS.json')
        for file,expected in manifest.items():
            assert digest(base/file)==expected,file
        manifests.append({'path':str(base/'SHA256SUMS.json'),'entries_verified':len(manifest)})
    bosch=load(firmware/'BOSCH_UPSTREAM.json')
    for entry in bosch['files']:
        assert digest(firmware/entry['file'])==entry['sha256']
    fixture=load(stage/'EMULATED_FIXTURE.json'); folder=resolve_session_path(fixture['session_path'])
    fixture['session_path']=str(folder)
    raw=rows(folder/'session/raw.csv')
    assert list(raw[0])==COLUMNS and len(raw)==fixture['rows']
    assert all(r['mode']=='EMULATED' for r in raw)
    assert digest(folder/'session/raw.csv')==fixture['raw_sha256']
    assert digest(folder/'session/wire.jsonl')==fixture['wire_sha256']
    for entry in fixture['trials']:
        trial=trial_directory(folder,entry['trial_id'])
        assert rows(trial/'raw.csv')==[r for r in raw if r['trial_id']==entry['trial_id']]
        summary=load(trial/'summary.json'); assert summary['raw_sha256']==digest(trial/'raw.csv')
        assert summary['mode']=='EMULATED' and summary['process_status']=='COMPLETE'
    metadata=load(folder/'session/metadata.json')
    assert metadata['status']=='CLOSED' and metadata['shutdown_off_acknowledged']
    old=load(ROOT/'runtime/STAGE02_VALIDATION.json')
    assert digest(resolve_session_path(old['session_path'])/'session/raw.csv')==old['session_raw_sha256']
    suite=ET.parse(args.test_results).getroot().find('testsuite')
    assert int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    stage02_modules={'test_state','test_quality','test_dataset','test_integration'}
    stage02_cases=[case for case in suite.findall('testcase')
                   if case.attrib.get('classname','').split('.')[-1] in stage02_modules]
    assert len(stage02_cases)==47 and all(case.find('failure') is None and case.find('error') is None
                                         and case.find('skipped') is None for case in stage02_cases)
    cpp=load(stage/'CPP_TEST_RESULTS.json'); assert cpp['all_commands_succeeded']
    date=datetime.now(timezone(timedelta(hours=7))).isoformat()
    readiness={'generated_at':date,'status':'NEEDS_INPUT_FOR_UPLOAD_AND_HARDWARE_VALIDATION',
        'board':paths['board'],'board_identified':False,'physical_com_opened_in_stage03':False,
        'uploaded':False,'physical_sensor_or_output_tested':False,
        'evidence':{'cli_board_details':'runtime/stage03/board-details.json',
                    'reference_role':'historical ControlTest, not actual board identification',
                    'last_port_inventory':'runtime/environment_report.json: COM3 Intel SOL, not confirmed ESP',
                    'actual_board_tools_configuration':None},
        'provisional_profiles':profiles,'core':'3.3.12','arduino_cli':'1.5.1',
        'needs_input':['physical board/module model or photo','previous successful Tools/FQBN/options',
                       'actual flash and PSRAM','native USB versus USB-UART connector/COM',
                       'hardware wiring/output polarity and boot OFF validation'],
        'pi_source_status':'NEEDS_INPUT','native_gui_status':'NOT_EXECUTED','cpp_execution_status':cpp['status']}
    assert all(value is None for value in readiness['board'].values())
    (ROOT/'runtime/STAGE03_BOARD_READINESS.json').write_text(json.dumps(readiness,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    report={'generated_at':date,'status':'PASS_SOFTWARE_AND_PROVISIONAL_LINK_ONLY','test_suite':suite.attrib,
        'profiles':profiles,'reference_manifests':manifests,'bosch_files_verified':len(bosch['files']),
        'cpp_status':cpp['status'],'cpp_executed':cpp['cpp_executed'],
        'emulated_fixture':fixture,'phase_counts':dict(Counter(row['phase'] for row in raw)),
        'stage02_raw_unchanged':True,'schema_header_preserved':True,
        'stage02_tests_passed':len(stage02_cases),
        'host_source_sha256':{file.name:digest(file) for file in sorted((ROOT/'robonose_s3').glob('*.py'))},
        'native_gui_validation':'NOT_EXECUTED','hardware_validation':'NOT_EXECUTED'}
    (stage/'VALIDATION.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'tests':suite.attrib,
        'profiles':[{k:v for k,v in p.items() if k!='artifacts'} for p in profiles],
        'emulated_rows':len(raw),'cpp_execution':cpp['cpp_executed'],'reference_unchanged':True},indent=2))


if __name__=='__main__':
    main()
