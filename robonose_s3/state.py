"""Pure phase owner for simulation. Hardware will supply MCU-owned telemetry instead."""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
import math
import uuid

from .config import Config

TIMED = {"BASELINE": "WAIT_EXPOSURE", "EXPOSURE": "WAIT_RECOVERY", "RECOVERY": "WAIT_FINISH"}
ACTIVE = set(TIMED) | set(TIMED.values())
SAMPLE_STATES = {"MONITOR", "BASELINE", "WAIT_EXPOSURE", "EXPOSURE", "WAIT_RECOVERY"}
HELP = ("start | expose | recover | finish | name <text> | notes <text> | next | "
        "extend <seconds> | abort | mark <text> | status | info | durations | help | quit")


@dataclass
class Trial:
    trial_id: str
    index: int
    started_mono_s: float
    status: str = "ACTIVE"
    name: str | None = None
    notes: str | None = None
    finished_mono_s: float | None = None
    intervals: list = field(default_factory=list)

    def snapshot(self):
        return deepcopy(self.__dict__)


class StateMachine:
    def __init__(self, config: Config):
        self.config = config
        self.phase = "OFF"
        self.phase_started = 0.0
        self.deadline = None
        self.pwm = 0
        self.trial = None
        self.trial_count = 0
        self.epoch = 0
        self.segment = 0
        self.events = []
        self.requests = OrderedDict()
        self.pump_start_count = 0

    @property
    def route(self):
        return "SAMPLE" if self.phase in SAMPLE_STATES else "FILTERED_AIR"

    @property
    def closed(self):
        return self.phase in ("CLOSED", "ERROR")

    def context(self, now):
        return {"trial_id": self.trial.trial_id if self.trial else None, "phase": self.phase,
                "segment_id": self.segment, "context_epoch": self.epoch,
                "phase_elapsed_s": max(0.0, now - self.phase_started),
                "pump_pwm_pct": self.pwm, "valve_energized": self.route == "SAMPLE",
                "air_path_commanded": self.route}

    def emit(self, event, effective, processed=None, **details):
        self.events.append({"event": event, "effective_mono_s": effective,
                            "processed_mono_s": effective if processed is None else processed,
                            **self.context(effective), "details": details})

    def _transition(self, phase, effective, processed=None, duration=None):
        previous = self.phase
        if self.trial and self.trial.intervals and self.trial.intervals[-1]["end_mono_s"] is None:
            self.trial.intervals[-1]["end_mono_s"] = effective
        self.phase = phase
        self.phase_started = effective
        self.deadline = None if duration is None else effective + duration
        self.epoch += 1
        self.segment += 1
        if self.trial:
            self.trial.intervals.append({"phase": phase, "segment_id": self.segment,
                                         "start_mono_s": effective, "end_mono_s": None,
                                         "planned_s": duration, "air_path_commanded": self.route})
        self.emit("phase_change", effective, processed, previous=previous, next=phase)
        self._metadata(effective)

    def _metadata(self, now, finalize=False):
        if self.trial:
            self.emit("trial_metadata", now, trial=self.trial.snapshot(), finalize=finalize)

    def start_session(self, now):
        if self.phase != "OFF":
            raise ValueError("Session already started")
        self.pwm = 80
        self.pump_start_count += 1
        self._transition("MONITOR", now)
        self.emit("simulated_output_start", now, mode="SIMULATED", pwm=80)

    def advance(self, now):
        if self.deadline is not None and now >= self.deadline:
            self._transition(TIMED[self.phase], self.deadline, now)

    def _finish(self, now, status):
        self.trial.status = status
        self.trial.finished_mono_s = now
        self._transition("WAIT_NAME", now)
        self.emit("trial_finished", now, status=status)

    def stop(self, now, fault=None, reason="quit"):
        if self.closed:
            return
        self.pwm = 0  # OFF before any filesystem/queue operation.
        if self.trial:
            if self.trial.status == "ACTIVE":
                self.trial.status = "ERROR" if fault else "ABORTED"
                self.trial.finished_mono_s = now
            if self.trial.intervals[-1]["end_mono_s"] is None:
                self.trial.intervals[-1]["end_mono_s"] = now
            self._metadata(now, finalize=True)
        self.trial = None
        self._transition("ERROR" if fault else "CLOSED", now)
        self.emit("session_fault" if fault else "session_stop", now, reason=fault or reason)

    def command(self, text, now, request_id=None):
        self.advance(now)
        request_id = request_id or str(uuid.uuid4())
        if request_id in self.requests:
            original, result = self.requests[request_id]
            return result if text == original else {"accepted": False, "reason": "request ID reused with different text", "request_id": request_id}
        command, _, arg = text.strip().partition(" ")
        command, arg = command.lower(), arg.strip()
        accepted, reason = True, "accepted"
        self.emit("command_received", now, request_id=request_id, text=text)
        if self.closed:
            accepted, reason = False, "Session closed/fault latched; launch a new demo session"
        elif len(text) > 2048:
            accepted, reason = False, "Command exceeds 2048 characters"
        elif command in ("status", "info", "help", "durations") and not arg:
            reason = HELP if command == "help" else str(self.context(now))
            if command == "durations":
                reason = f"baseline={self.config.baseline_s}s exposure={self.config.exposure_s}s recovery={self.config.recovery_s}s"
        elif command == "quit" and not arg:
            self.stop(now)
        elif command == "start" and not arg and self.phase == "MONITOR":
            self.trial_count += 1
            self.trial = Trial(str(uuid.uuid4()), self.trial_count, now)
            self._transition("BASELINE", now, duration=self.config.baseline_s)
        elif command == "expose" and not arg and self.phase == "WAIT_EXPOSURE":
            self._transition("EXPOSURE", now, duration=self.config.exposure_s)
        elif command == "recover" and not arg and self.phase == "WAIT_RECOVERY":
            self._transition("RECOVERY", now, duration=self.config.recovery_s)
        elif command == "extend" and self.phase == "WAIT_FINISH":
            try:
                duration = float(arg)
                if not math.isfinite(duration) or not 0 < duration <= self.config.max_extend_s:
                    raise ValueError()
                self._transition("RECOVERY", now, duration=duration)
            except ValueError:
                accepted, reason = False, f"extend requires finite seconds in (0, {self.config.max_extend_s}]"
        elif command in ("finish", "abort") and not arg and self.phase in ACTIVE:
            self._finish(now, "COMPLETE" if command == "finish" and self.phase == "WAIT_FINISH" else "ABORTED")
        elif command in ("name", "notes") and self.phase == "WAIT_NAME" and arg:
            setattr(self.trial, command, arg)
            self._metadata(now)
        elif command == "next" and not arg and self.phase == "WAIT_NAME":
            self.trial.intervals[-1]["end_mono_s"] = now
            self._metadata(now, finalize=True)
            self.trial = None
            self._transition("MONITOR", now)
        elif command == "mark" and arg:
            self.emit("marker", now, text=arg)
        else:
            accepted, reason = False, f"{command or '(empty)'} is invalid in {self.phase}, or arguments are missing/unexpected; use help"
        result = {"accepted": accepted, "reason": reason, "phase": self.phase, "request_id": request_id}
        self.emit("command_result", now, **result)
        self.requests[request_id] = (text, result)
        if len(self.requests) > 256:
            self.requests.popitem(last=False)
        return result

    def drain_events(self):
        events, self.events = self.events, []
        return events
