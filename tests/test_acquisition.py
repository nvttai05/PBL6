import queue
import threading
import time
from robonose.config import load
from robonose.readers import SimReader
from robonose.session import Acquisition, Context

def test_inflight_phase_snapshot_is_preserved():
    cfg = load()
    entered, release = threading.Event(), threading.Event()
    class SlowReader(SimReader):
        def read(self, phase, start):
            entered.set()
            assert release.wait(timeout=2)
            return super().read(phase, start)
    reader = SlowReader(cfg)
    now = time.monotonic()
    old, new = object(), object()
    acq = Acquisition(reader, 20, now, Context(old, "BASELINE", now, "BASELINE", "OFF"))
    acq.thread.start()
    assert entered.wait(timeout=2)
    acq.set_context(Context(new, "WAIT_EXPOSURE", now+.01, "WAIT_EXPOSURE", "ON"))
    release.set()
    kind, row, ctx = acq.items.get(timeout=2)
    assert ctx.run is old and row["phase"] == "BASELINE" and ctx.pump_command == "OFF"
    acq.stop.set()
    acq.thread.join(timeout=2)
    assert not acq.thread.is_alive()

def test_bounded_queue_shutdown_keeps_all_acquired_samples():
    reader = SimReader(load())
    now = time.monotonic()
    acq = Acquisition(reader, 1000, now, Context(None, "MONITOR", now, "MONITOR", "DISABLED"))
    acq.items = queue.Queue(maxsize=4)
    acq.thread.start()
    time.sleep(.03)  # producer is blocked, not discarding samples
    rows = []
    def drain(time_budget=None):
        while True:
            try:
                rows.append(acq.items.get_nowait())
            except queue.Empty:
                return
    acq.close(drain)
    assert len(rows) == reader.index
    assert all(kind == "row" for kind, _, _ in rows)
