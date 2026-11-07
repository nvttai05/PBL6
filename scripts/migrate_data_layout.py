"""Plan/apply readable dataset folder names offline, with checksums and a journal."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robonose_s3.layout_migration import apply_layout, plan_layout, rollback_layout
from robonose_s3.recorder import write_json


def main():
    paths = json.loads((ROOT / 'configs/paths.local.json').read_text(encoding='utf-8'))
    if Path(sys.executable).resolve() != Path(paths['python_exe']).resolve():
        raise SystemExit('Use configured python_exe')
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true')
    action.add_argument('--rollback', metavar='JOURNAL')
    args = parser.parse_args()
    if args.rollback:
        report = rollback_layout(args.rollback)
    else:
        report = plan_layout(ROOT / 'data')
        if args.apply and report['operations']:
            journal = ROOT / 'runtime/DATA_LAYOUT_MIGRATION.json'
            if journal.exists():
                previous = json.loads(journal.read_text(encoding='utf-8'))
                if previous.get('status') == 'APPLIED':
                    backup = journal.with_name('DATA_LAYOUT_MIGRATION_' + str(journal.stat().st_mtime_ns) + '.json')
                    backup.write_bytes(journal.read_bytes())
            report = apply_layout(report, journal)
        else:
            write_json(ROOT / 'runtime/DATA_LAYOUT_PLAN.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'data_root', 'skipped')}, ensure_ascii=False, indent=2))
    print(f"Sessions: {len(report['sessions'])}; renames: {len(report['operations'])}; files: {len(report['file_sha256_before'])}")
    for session in report['sessions']:
        print(session['destination'])
        for trial in session['trials']:
            print('  trials/' + trial['folder'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
