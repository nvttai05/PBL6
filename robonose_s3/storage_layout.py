"""Human-readable folders; immutable UUIDs remain the dataset identity."""
import csv
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import unicodedata
import uuid

from .clock import LOCAL_TZ

LAYOUT_VERSION = 2


def safe_label(name):
    label = unicodedata.normalize('NFC', name or 'Chua_dat_ten').strip()
    label = ''.join(c if c.isalnum() or unicodedata.category(c).startswith('M') or c in '-_' else '_' for c in label)
    label = re.sub('_+', '_', label).strip('_')[:32].rstrip('_') or 'Chua_dat_ten'
    if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]', label, re.IGNORECASE):
        label = 'Mau_' + label
    return label


def local_time(timestamp):
    value = datetime.fromisoformat(timestamp)
    if value.tzinfo is None:
        raise ValueError('Dataset folder time requires an explicit timezone')
    return value.astimezone(LOCAL_TZ)


def readable_folder(label, timestamp, identifier, id_length=12):
    # Full identity is always kept in raw/metadata; shortening only affects paths.
    identity = uuid.UUID(str(identifier)).hex
    stamp = local_time(timestamp).strftime('%H%M%S_%Y-%m-%d') if timestamp else 'Gio_khong_ro_Ngay_khong_ro'
    return f'{safe_label(label)}_{stamp}_{identity[:id_length]}'


def available_folder(parent, label, timestamp, identifier, current=None, reserved=()):
    parent = Path(parent)
    taken = {str(name).casefold() for name in reserved}
    for length in (12, 20, 32):
        candidate = parent / readable_folder(label, timestamp, identifier, length)
        if current is not None and candidate == Path(current):
            return candidate
        if candidate.name.casefold() not in taken and not candidate.exists():
            return candidate
    raise FileExistsError(f'Cannot allocate a unique dataset folder for {identifier}')


def folder_matches_id(folder_name, identifier):
    try:
        identity = uuid.UUID(str(identifier))
    except (ValueError, TypeError, AttributeError):
        return False
    return folder_name == str(identity) or any(folder_name.endswith('_' + identity.hex[:n]) for n in (12, 20, 32))


def trial_directory(session, trial_id):
    """Resolve both legacy UUID folders and layout v2 folders without guessing names."""
    parent = Path(session) / 'trials'
    legacy = parent / str(uuid.UUID(str(trial_id)))
    if legacy.is_dir():
        return legacy
    for metadata in parent.glob('*/metadata.json'):
        if not folder_matches_id(metadata.parent.name, trial_id):
            continue
        if json.loads(metadata.read_text(encoding='utf-8-sig')).get('trial_id') == trial_id:
            return metadata.parent
    raise FileNotFoundError(f'Trial {trial_id} not found in {parent}')


def resolve_session_path(path):
    """Keep historical fixture manifests usable after a session folder is renamed."""
    path = Path(path)
    if path.is_dir():
        return path
    for metadata in path.parent.glob('*/session/metadata.json'):
        value = json.loads(metadata.read_text(encoding='utf-8-sig'))
        if value.get('session_id') == path.name:
            return metadata.parent.parent
    raise FileNotFoundError(path)


def first_raw_anchor(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        row = next(csv.DictReader(handle), None)
    if not row:
        return None
    return local_time(row['timestamp']), float(row['mono_s'])


def historical_trial_start(trial, session, anchor=None):
    if trial.get('started_at'):
        return local_time(trial['started_at']).isoformat()
    if anchor is not None and trial.get('started_mono_s') is not None:
        stamp, mono = anchor
        return (stamp + timedelta(seconds=trial['started_mono_s'] - mono)).isoformat()
    # Never invent a start time for an incomplete historical record.
    return None


class DatasetLease:
    """Exclude maintenance while the backend's writer is active; never open COM."""
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.handle = (root / '.writer.lock').open('a+b')
        try:
            if self.handle.tell() == 0:
                self.handle.write(b'0')
                self.handle.flush()
            self.handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            raise RuntimeError(f'Dataset is in use: {root}; close collection before migration') from error

    def close(self):
        if not self.handle.closed:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
