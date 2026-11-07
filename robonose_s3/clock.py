from datetime import datetime, timedelta, timezone
import time

LOCAL_TZ = timezone(timedelta(hours=7))


class Clock:
    def __init__(self):
        self.origin = time.monotonic()
        self.wall_origin = datetime.now(LOCAL_TZ)

    def now(self):
        return time.monotonic() - self.origin

    def timestamp(self, mono_s=None):
        return (self.wall_origin + timedelta(seconds=self.now() if mono_s is None else mono_s)).isoformat()


class FakeClock(Clock):
    """Deterministic simulation fixture clock; never changes the user's preset."""
    def __init__(self):
        self.value = 0.0
        self.wall_origin = datetime(2026, 11, 6, 9, tzinfo=LOCAL_TZ)

    def now(self):
        return self.value

    def advance(self, seconds):
        if seconds < 0:
            raise ValueError("Monotonic clock cannot go backwards")
        self.value += seconds
