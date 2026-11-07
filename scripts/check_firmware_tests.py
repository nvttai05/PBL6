"""Run native C++ tests when available; otherwise cross-compile without claiming execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    paths=json.loads((ROOT/'configs/paths.local.json').read_text(encoding='utf-8'))
    if Path(sys.executable).resolve()!=Path(paths['python_exe']).resolve():
        raise SystemExit('Use python_exe from configs/paths.local.json')
    firmware=ROOT/'firmware/RoboNose_Dataset_S3'; stub=ROOT/'tests/firmware_stubs'
    native=shutil.which('g++') or shutil.which('clang++')
    cross_root=Path(os.environ['LOCALAPPDATA'])/'Arduino15/packages/esp32/tools/esp-x32'
    cross=next(cross_root.glob('*/bin/xtensa-esp32s3-elf-g++.exe'),None)
    if not native and cross is None:
        raise SystemExit('No native or installed Xtensa C++ compiler found')
    compiler=native or str(cross)
    output=ROOT/'runtime/stage03/cpp_tests'; output.mkdir(parents=True,exist_ok=True)
    sources=[firmware/'trial_engine.cpp',firmware/'ads1115_reader.cpp',firmware/'output_hardware.cpp',
             firmware/'serial_transport.cpp',stub/'test_engine.cpp',stub/'test_drivers.cpp',
             stub/'test_timing.cpp',stub/'test_transport.cpp',stub/'test_framed_tx.cpp']
    commands=[]
    for source in sources:
        flags=['-DARDUINO_USB_CDC_ON_BOOT=1','-DARDUINO_USB_MODE=1'] if source.stem in ('serial_transport','test_transport') else []
        command=[compiler,'-std=c++17','-Wall','-Wextra',*flags,'-I',str(stub),'-I',str(firmware),'-c',str(source),'-o',str(output/(source.stem+'.o'))]
        result=subprocess.run(command,capture_output=True,text=True)
        commands.append({'argv':command,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        if result.returncode:
            print(result.stderr); break
    status='COMPILE_ONLY'
    if native and all(c['exit_code']==0 for c in commands):
        for name,objects in [('test_engine',['trial_engine','test_engine']),('test_drivers',['ads1115_reader','output_hardware','test_drivers']),
                             ('test_timing',['test_timing']),('test_transport',['serial_transport','test_transport']),('test_framed_tx',['test_framed_tx'])]:
            executable=output/(name+'.exe' if os.name=='nt' else name)
            subprocess.run([native,*[str(output/(item+'.o')) for item in objects],'-o',str(executable)],check=True)
            command=[str(executable),str(ROOT/'fixtures/stage03_phases.tsv')] if name=='test_engine' else [str(executable)]
            result=subprocess.run(command,capture_output=True,text=True)
            commands.append({'argv':command,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        status='NATIVE_EXECUTED'
    version=subprocess.run([compiler,'--version'],capture_output=True,text=True).stdout.splitlines()[0]
    report={'status':status,'native_compiler':native,'compiler':compiler,'compiler_version':version,
            'all_commands_succeeded':all(c['exit_code']==0 for c in commands),'commands':commands,
            'hardware_tested':False,'cpp_executed':bool(native)}
    (ROOT/'runtime/stage03/CPP_TEST_RESULTS.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='commands'},indent=2))
    return 0 if report['all_commands_succeeded'] else 1


if __name__=='__main__':
    raise SystemExit(main())
