"""Compile/link provisional ESP32-S3 profiles, never upload or select a port."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile",choices=["cdc_on","cdc_off"],required=True)
    args=parser.parse_args()
    paths=json.loads((ROOT/'configs/paths.local.json').read_text(encoding='utf-8'))
    if Path(sys.executable).resolve()!=Path(paths['python_exe']).resolve():
        parser.error('Use python_exe from paths.local.json')
    cli=paths['arduino_cli_exe']
    details=json.loads((ROOT/'runtime/stage03/board-details.json').read_text(encoding='utf-8-sig'))
    assert details['fqbn']=='esp32:esp32:esp32s3' and details['version']=='3.3.12'
    options={'CDCOnBoot':'cdc' if args.profile=='cdc_on' else 'default','USBMode':'hwcdc',
             'FlashSize':'4M','PSRAM':'disabled','PartitionScheme':'default'}
    available={item['option']:{v['value'] for v in item['values']} for item in details['config_options']}
    assert all(value in available[key] for key,value in options.items())
    fqbn=details['fqbn']+':'+','.join(f'{key}={value}' for key,value in options.items())
    build=ROOT/'runtime/stage03'/f'build_{args.profile}'
    output=ROOT/'runtime/stage03/artifacts'/args.profile
    log=ROOT/'runtime/stage03'/f'build_{args.profile}.log'
    command=[cli,'compile','--fqbn',fqbn,'--jobs','2','--build-path',str(build),
             '--output-dir',str(output),str(ROOT/'firmware/RoboNose_Dataset_S3')]
    profile={'status':'PROVISIONAL_COMPILE_ONLY','board_identified':False,'core':'3.3.12',
             'fqbn':fqbn,'options':options,'command':command,'log':str(log),'upload':False}
    profile['firmware_source_sha256']={str(p.relative_to(ROOT/'firmware/RoboNose_Dataset_S3')):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'firmware/RoboNose_Dataset_S3').iterdir()) if p.is_file()}
    (ROOT/'runtime/stage03'/f'profile_{args.profile}.json').write_text(json.dumps(profile,indent=2)+'\n',encoding='utf-8')
    started=time.monotonic()
    with log.open('w',encoding='utf-8') as handle:
        handle.write('PROVISIONAL_COMPILE_ONLY; board UNKNOWN; no port/upload\n')
        handle.flush()
        result=subprocess.run(command,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
    profile.update(exit_code=result.returncode,elapsed_s=round(time.monotonic()-started,3),
                   build_result='LINK_PASS' if result.returncode==0 else 'FAIL')
    (ROOT/'runtime/stage03'/f'profile_{args.profile}.json').write_text(json.dumps(profile,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(profile,indent=2))
    print('\n'.join(log.read_text(encoding='utf-8').splitlines()[-18:]))
    return result.returncode


if __name__=='__main__':
    raise SystemExit(main())
