import shutil
import subprocess
from pathlib import Path
import pytest
from robonose_s3.config import Config
from robonose_s3.state import StateMachine

ROOT=Path(__file__).resolve().parents[1]


def test_shared_phase_fixture_matches_python_reference_model():
    model=StateMachine(Config())
    fixture=ROOT/'fixtures/stage03_phases.tsv'
    count=0
    for row in fixture.read_text(encoding='utf-8').splitlines():
        at,verb,arg,phase,pwm,valve=row.split(); now=int(at)/1000
        if verb=='BEGIN':
            model.start_session(now)
        elif verb=='OFF':
            model.stop(now)
        elif verb in ('TICK','PING'):
            model.advance(now)
        elif verb=='START':
            assert model.command('start',now)['accepted']; model.trial.trial_id=arg
        elif verb=='EXTEND':
            assert model.command(f'extend {int(arg)/1000}',now)['accepted']
        else:
            assert model.command(verb.lower(),now)['accepted']
        assert (model.phase,model.pwm,int(model.route=='SAMPLE'))==(phase,int(pwm),int(valve))
        model.drain_events(); count+=1
    assert count==116 and model.pump_start_count==1


@pytest.mark.skipif(not (shutil.which('g++') or shutil.which('clang++')),reason='No native C++ compiler; Xtensa mock object compilation is reported separately, not execution')
def test_cpp_native_phase_parity_and_driver_mocks(tmp_path):
    compiler=shutil.which('g++') or shutil.which('clang++')
    firmware=ROOT/'firmware/RoboNose_Dataset_S3'; stubs=ROOT/'tests/firmware_stubs'
    for name,sources in [('engine',[firmware/'trial_engine.cpp',stubs/'test_engine.cpp']),
                         ('drivers',[firmware/'ads1115_reader.cpp',firmware/'output_hardware.cpp',stubs/'test_drivers.cpp']),
                         ('timing',[stubs/'test_timing.cpp']),
                         ('transport',[firmware/'serial_transport.cpp',stubs/'test_transport.cpp']),
                         ('framed_tx',[stubs/'test_framed_tx.cpp'])]:
        executable=tmp_path/(name+'.exe')
        flags=['-DARDUINO_USB_CDC_ON_BOOT=1','-DARDUINO_USB_MODE=1'] if name=='transport' else []
        subprocess.run([compiler,'-std=c++17',*flags,'-I',str(stubs),'-I',str(firmware),*[str(s) for s in sources],'-o',str(executable)],check=True,capture_output=True)
        command=[str(executable),str(ROOT/'fixtures/stage03_phases.tsv')] if name=='engine' else [str(executable)]
        subprocess.run(command,check=True,capture_output=True)
