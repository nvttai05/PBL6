"""Exercise actual Matplotlib button mouse events against the demo worker."""
import argparse
import csv
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))


class DashboardControlTests(unittest.TestCase):
    def test_slider_apply_valve_and_all_off_buttons(self):
        import matplotlib
        matplotlib.use("Agg", force=True)
        from matplotlib.backend_bases import MouseEvent
        from dashboard import Dashboard
        from monitor import Acquisition
        from robonose_core import SessionRecorder
        with tempfile.TemporaryDirectory() as tmp:
            recorder = SessionRecorder(Path(tmp), "DEMO")
            args = argparse.Namespace(demo=True, demo_interval=.04, demo_faults=False,
                                      duration=0, headless=True, port=None)
            stop = threading.Event()
            worker = Acquisition(args, recorder, stop)
            chart = Dashboard(600, "DEMO", control_request=worker.control.request)
            try:
                worker.start()

                def wait_for(predicate):
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        if predicate(): return
                        time.sleep(.01)
                    self.fail(str(worker.control.snapshot()))

                wait_for(lambda: worker.control.snapshot()["enabled"])
                chart.refresh_controls(worker.control.snapshot())
                chart.figure.canvas.draw()

                def click(index):
                    button = chart.control_buttons[index][1]
                    box = button.ax.bbox
                    x, y = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
                    for kind in ("button_press_event", "button_release_event"):
                        event = MouseEvent(kind, chart.figure.canvas, x, y, button=1)
                        chart.figure.canvas.callbacks.process(kind, event)

                chart.pump_slider.set_val(60)
                self.assertEqual(worker.control.snapshot()["confirmed"]["pump_pwm_pct"], 0)
                click(0) # Apply Pump, not the slider itself
                wait_for(lambda: worker.control.snapshot()["confirmed"].get("pump_pwm_pct") == 60)
                click(3) # Lay mau / B / ON
                wait_for(lambda: worker.control.snapshot()["confirmed"].get("valve_energized") is True)
                chart.refresh_controls(worker.control.snapshot())
                self.assertIn("SAMPLE (B/ON)", chart.output_feedback.get_text())
                click(4) # ALL OFF
                wait_for(lambda: worker.control.snapshot()["confirmed"].get("pump_pwm_pct") == 0
                         and worker.control.snapshot()["confirmed"].get("valve_energized") is False)
                chart.refresh_controls(worker.control.snapshot())
                self.assertIn("FILTERED AIR (A/OFF)", chart.output_feedback.get_text())
            finally:
                stop.set(); worker.join(timeout=4)
                chart.plt.close(chart.figure)
                self.assertFalse(worker.is_alive())
                recorder.finalize(worker.reason)
            self.assertEqual(worker.error, "")
            with (recorder.directory / "control_events.csv").open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(any(row["command"] == "PUMP" and row["requested_value"] == "60"
                                and row["event"] == "command_sent" for row in rows))
