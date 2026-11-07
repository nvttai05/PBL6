"""One bounded asynchronous writer for canonical CSV, events and metadata."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
import json
import os
from pathlib import Path
import queue
import threading
import time
import uuid

from . import __version__
from .analysis import summarize
from .schema import COLUMNS, SCHEMA, finite_or_none
from .storage_layout import LAYOUT_VERSION, DatasetLease, available_folder


class RecorderError(RuntimeError):
    pass


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(finite_or_none(value), handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


class Recorder:
    def __init__(self, root, config, clock, io_hook=None, mode="SIMULATED"):
        self.config, self.clock = config, clock
        self.mode = mode
        self.session_id = str(uuid.uuid4())
        started_at = clock.timestamp()
        self.lease = DatasetLease(Path(root).resolve())
        try:
            self.path = available_folder(Path(root).resolve() / started_at[:10], 'Phien', started_at, self.session_id)
            self.path.mkdir(parents=True, exist_ok=False)
            (self.path / "session").mkdir()
            (self.path / "trials").mkdir()
        except Exception:
            self.lease.close()
            raise
        self.queue = queue.Queue(config.writer_queue_size)
        self.ready = threading.Event()
        self.closing = threading.Event()
        self.done = threading.Event()
        self.fault_reason = None
        self.close_reason = "quit"
        self.rows_written = 0
        self.last_written_seq = None
        self.synced_seq = None
        self.last_written_mono_s = None
        self.last_sync_mono_s = None
        self.io_hook = io_hook
        self.final_details = {}
        self.trials = {}
        self.futures = []
        self.metadata = {"schema": SCHEMA, "mode": mode, "app_version": __version__,
                         "session_id": self.session_id, "status": "PARTIAL", "started_at": started_at,
                         "storage_layout_version": LAYOUT_VERSION, "folder": self.path.name,
                         "config": config.snapshot(), "config_hash": config.config_hash,
                         "board": None, "hardware_validated": False,
                         "phase_owner": "SIMULATION_ENGINE" if mode == "SIMULATED" else "MCU" if mode == "HARDWARE" else "EMULATED_MCU",
                         "physical_feedback": False,
                         "profile_applied_is_simulated": mode != "HARDWARE", "trials": []}
        if mode != "SIMULATED":
            self.metadata["config"].pop("bme_applied_simulated", None)
            self.metadata["config"]["bme_requested"] = {**self.metadata["config"]["bme_requested"], "id": "s3_bringup_300_100_t2h2p4.v1"}
        self.thread = threading.Thread(target=self._run, name="dataset-writer", daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            self.fail("Writer initialization timeout")
            raise RecorderError(self.fault_reason)
        if self.fault_reason:
            raise RecorderError(self.fault_reason)

    def submit(self, kind, payload):
        if self.fault_reason or self.closing.is_set():
            raise RecorderError(self.fault_reason or "Writer closing")
        try:
            self.queue.put_nowait((kind, deepcopy(payload)))
        except queue.Full:
            self.fail("Writer queue full; acquisition stopped without fabricating samples")
            raise RecorderError(self.fault_reason)

    def fail(self, reason):
        self.fault_reason = self.fault_reason or str(reason)
        self.closing.set()

    def health(self):
        return {"rows_written": self.rows_written, "last_written_seq": self.last_written_seq,
                "synced_seq": self.synced_seq, "queue_depth": self.queue.qsize(),
                "last_written_mono_s": self.last_written_mono_s, "last_sync_mono_s": self.last_sync_mono_s,
                "status": "ERROR" if self.fault_reason else "CLOSED" if self.done.is_set() else "RECORDING",
                "error": self.fault_reason, "path": str(self.path)}

    def close(self, reason="quit", timeout=10, final_details=None):
        self.close_reason = reason
        self.final_details = final_details or {}
        self.closing.set()
        self.thread.join(timeout)
        if self.thread.is_alive():
            self.fail("Writer shutdown timeout; output OFF; storage completion unconfirmed")
        return self.done.is_set() and not self.fault_reason

    def _event(self, event):
        self.events.write(json.dumps(finite_or_none(event), ensure_ascii=False, allow_nan=False) + "\n")
        self.events.flush()

    def _trial(self, trial, finalize=False):
        trial = {**trial, "mode": self.mode}
        trial_id = trial["trial_id"]
        if trial_id not in self.trials:
            offset = self.metadata.get('clock_mapping', {}).get('offset_s', 0)
            started_at = self.clock.timestamp(trial['started_mono_s'] - offset)
            directory = available_folder(self.path / 'trials', trial.get('name'), started_at, trial_id)
            directory.mkdir(exist_ok=False)
            handle = (directory / "raw.csv").open("x", encoding="utf-8", newline="")
            writer = csv.DictWriter(handle, COLUMNS, extrasaction="raise")
            writer.writeheader()
            self.trials[trial_id] = {"directory": directory, "handle": handle, "writer": writer,
                                     "first_seq": None, "last_seq": None, "rows": 0, "finalized": False,
                                     "last_cycle_end_mono_s": None,
                                     "started_at": started_at}
        item = self.trials[trial_id]
        destination = available_folder(self.path / 'trials', trial.get('name'), item['started_at'], trial_id, current=item['directory'])
        if destination != item['directory'] and not item['finalized']:
            # Windows cannot rename a folder containing our open CSV handle.
            # Only the writer closes/reopens it; acquisition keeps its own queue.
            item['handle'].flush()
            os.fsync(item['handle'].fileno())
            item['handle'].close()
            try:
                item['directory'].rename(destination)
            except OSError as error:
                self._event({'event': 'trial_folder_rename_deferred', 'mode': self.mode,
                             'trial_id': trial_id, 'reason': str(error), 'timestamp': self.clock.timestamp()})
            else:
                item['directory'] = destination
            item['handle'] = (item['directory'] / 'raw.csv').open('a', encoding='utf-8', newline='')
            item['writer'] = csv.DictWriter(item['handle'], COLUMNS, extrasaction='raise')
        item["metadata"] = deepcopy(trial)
        metadata = {**trial, "schema": SCHEMA, "mode": self.mode, "session_id": self.session_id,
                    "started_at": item['started_at'], "folder": item['directory'].name,
                    "storage_layout_version": LAYOUT_VERSION,
                    "source_raw": "../../session/raw.csv", "is_export_of_session": True,
                    "config_hash": self.metadata["config_hash"], "config": self.metadata["config"],
                    "first_seq": item["first_seq"], "last_seq": item["last_seq"], "rows": item["rows"],
                    "export_finalized": finalize}
        write_json(item["directory"] / "metadata.json", metadata)
        write_json(self.path / "trials/index.json", [
            {"trial_id": key, "index": val["metadata"]["index"], "status": val["metadata"]["status"],
             "name": val["metadata"]["name"], "folder": val['directory'].name,
             "started_at": val['started_at']} for key, val in self.trials.items()])
        if finalize and not item["finalized"]:
            item["handle"].flush()
            os.fsync(item["handle"].fileno())
            item["handle"].close()
            item["finalized"] = True
            self._collect_analysis()
            if len(self.futures) >= 4:
                raise RecorderError("Analysis backlog full")
            self.futures.append((item["directory"], self.analysis.submit(
                summarize, item["directory"] / "raw.csv", deepcopy(trial), self.config)))

    def _sample(self, row):
        if self.io_hook:
            self.io_hook(row)
        row = finite_or_none(row)
        self.raw_writer.writerow(row)
        self.raw.flush()
        self.rows_written += 1
        self.last_written_seq = row["seq"]
        self.last_written_mono_s = self.clock.now()
        self.metadata.setdefault("boot_id", row["boot_id"])
        if row["trial_id"]:
            item = self.trials[row["trial_id"]]
            if item["finalized"]:
                raise RecorderError("In-flight sample arrived after trial export barrier")
            item["writer"].writerow(row)
            item["handle"].flush()
            item["rows"] += 1
            item["first_seq"] = row["seq"] if item["first_seq"] is None else item["first_seq"]
            item["last_seq"] = row["seq"]
            item['last_cycle_end_mono_s'] = row.get('cycle_end_mono_s',row['mono_s'])

    def _collect_analysis(self, wait=False):
        pending = []
        for directory, future in self.futures:
            if future.done() or wait:
                write_json(directory / "summary.json", future.result(timeout=10 if wait else None))
            else:
                pending.append((directory, future))
        self.futures = pending

    def _checkpoint(self):
        self._event({"event": "checkpoint", "timestamp": self.clock.timestamp(),
                     "last_written_seq": self.last_written_seq, "mode": self.mode})
        handles = [self.raw, self.events, *(v["handle"] for v in self.trials.values() if not v["finalized"])]
        if self.wire:
            handles.append(self.wire)
        for handle in handles:
            handle.flush()
            os.fsync(handle.fileno())
        candidate = self.last_written_seq
        write_json(self.path / "session/checkpoint.json", {"mode": self.mode, "synced_seq": candidate,
                                                          "rows_written": self.rows_written, "at": self.clock.timestamp()})
        self.synced_seq = candidate
        self.last_sync_mono_s = self.clock.now()

    def _run(self):
        self.analysis = ThreadPoolExecutor(max_workers=1, thread_name_prefix="closed-trial-analysis")
        self.raw = self.events = self.wire = None
        try:
            self.raw = (self.path / "session/raw.csv").open("x", encoding="utf-8", newline="")
            self.events = (self.path / "session/events.jsonl").open("x", encoding="utf-8", newline="\n")
            if self.mode != "SIMULATED":
                self.wire = (self.path / "session/wire.jsonl").open("x", encoding="utf-8", newline="\n")
            self.raw_writer = csv.DictWriter(self.raw, COLUMNS, extrasaction="raise")
            self.raw_writer.writeheader()
            write_json(self.path / "session/metadata.json", self.metadata)
            self._checkpoint()
            self.ready.set()
            last_sync = time.monotonic()
            while not self.closing.is_set() or not self.queue.empty():
                try:
                    kind, payload = self.queue.get(timeout=.05)
                except queue.Empty:
                    kind = None
                try:
                    if kind == "sample":
                        self._sample(payload)
                    elif kind == "event":
                        self._event(payload)
                    elif kind == "trial":
                        self._trial(payload["trial"], payload.get("finalize", False))
                    elif kind == "session_metadata":
                        self.metadata.update(payload)
                        write_json(self.path / "session/metadata.json", self.metadata)
                    elif kind == "sync":
                        self._checkpoint()
                    elif kind == "wire":
                        if not self.wire:
                            raise RecorderError("Wire log unavailable for this mode")
                        self.wire.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
                        self.wire.flush()
                finally:
                    if kind is not None:
                        self.queue.task_done()
                self._collect_analysis()
                if time.monotonic() - last_sync >= self.config.checkpoint_s:
                    self._checkpoint()
                    last_sync = time.monotonic()
        except Exception as error:
            self.fail(f"{type(error).__name__}: {error}")
        finally:
            self.ready.set()
            try:
                for item in list(self.trials.values()):
                    if not item["finalized"]:
                        trial = deepcopy(item["metadata"])
                        # Hardware intervals use MCU boot time, not process
                        # uptime. When OFF is unconfirmed this is an explicitly
                        # labelled estimate, bounded by the last recorded scan.
                        final_mono=max(self.clock.now()+self.metadata.get('clock_mapping',{}).get('offset_s',0),
                                       trial['started_mono_s'],item['last_cycle_end_mono_s'] or 0)
                        if trial["status"] == "ACTIVE":
                            trial["status"] = "ERROR" if self.fault_reason else "ABORTED"
                            trial["finished_mono_s"] = final_mono
                            trial['finished_time_source']='host_shutdown_clock_estimate'
                        if trial["intervals"][-1]["end_mono_s"] is None:
                            trial["intervals"][-1]["end_mono_s"] = final_mono
                            trial['intervals'][-1]['end_time_source']='host_shutdown_clock_estimate'
                        self._trial(trial, finalize=True)
                self._collect_analysis(wait=True)
                if self.raw and self.events:
                    self._checkpoint()
            except Exception as error:
                self.fail(f"Finalize: {error}")
            self.metadata.update(status="ERROR" if self.fault_reason else "CLOSED",
                                 ended_at=self.clock.timestamp(), reason=self.fault_reason or self.close_reason,
                                 rows_written=self.rows_written, synced_seq=self.synced_seq,
                                 uncommitted_queue_items=self.queue.qsize(),
                                 trials=[item["metadata"]["trial_id"] for item in self.trials.values()])
            self.metadata.update(self.final_details)
            try:
                write_json(self.path / "session/metadata.json", self.metadata)
            except Exception as error:
                self.fail(f"Metadata unavailable: {error}")
            for handle in [self.raw, self.events, self.wire, *(v["handle"] for v in self.trials.values())]:
                if handle and not handle.closed:
                    try:
                        handle.close()
                    except OSError as error:
                        self.fail(str(error))
            self.analysis.shutdown(wait=False, cancel_futures=True)
            self.lease.close()
            self.done.set()


def find_partial_sessions(root):
    """Read-only discovery: never relabel or resume a previous session."""
    partials = []
    for path in Path(root).glob("*/*/session/metadata.json"):
        try:
            if json.loads(path.read_text(encoding="utf-8"))["status"] in ("PARTIAL", "ERROR"):
                partials.append(str(path))
        except (OSError, ValueError, KeyError):
            partials.append(str(path))
    return partials
