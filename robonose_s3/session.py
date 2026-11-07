"""Simulation owner, nonblocking command mailbox and immutable UI snapshots."""
from collections import deque
from copy import deepcopy
import queue
import threading
import time
import uuid

from .clock import Clock
from .config import Config
from .quality import evaluate
from .recorder import Recorder, RecorderError
from .simulated import SimDevice
from .state import StateMachine


class Engine:
    def __init__(self, config, clock, recorder):
        self.config, self.clock, self.recorder = config, clock, recorder
        self.state = StateMachine(config)
        self.device = SimDevice(config, recorder.session_id, clock)
        self.history = deque(maxlen=config.history_size)
        self.recent_events = deque(maxlen=100)
        self.quality = evaluate([], clock.now(), config)
        self.next_sample = clock.now()
        self.gaps = self.errors = self.stale = 0
        self.shutdown_count = 0
        try:
            self.state.start_session(clock.now())  # Recorder readiness precedes simulated ON.
            self.publish_events()
        except RecorderError as error:
            self.fault(error)
            recorder.close("startup fault")
            raise

    def publish_events(self):
        for event in self.state.drain_events():
            event.update(mode="SIMULATED", timestamp=self.clock.timestamp(event["effective_mono_s"]))
            self.recent_events.append(event)
            self.recorder.submit("event", event)
            if event["event"] == "trial_metadata":
                self.recorder.submit("trial", event["details"])

    def fault(self, reason):
        self.state.stop(self.clock.now(), fault=str(reason))
        self.device.close()
        self.recorder.fail(str(reason))
        # The output state is latched OFF even if the full queue cannot log it.
        self.recent_events.extend(self.state.drain_events())

    def command(self, text, request_id=None, received_mono=None):
        if self.recorder.fault_reason:
            self.fault(self.recorder.fault_reason)
        before = self.state.phase
        request_id = request_id or str(uuid.uuid4())
        is_new = request_id not in self.state.requests
        try:
            if is_new and not self.state.closed:
                self.recorder.submit("event", {"event": "host_command_received", "mode": "SIMULATED",
                    "request_id": request_id, "text": text,
                    "received_mono_s": self.clock.now() if received_mono is None else received_mono,
                    "applied_mono_s": self.clock.now()})
            result = self.state.command(text, self.clock.now(), request_id)
            if is_new and result["accepted"] and before == "MONITOR" and self.state.phase == "BASELINE":
                if self.quality["overall"] != "STABLE":
                    self.state.emit("baseline_started_without_stability", self.clock.now(), quality=deepcopy(self.quality))
            self.publish_events()
            return result
        except RecorderError as error:
            self.fault(error)
            return {"accepted": False, "reason": str(error), "phase": "ERROR", "request_id": request_id}

    def capture(self, errors=None):
        now = self.clock.now()
        self.state.advance(now)
        self.publish_events()
        return self.device.read(now, self.state.context(now), errors=errors)

    def commit(self, row):
        self.state.advance(self.clock.now())
        # Keep the captured context; metadata commands are processed after acquisition.
        row["context_straddled"] = (row["context_epoch"] != self.state.epoch or
            (self.state.deadline is not None and row["mono_s"] < self.state.deadline <= row["cycle_end_mono_s"]))
        self.recorder.submit("sample", row)
        self.history.append(row)
        self.publish_events()
        self.quality = evaluate(self.history, self.clock.now(), self.config)
        self.errors += sum(row[f"{s}_status"] == "ERROR" for s in (*self.config.snapshot()["channel_map"].values(), "bme688"))
        self.stale += sum(row[f"{s}_status"] == "STALE" for s in (*self.config.snapshot()["channel_map"].values(), "bme688"))

    def step(self):
        if self.recorder.fault_reason:
            self.fault(self.recorder.fault_reason)
        if self.state.closed:
            return
        try:
            now = self.clock.now()
            self.state.advance(now)
            self.publish_events()
            if now >= self.next_sample:
                period = 1 / self.config.sampling_hz
                lag = max(0, now - self.next_sample)
                skipped = int((lag + 1e-9) / period)
                row = self.capture()
                row.update(schedule_lag_s=lag, skipped_cycles=skipped)
                self.gaps += skipped
                self.commit(row)
                self.next_sample += (skipped + 1) * period
        except Exception as error:
            self.fault(error)

    def snapshot(self):
        now = self.clock.now()
        latest = self.history[-1] if self.history else None
        health = self.recorder.health()
        heartbeat = bool(latest and now - latest["mono_s"] < 3 and
                         health["last_written_seq"] is not None and
                         latest["seq"] - health["last_written_seq"] <= 2 and
                         health["last_sync_mono_s"] is not None and
                         now - health["last_sync_mono_s"] <= max(3, self.config.checkpoint_s * 2)
                         and not self.state.closed)
        return {"mode": "SIMULATED", "now": now, **self.state.context(now),
                "remaining_s": max(0, self.state.deadline - now) if self.state.deadline is not None else None,
                "trial": self.state.trial.snapshot() if self.state.trial else None,
                "latest": latest, "history": tuple(self.history), "events": tuple(self.recent_events),
                "quality": self.quality, "writer": health, "sample_count": self.device.seq,
                "gaps": self.gaps, "errors": self.errors, "stale": self.stale,
                "simulated_heartbeat_healthy": heartbeat}

    def shutdown(self, reason="quit"):
        if self.shutdown_count:
            return
        self.shutdown_count += 1
        if not self.state.closed:
            self.state.stop(self.clock.now(), reason=reason)
        try:
            self.publish_events()
        except RecorderError as error:
            self.fault(error)
        self.device.close()
        self.recorder.close(reason)
        if self.recorder.fault_reason:
            self.state.phase, self.state.pwm = "ERROR", 0


class Session:
    def __init__(self, root, config=None, clock=None, io_hook=None, on_message=None,
                 engine_factory=None, mode="SIMULATED"):
        self.config = config or Config()
        self.clock = clock or Clock()
        self.mode = mode
        recorder = Recorder(root, self.config, self.clock, io_hook=io_hook, mode=mode)
        self.engine = (engine_factory or Engine)(self.config, self.clock, recorder)
        self.commands = queue.Queue(self.config.command_queue_size)
        self.stop_requested = threading.Event()
        self.finished = threading.Event()
        self.stop_reason = "quit"
        self.on_message = on_message or (lambda text: None)
        self.lock = threading.Lock()
        self.current = self.engine.snapshot()
        self.thread = threading.Thread(target=self._run, name="simulation-engine", daemon=True)

    def start(self):
        self.thread.start()

    def post(self, text, request_id=None):
        if self.finished.is_set() or self.stop_requested.is_set():
            return False
        if self.mode != "SIMULATED" and text.strip().lower() == "quit":
            self.request_stop("quit")
            return True
        try:
            self.commands.put_nowait((text, request_id or str(uuid.uuid4()), self.clock.now()))
            return True
        except queue.Full:
            return False

    def request_stop(self, reason="quit"):
        if not self.stop_requested.is_set():
            self.stop_reason = reason
        self.stop_requested.set()

    def snapshot(self):
        if hasattr(self.engine, "note_ui_read"):
            self.engine.note_ui_read()
        with self.lock:
            # Samples and quality dictionaries are immutable once published.
            return dict(self.current)

    def _run(self):
        previous = self.engine.state.phase
        try:
            while not self.stop_requested.is_set() and not self.engine.state.closed:
                for _ in range(16):
                    if not getattr(self.engine, "command_ready", True):
                        break
                    try:
                        text, request_id, received = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    result = self.engine.command(text, request_id, received)
                    label = 'PENDING' if result['accepted'] is None else 'OK' if result['accepted'] else 'REJECTED'
                    self.on_message(f"{label} {text}: {result['reason']}")
                    self.commands.task_done()
                    if self.engine.state.closed:
                        break
                self.engine.step()
                if hasattr(self.engine, "drain_messages"):
                    for message in self.engine.drain_messages():
                        self.on_message(message)
                if self.engine.state.phase != previous:
                    previous = self.engine.state.phase
                    self.on_message(f"{self.mode} phase: {previous}")
                with self.lock:
                    self.current = self.engine.snapshot()
                self.stop_requested.wait(.02)
        except Exception as error:
            self.engine.fault(error)
        finally:
            self.engine.shutdown(self.stop_reason)
            with self.lock:
                self.current = self.engine.snapshot()
            self.finished.set()
