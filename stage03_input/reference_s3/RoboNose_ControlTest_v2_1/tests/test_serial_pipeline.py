"""Exercise pyserial against a Linux pseudo-terminal, not physical sensors."""
import csv
import importlib.util
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from robonose_core import demo_hello, demo_sample
from test_control import ack


@unittest.skipUnless(os.name == "posix" and importlib.util.find_spec("serial"),
                     "Optional serial integration test requires POSIX PTY and pyserial")
class SerialPipelineTests(unittest.TestCase):
    def test_real_serial_reader_records_partial_lines_errors_and_reset(self):
        root = Path(__file__).resolve().parents[1]
        master, slave = os.openpty()
        port = os.ttyname(slave)
        process = None
        try:
            with tempfile.TemporaryDirectory() as temp:
                process = subprocess.Popen(
                    [sys.executable, str(root / "pc" / "monitor.py"), "--port", port,
                     "--headless", "--duration", "1.8", "--output", temp],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env={**os.environ, "MPLBACKEND": "Agg"})
                requested = b""
                limit = time.monotonic() + 4
                while b"INFO\n" not in requested and time.monotonic() < limit:
                    readable, _, _ = select.select([master], [], [], .05)
                    if readable:
                        requested += os.read(master, 4096)
                self.assertIn(b"INFO\n", requested, "Host did not open the serial connection")
                missing = demo_sample(10, faults=True); missing["seq"] = 1
                invalid = demo_sample(15, faults=True); invalid["seq"] = 4
                reset = demo_sample(0); reset["boot_id"] = "RESET_BOOT"
                packets = [demo_hello(), demo_sample(0), missing, invalid, invalid, reset]
                payload = b"ROM boot text\r\n" + b"".join(
                    json.dumps(p).encode() + b"\r\n" for p in packets)
                os.write(master, payload[:71])
                time.sleep(.03)
                os.write(master, payload[71:])
                expected_bytes = bytearray(payload)
                pending = b""
                limit = time.monotonic() + 12
                while process.poll() is None and time.monotonic() < limit:
                    readable, _, _ = select.select([master], [], [], .05)
                    if not readable:
                        continue
                    pending += os.read(master, 4096)
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        parts = line.decode().split()
                        if not parts or not parts[0].startswith("@"):
                            continue
                        reply = ack({"request_id": int(parts[0][1:]), "command": parts[1]},
                                    stamp=10000 + len(expected_bytes), boot="RESET_BOOT")
                        data = json.dumps(reply).encode() + b"\n"
                        os.write(master, data)
                        expected_bytes.extend(data)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                summary_file = next(Path(temp).rglob("summary.json"))
                summary = json.loads(summary_file.read_text())
                self.assertEqual(summary["sample_count"], 5)
                self.assertEqual(summary["missing_sequence_numbers"], 2)
                self.assertEqual(summary["device_boot_changes"], 1)
                self.assertEqual(summary["duplicate_or_out_of_order"], 1)
                self.assertEqual(summary["parse_errors"], 1)
                with (summary_file.parent / "samples.csv").open(encoding="utf-8-sig", newline="") as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(rows[1]["mq135_1_voltage_v"], "")
                self.assertEqual(rows[2]["gas_valid"], "False")
                self.assertEqual((summary_file.parent / "serial_bytes.bin").read_bytes(), bytes(expected_bytes))
                self.assertTrue(summary["shutdown_all_off_acknowledged"])
                self.assertTrue((summary_file.parent / "dashboard.png").exists())
        finally:
            if process is not None and process.poll() is None:
                process.kill(); process.communicate()
            os.close(master); os.close(slave)
