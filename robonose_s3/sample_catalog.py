"""Read-only lookup of named trials; no Qt, device, recorder or serial imports."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import csv
import json
from pathlib import Path
import unicodedata

from .schema import SCHEMA
from .storage_layout import folder_matches_id

MODE_DIRS={'hardware':'HARDWARE','simulation':'SIMULATED','emulation':'EMULATED'}
LOCAL_TZ=timezone(timedelta(hours=7))


@dataclass(frozen=True)
class SampleMatch:
    name: str
    mode: str
    index: int | None
    trial_id: str
    session_id: str
    status: str
    first_sample_at: str | None
    notes: str | None
    folder: Path
    export_finalized: bool


@dataclass(frozen=True)
class SearchResult:
    matches: tuple[SampleMatch,...]
    warnings: tuple[str,...]


def normalized_name(name):
    return unicodedata.normalize('NFC',name.strip()).casefold()


def single_line(value):
    return ''.join(char if char.isprintable() else ' ' for char in str(value))


def first_sample_time(raw_path):
    if not raw_path.is_file():
        return None
    with raw_path.open(encoding='utf-8-sig',newline='') as handle:
        first=next(csv.DictReader(handle),None)
    if not first or not first.get('timestamp'):
        return None
    timestamp=datetime.fromisoformat(first['timestamp'])
    if timestamp.tzinfo is None:
        return None  # Do not invent a timezone for historical/partial records.
    return timestamp.astimezone(LOCAL_TZ).isoformat()


def find_samples(data_root,name):
    query=normalized_name(name)
    if not query:
        raise ValueError('Tên mẫu không được để trống')
    matches=[]; warnings=[]
    for directory,expected_mode in MODE_DIRS.items():
        for path in (Path(data_root)/directory).glob('*/*/trials/*/metadata.json'):
            try:
                metadata=json.loads(path.read_text(encoding='utf-8-sig'))
                if not isinstance(metadata,dict):
                    raise ValueError('metadata phải là JSON object')
                sample_name=metadata.get('name')
                if not isinstance(sample_name,str) or normalized_name(sample_name)!=query:
                    continue
                if metadata.get('schema')!=SCHEMA:
                    raise ValueError('schema chưa được hỗ trợ')
                if not folder_matches_id(path.parent.name, metadata.get('trial_id')):
                    raise ValueError('trial UUID không khớp thư mục')
                mode=metadata.get('mode','UNKNOWN')
                if mode!=expected_mode:
                    warnings.append(f'{path}: mode metadata {mode!r} khác thư mục {expected_mode}')
                first=None
                try:
                    first=first_sample_time(path.parent/'raw.csv')
                except (OSError,ValueError,UnicodeError,csv.Error) as error:
                    warnings.append(f'{path.parent / "raw.csv"}: {error}')
                index=metadata.get('index')
                matches.append(SampleMatch(name=sample_name,mode=str(mode),
                    index=index if type(index) is int else None,trial_id=metadata['trial_id'],
                    session_id=str(metadata.get('session_id',path.parents[2].name)),
                    status=str(metadata.get('status','UNKNOWN')),first_sample_at=first,
                    notes=metadata.get('notes') if isinstance(metadata.get('notes'),str) else None,
                    folder=path.parent.resolve(),export_finalized=metadata.get('export_finalized') is True))
            except (OSError,ValueError,UnicodeError) as error:
                warnings.append(f'{path}: {error}')
    matches.sort(key=lambda match:(match.first_sample_at or '',match.session_id,match.index or 0,match.trial_id))
    return SearchResult(tuple(matches),tuple(warnings))


def format_results(name,result):
    if not result.matches:
        return f'Không tìm thấy lượt nào tên "{single_line(name)}" trong data/hardware, data/simulation hoặc data/emulation.'
    lines=[f'Tìm thấy {len(result.matches)} lượt tên "{single_line(name)}".',
           'Tên trùng được phân biệt bằng phiên, số lượt, thời điểm và UUID; dữ liệu không gộp/ghi đè.',
           'Mẫu đầu (+07)        | Loại       | Lượt | Trạng thái | Trial UUID']
    for number,match in enumerate(result.matches,1):
        timestamp=match.first_sample_at[:19].replace('T',' ') if match.first_sample_at else 'Chưa có mẫu/giờ'
        lines.append(f'{timestamp:<19} | {single_line(match.mode):<10} | {str(match.index or "?"):<4} | {single_line(match.status):<10} | {match.trial_id}')
        lines.append(f'  [{number}] Thư mục: {match.folder}')
        lines.append(f'      Phiên: {match.session_id}; export: {"đã chốt" if match.export_finalized else "chưa chốt"}')
        files=[name for name in ('raw.csv','metadata.json','summary.json') if (match.folder/name).is_file()]
        lines.append('      File: '+', '.join(files))
        if match.notes:
            lines.append(f'      Notes: {single_line(match.notes)}')
    lines.append('COMPLETE là đủ quy trình; chất lượng xem trong summary.json. Lookup chỉ đọc file, không mở COM.')
    return '\n'.join(lines)
