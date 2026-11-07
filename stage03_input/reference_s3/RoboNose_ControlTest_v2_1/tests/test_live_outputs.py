"""Acquisition + command feedback + raw recording through an emulated COM port."""
import argparse
import csv
import importlib.util
import json
import os
import select
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from monitor import Acquisition
from robonose_core import SessionRecorder, demo_hello, demo_sample
from test_control import ack


@unittest.skipUnless(os.name == "posix" and importlib.util.find_spec("serial"),
                     "Optional output integration test requires POSIX PTY and pyserial")
class LiveOutputTests(unittest.TestCase):
    def test_change_outputs_while_recording_and_confirm_shutdown_off(self):
        master, slave = os.openpty()
        stopping = threading.Event()
        emulator_error = []
        state = {"pump": 0, "valve": False}
        all_off_seen = []
        worker = None

        def send(packet):
            data = json.dumps(packet).encode() + b"\n"
            while data:
                count = os.write(master, data); data = data[count:]

        def device():
            buffer, sequence, deadline = b"", 0, time.monotonic()
            started = time.monotonic()
            try:
                while not stopping.is_set():
                    readable, _, _ = select.select([master], [], [], .01)
                    if readable:
                        buffer += os.read(master, 4096)
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            parts = line.decode("ascii").strip().split()
                            if parts == ["INFO"]:
                                send(demo_hello(.05)); continue
                            if not parts or not parts[0].startswith("@"):
                                continue
                            request = {"request_id": int(parts[0][1:]), "command": parts[1]}
                            if parts[1] == "PUMP": state["pump"] = int(parts[2])
                            elif parts[1] == "VALVE": state["valve"] = bool(int(parts[2]))
                            elif parts[1] == "ALL_OFF":
                                state.update(pump=0, valve=False); all_off_seen.append(request["request_id"])
                            send(ack(request, int((time.monotonic() - started) * 1000), state["pump"], state["valve"]))
                    if time.monotonic() >= deadline:
                        p = demo_sample(sequence, time.monotonic() - started)
                        p.update(pump_pwm_pct=state["pump"], pump_pwm_duty=(state["pump"] * 1023 + 50) // 100,
                                 valve_energized=state["valve"])
                        send(p)
                        sequence += 1; deadline += .05
            except Exception as exc:
                emulator_error.append(exc)

        device_thread = threading.Thread(target=device, daemon=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                rec = SessionRecorder(Path(tmp), "DEMO", port=os.ttyname(slave))
                args = argparse.Namespace(port=os.ttyname(slave), baud=115200, dtr="on", demo=False,
                                          headless=True, duration=0)
                host_stop = threading.Event()
                worker = Acquisition(args, rec, host_stop)
                worker.start(); device_thread.start()

                def wait_for(predicate):
                    limit = time.monotonic() + 3
                    while time.monotonic() < limit:
                        if predicate(): return
                        time.sleep(.01)
                    self.fail("Timed out waiting for emulated output state: " + str(worker.control.snapshot()))

                wait_for(lambda: worker.control.snapshot()["enabled"])
                self.assertTrue(worker.control.request("PUMP", 65))
                wait_for(lambda: worker.control.snapshot()["confirmed"].get("pump_pwm_pct") == 65)
                self.assertTrue(worker.control.request("VALVE", 1))
                wait_for(lambda: worker.control.snapshot()["confirmed"].get("valve_energized") is True)
                time.sleep(.15)
                self.assertTrue(worker.control.request("ALL_OFF"))
                wait_for(lambda: worker.control.snapshot()["confirmed"].get("pump_pwm_pct") == 0)
                host_stop.set(); worker.join(timeout=4)
                self.assertFalse(worker.is_alive())
                self.assertEqual(worker.error, "")
                report = rec.finalize(worker.reason)
                self.assertTrue(report["shutdown_all_off_acknowledged"])
                self.assertEqual(state, {"pump": 0, "valve": False})
                self.assertGreaterEqual(len(all_off_seen), 3) # initial sync, user stop, shutdown
                with (rec.directory / "samples.csv").open(encoding="utf-8-sig", newline="") as f:
                    rows = list(csv.DictReader(f))
                self.assertTrue(any(row["pump_pwm_pct"] == "65" and row["valve_energized"] == "True" for row in rows))
                with (rec.directory / "control_events.csv").open(encoding="utf-8-sig", newline="") as f:
                    events = list(csv.DictReader(f))
                self.assertTrue(any(e["command"] == "PUMP" and e["event"] == "device_ack" and e["ok"] == "True" for e in events))
        finally:
            if worker is not None and worker.is_alive():
                worker.stop.set(); worker.join(timeout=4)
            stopping.set(); device_thread.join(timeout=1)
            os.close(master); os.close(slave)
        self.assertFalse(emulator_error)
