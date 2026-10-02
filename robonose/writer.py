import csv
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import platform
import sys
import time
import uuid
from . import __version__
from .schema import FIELDS, TZ, iso_now

EVENT_FIELDS = ["run_id", "timestamp", "elapsed_s", "phase_elapsed_s", "phase", "event", "details_json"]

def atomic_json(path, obj):
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def safe_name(name):
    # Keep Vietnamese letters; eliminate separators, controls, dot traversals.
    clean = re.sub(r"[^\w-]+", "_", name, flags=re.UNICODE).strip("_-")[:80]
    return clean.encode("utf-8")[:160].decode("utf-8", errors="ignore") or "run"

class RunWriter:
    def __init__(self, output, backend, cfg, applied, sample_info=None, run_start=None, kind="collect"):
        self.start = time.monotonic() if run_start is None else run_start
        self.run_id = uuid.uuid4().hex
        now = datetime.now(TZ)
        parent = Path(output).resolve() / ("simulation" if backend == "sim" else "exploration") / now.strftime("%Y-%m-%d")
        parent.mkdir(parents=True, exist_ok=True)
        self.path = parent / f"{now:%Y%m%d_%H%M%S}_{self.run_id}"
        self.path.mkdir(exist_ok=False)
        self.base_name = self.path.name
        self.seq, self.last_sync = 0, self.start
        self.fsync_interval = cfg["fsync_interval_s"]
        self.closed = False
        self.raw_file = (self.path / "raw.csv").open("x", encoding="utf-8", newline="")
        self.event_file = (self.path / "events.csv").open("x", encoding="utf-8", newline="")
        self.raw = csv.DictWriter(self.raw_file, fieldnames=FIELDS, extrasaction="raise")
        self.events = csv.DictWriter(self.event_file, fieldnames=EVENT_FIELDS)
        self.raw.writeheader()
        self.events.writeheader()
        self.meta = {"schema_version": "1.0", "program_version": __version__, "run_id": self.run_id,
            "backend": backend, "kind": kind, "started_at": iso_now(), "ended_at": None,
            "status": "PARTIAL", "config": cfg, "applied": applied,
            "sample": sample_info or {}, "original_name": None, "notes": "",
            "phase_intervals": [], "extensions": [], "rows": 0,
            "time_basis": "elapsed_s = monotonic - run_start; ISO Asia/Ho_Chi_Minh",
            "pump_feedback": "command only; no physical feedback"}
        from .readers import package_version
        self.meta["software"] = {"python": sys.version, "platform": platform.platform(),
            "dependencies": {k: package_version(k) for k in ("numpy", "matplotlib", "smbus2", "gpiozero", "lgpio")}}
        atomic_json(self.path / "metadata.json", self.meta)
        self.sync(force=True)
        sync_directory(self.path)

    def row(self, values):
        self.seq += 1
        values = dict(values, run_id=self.run_id, seq=self.seq)
        self.raw.writerow(values)
        self.raw_file.flush()
        self.sync()

    def event(self, event, now, phase, phase_since, details=None):
        # Delayed queue/UI processing preserves the event's effective time.
        timestamp = (datetime.now(TZ) - timedelta(seconds=time.monotonic() - now)).isoformat(timespec="microseconds")
        self.events.writerow({"run_id": self.run_id, "timestamp": timestamp, "elapsed_s": now - self.start,
            "phase_elapsed_s": now - phase_since, "phase": phase, "event": event,
            "details_json": json.dumps(details or {}, ensure_ascii=False, allow_nan=False)})
        self.event_file.flush()
        self.sync()

    def sync(self, force=False):
        now = time.monotonic()
        if force or now - self.last_sync >= self.fsync_interval:
            for f in (self.raw_file, self.event_file):
                f.flush()
                os.fsync(f.fileno())
            self.meta["rows"] = self.seq
            atomic_json(self.path / "metadata.json", self.meta)
            self.last_sync = now

    def finish(self, state, status, now, reason=None, ended_at=None):
        if self.closed:
            return
        intervals = state.history + [{"phase": state.phase, "start_mono": state.since, "end_mono": now,
                                      "actual_s": now - state.since, "planned_s": state.phase_planned}]
        self.meta["phase_intervals"] = [{"phase": i["phase"], "start_s": i["start_mono"] - self.start,
            "end_s": i["end_mono"] - self.start, "actual_s": i["actual_s"], "planned_s": i["planned_s"]} for i in intervals]
        self.meta["extensions"] = [{"at_s": x["at_mono"] - self.start, "duration_s": x["duration_s"]} for x in state.extensions]
        self.meta.update(status=status, ended_at=ended_at or iso_now(), elapsed_s=now - self.start, rows=self.seq, end_reason=reason)
        self.meta["durations"] = {p: {"planned_s": state.durations[p] + (sum(x["duration_s"] for x in state.extensions) if p == "RECOVERY" else 0),
            "actual_s": sum(i["actual_s"] for i in intervals if i["phase"] == p)} for p in state.durations}
        self.sync(force=True)
        self.raw_file.close()
        self.event_file.close()
        self.closed = True
        sync_directory(self.path)

    def finalize_name(self, name="", notes=""):
        self.meta["original_name"] = name
        self.meta["notes"] = notes
        atomic_json(self.path / "metadata.json", self.meta)
        if not name.strip():
            return self.path
        # UUID remains part of the name; no existing directory is overwritten.
        target = self.path.parent / f"{safe_name(name)}_{self.base_name}"
        try:
            if target.exists():
                raise FileExistsError(str(target))
            # Linux renameat2 RENAME_NOREPLACE avoids races, including empty directories.
            import ctypes
            libc = ctypes.CDLL(None, use_errno=True)
            rename = libc.renameat2
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            if rename(-100, os.fsencode(self.path), -100, os.fsencode(target), 1):
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code), str(target))
            self.path = target
            sync_directory(target.parent)
        except Exception as exc:
            self.meta["rename_error"] = str(exc)
            atomic_json(self.path / "metadata.json", self.meta)
            print(f"Đổi tên lỗi: {exc}; dữ liệu vẫn ở {self.path}", flush=True)
        return self.path
