"""Create two deterministic virtual-time trials, without changing demo durations."""
from pathlib import Path
import json
import os
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robonose_s3.clock import FakeClock
from robonose_s3.config import Config
from robonose_s3.recorder import Recorder
from robonose_s3.session import Engine


def main():
    configured = json.loads((ROOT / "configs/paths.local.json").read_text(encoding="utf-8"))["python_exe"]
    if Path(sys.executable).resolve() != Path(configured).resolve():
        raise SystemExit(f"Use {configured}")
    config, clock = Config(), FakeClock()
    recorder = Recorder(ROOT / "data/simulation", config, clock)
    engine = Engine(config, clock, recorder)
    ids = []

    def drain():
        deadline = time.monotonic() + 5
        while recorder.queue.unfinished_tasks and time.monotonic() < deadline:
            if recorder.fault_reason:
                raise RuntimeError(recorder.fault_reason)
            time.sleep(.001)
        if recorder.queue.unfinished_tasks:
            raise RuntimeError("Fixture writer timeout")

    def seconds(count):
        for _ in range(count):
            engine.step()
            drain()
            clock.advance(1)
        engine.state.advance(clock.now())
        engine.publish_events()
        drain()

    def command(text):
        result = engine.command(text)
        if not result["accepted"]:
            raise RuntimeError(result)
        drain()

    try:
        seconds(5)
        for number in (1, 2):
            command("start")
            ids.append(engine.state.trial.trial_id)
            seconds(60)
            seconds(5)
            command("mark sample placement — SIMULATED")
            command("expose")
            seconds(120)
            seconds(5)
            command("recover")
            seconds(60)
            seconds(5)
            if number == 2:
                command("extend 10")
                seconds(10)
                seconds(4)
            command("finish")
            command("name Mẫu mô phỏng trùng tên")
            command(f"notes SIMULATED trial {number}; no physical sample measured")
            seconds(5)
            if number == 1:
                command("next")
                seconds(5)

        # Render the completed second trial with WAIT labels before closing it.
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6 import QtWidgets
        from robonose_s3.dashboard import Dashboard, configure_qt_font
        app = QtWidgets.QApplication([])
        configure_qt_font(app)

        class StaticSession:
            finished = threading.Event()
            def __init__(self):
                self.config = config
            def snapshot(self):
                return engine.snapshot()
            def request_stop(self, reason):
                pass

        window = Dashboard(StaticSession())
        window.window_combo.setCurrentIndex(1)
        window.show()
        app.processEvents()
        window.refresh()
        if not window.grab().save(str(ROOT / "runtime/STAGE02_DASHBOARD.png")):
            raise RuntimeError("Dashboard snapshot failed")
        window.close()
        command("next")
        seconds(3)
        command("quit")
    finally:
        engine.shutdown("fixture complete")
    if recorder.fault_reason:
        raise RuntimeError(recorder.fault_reason)
    report = {"mode": "SIMULATED", "clock": "FakeClock; virtual seconds, no real-time duration benchmark",
              "status": "CLOSED", "session_path": str(recorder.path), "trial_ids": ids,
              "rows": recorder.rows_written, "config_hash": config.config_hash,
              "durations_s": {"baseline": 60, "exposure": 120, "recovery": 60},
              "pump_start_count": engine.state.pump_start_count, "sensor_init_count": engine.device.init_count,
              "final_pwm_pct": engine.state.pwm, "hardware_access": False,
              "screenshot": "runtime/STAGE02_DASHBOARD.png"}
    (ROOT / "runtime/STAGE02_FIXTURE.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
