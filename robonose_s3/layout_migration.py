"""Offline, journaled folder renames. Dataset file contents remain byte-identical."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

from .recorder import write_json
from .schema import SCHEMA
from .storage_layout import (DatasetLease, available_folder, first_raw_anchor,
                             historical_trial_start)

BACKENDS = ('hardware', 'simulation', 'emulation')


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def checked_path(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root) or path.resolve() == root:
        raise ValueError(f'Migration path escapes dataset root: {path}')
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f'Migration refuses symbolic links: {parent}')
    return path


def translated(relative, operations):
    path = Path(relative)
    for operation in operations:
        source = Path(operation['source'])
        if path.is_relative_to(source):
            path = Path(operation['destination']) / path.relative_to(source)
    return path.as_posix()


def plan_layout(data_root):
    root = Path(data_root).resolve()
    operations, files, sessions, skipped = [], {}, [], []
    for backend in BACKENDS:
        for metadata_path in sorted((root / backend).glob('*/*/session/metadata.json')):
            session = metadata_path.parent.parent
            checked_path(root, session.relative_to(root))
            metadata = json.loads(metadata_path.read_text(encoding='utf-8-sig'))
            if metadata.get('schema') != SCHEMA or metadata.get('status') not in ('CLOSED', 'ERROR'):
                skipped.append({'folder': str(session), 'reason': 'Not a closed/error v1 session; kept unchanged'})
                continue
            destination = available_folder(session.parent, 'Phien', metadata['started_at'],
                                           metadata['session_id'], current=session,
                                           reserved=[Path(op['destination']).name for op in operations])
            anchor = first_raw_anchor(session / 'session/raw.csv')
            trials = []
            for trial_meta in sorted((session / 'trials').glob('*/metadata.json')):
                trial = json.loads(trial_meta.read_text(encoding='utf-8-sig'))
                if trial.get('schema') != SCHEMA or trial.get('session_id') != metadata['session_id']:
                    raise ValueError(f'Trial identity/schema mismatch: {trial_meta}')
                started_at = historical_trial_start(trial, metadata, anchor)
                target = available_folder(trial_meta.parent.parent, trial.get('name'), started_at,
                                          trial['trial_id'], current=trial_meta.parent,
                                          reserved=[Path(op['destination']).name for op in operations])
                trials.append({'trial_id': trial['trial_id'], 'name': trial.get('name'),
                               'started_at': started_at, 'folder': target.name})
                if target != trial_meta.parent:
                    operations.append({'source': trial_meta.parent.relative_to(root).as_posix(),
                                       'destination': target.relative_to(root).as_posix()})
            if destination != session:
                operations.append({'source': session.relative_to(root).as_posix(),
                                   'destination': destination.relative_to(root).as_posix()})
            for path in session.rglob('*'):
                if path.is_symlink():
                    raise ValueError(f'Migration refuses symbolic links: {path}')
                if path.is_file():
                    files[path.relative_to(root).as_posix()] = digest(path)
            sessions.append({'session_id': metadata['session_id'], 'backend': backend,
                             'source': session.relative_to(root).as_posix(),
                             'destination': destination.relative_to(root).as_posix(), 'trials': trials})
    for operation in operations:
        checked_path(root, operation['source'])
        target = checked_path(root, operation['destination'])
        if target.exists():
            raise FileExistsError(target)
    return {'status': 'PLANNED', 'data_root': str(root), 'layout_version': 2,
            'operations': operations, 'sessions': sessions, 'skipped': skipped,
            'file_sha256_before': files, 'completed_operations': 0}


def rename_directory(root, source, destination):
    source, destination = checked_path(root, source), checked_path(root, destination)
    if destination.exists():
        raise FileExistsError(destination)
    source.rename(destination)


def apply_layout(plan, journal):
    root = Path(plan['data_root']).resolve()
    journal = Path(journal)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for backend in sorted({session['backend'] for session in plan['sessions']}):
            stack.enter_context(DatasetLease(root / backend))
        for relative, expected in plan['file_sha256_before'].items():
            if digest(checked_path(root, relative)) != expected:
                raise RuntimeError(f'Dataset changed since planning: {relative}')
        for operation in plan['operations']:
            if checked_path(root, operation['destination']).exists():
                raise FileExistsError(operation['destination'])
        plan.update(status='APPLYING', completed_operations=0)
        write_json(journal, plan)
        try:
            for operation in plan['operations']:
                rename_directory(root, operation['source'], operation['destination'])
                plan['completed_operations'] += 1
                write_json(journal, plan)
            for relative, expected in plan['file_sha256_before'].items():
                final = translated(relative, plan['operations'])
                if digest(checked_path(root, final)) != expected:
                    raise RuntimeError(f'Dataset changed during migration: {final}')
        except Exception as error:
            completed = plan['operations'][:plan['completed_operations']]
            try:
                for operation in reversed(completed):
                    rename_directory(root, operation['destination'], operation['source'])
            except Exception as rollback_error:
                plan.update(status='ROLLBACK_REQUIRED', error=str(error), rollback_error=str(rollback_error))
            else:
                plan.update(status='ROLLED_BACK', error=str(error), completed_operations=0)
            write_json(journal, plan)
            raise
        plan.update(status='APPLIED', all_file_contents_unchanged=True,
                    files_verified=len(plan['file_sha256_before']),
                    path_map={op['source']: translated(op['source'], plan['operations']) for op in plan['operations']})
        write_json(journal, plan)
    return plan


def rollback_layout(journal):
    """Reverse a completed migration only while every archived file is unchanged."""
    journal = Path(journal)
    plan = json.loads(journal.read_text(encoding='utf-8'))
    if plan['status'] != 'APPLIED':
        raise ValueError('Rollback requires a successfully applied migration journal')
    root = Path(plan['data_root']).resolve()
    with ExitStack() as stack:
        for backend in sorted({session['backend'] for session in plan['sessions']}):
            stack.enter_context(DatasetLease(root / backend))
        for relative, expected in plan['file_sha256_before'].items():
            final = translated(relative, plan['operations'])
            if digest(checked_path(root, final)) != expected:
                raise RuntimeError(f'Refusing rollback of changed data: {final}')
        for operation in reversed(plan['operations']):
            rename_directory(root, operation['destination'], operation['source'])
        plan.update(status='ROLLED_BACK', completed_operations=0)
        write_json(journal, plan)
    return plan
