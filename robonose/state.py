from .config import positive

TIMED = {"BASELINE": "WAIT_EXPOSURE", "EXPOSURE": "WAIT_RECOVERY", "RECOVERY": "WAIT_FINISH"}

class StateMachine:
    def __init__(self, now, durations):
        self.phase = "MONITOR"
        self.since = now
        self.durations = dict(durations)
        self.history = []
        self.extensions = []
        self.deadline = None
        self.phase_planned = None

    def transition(self, phase, now):
        old = self.phase
        self.history.append({"phase": old, "start_mono": self.since, "end_mono": now,
                             "actual_s": now - self.since, "planned_s": self.phase_planned})
        self.phase, self.since = phase, now
        self.deadline = now + self.durations[phase] if phase in TIMED else None
        self.phase_planned = self.durations.get(phase) if phase in TIMED else None
        return old, phase

    def tick(self, now):
        if self.deadline is not None and now >= self.deadline:
            # A late UI poll must not turn its delay into extra exposure time.
            return self.transition(TIMED[self.phase], self.deadline)
        return None

    def command(self, cmd, now):
        if cmd == "start" and self.phase == "MONITOR":
            return self.transition("BASELINE", now)
        if cmd == "expose" and self.phase == "WAIT_EXPOSURE":
            return self.transition("EXPOSURE", now)
        if cmd == "recover" and self.phase == "WAIT_RECOVERY":
            return self.transition("RECOVERY", now)
        if cmd.startswith("extend ") and self.phase == "WAIT_FINISH":
            if len(cmd.split()) != 2:
                raise ValueError("extend <số giây>")
            seconds = float(cmd.split()[1])
            positive(seconds, "extend")
            self.extensions.append({"at_mono": now, "duration_s": seconds})
            # Planned total remains distinct from each recovery segment duration.
            original = self.durations["RECOVERY"]
            self.durations["RECOVERY"] = seconds
            change = self.transition("RECOVERY", now)
            self.durations["RECOVERY"] = original
            return change
        raise ValueError(f"Lệnh không hợp lệ trong pha {self.phase}")

    def remaining(self, now):
        return None if self.deadline is None else max(0., self.deadline - now)
