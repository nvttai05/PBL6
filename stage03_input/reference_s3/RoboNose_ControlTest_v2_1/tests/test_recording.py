import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from robonose_core import (MAX_LINE_BYTES, LineFramer, ProtocolError, SessionRecorder,
                           demo_hello, demo_sample, parse_packet, valid_value)


def encoded(packet):
    return json.dumps(packet, allow_nan=False).encode()


class ProtocolTests(unittest.TestCase):
    def test_valid_values_and_direct_ao_scale(self):
        p = parse_packet(encoded(demo_sample(1)))
        for name in ("mq135_1", "mq3_1", "tgs2602", "mq3_2"):
            # Firmware serializes voltage to six decimal places (0.5 uV rounding).
            self.assertAlmostEqual(p[name + "_voltage_v"], p[name + "_count"] * .0001875, delta=.00000051)

    def test_null_is_allowed_but_string_missing_is_rejected(self):
        p = demo_sample(10, faults=True)
        parsed = parse_packet(encoded(p))
        self.assertIsNone(parsed["mq135_1_voltage_v"])
        p["mq135_1_voltage_v"] = "None_V"
        with self.assertRaises(ProtocolError):
            parse_packet(encoded(p))

    def test_wrong_firmware_malformed_and_nonfinite_rejected(self):
        for raw in (b"boot:0x8", b"[]", b'{"type":"sample"}', b'\xff',
                    b'{"v":NaN}', b'{"v":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                parse_packet(raw)
        p = demo_sample(0)
        p["temperature_c"] = True
        with self.assertRaises(ProtocolError):
            parse_packet(encoded(p))

    def test_partial_multiple_crlf_and_oversize_resynchronization(self):
        framer = LineFramer()
        self.assertEqual(framer.feed(b"ab"), [])
        self.assertEqual(framer.feed(b"c\r\nd\ne"), [b"abc", b"d"])
        self.assertEqual(framer.feed(b"f\n"), [b"ef"])
        oversized = framer.feed(b"x" * (MAX_LINE_BYTES + 30))
        self.assertEqual(len(oversized), 1)
        with self.assertRaises(ProtocolError):
            parse_packet(oversized[0])
        self.assertEqual(framer.feed(b"discarded\nnext\n"), [b"next"])

    def test_gas_invalid_does_not_invalidate_temperature(self):
        p = demo_sample(15, faults=True)
        self.assertFalse(valid_value(p, "bme688_gas_ohm"))
        self.assertTrue(valid_value(p, "temperature_c"))


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.r = SessionRecorder(Path(self.temp.name), "DEMO", sync_seconds=.01)
        self.r.receive(encoded(demo_hello()))

    def tearDown(self):
        if not self.r.closed:
            self.r.finalize("user_stop")
        self.temp.cleanup()

    def test_missing_read_is_empty_in_csv_and_not_zero(self):
        self.r.receive(encoded(demo_sample(10, faults=True)))
        report = self.r.finalize("user_stop")
        with (self.r.directory / "samples.csv").open(encoding="utf-8-sig", newline="") as f:
            row = next(csv.DictReader(f))
        self.assertEqual(row["mq135_1_voltage_v"], "")
        self.assertEqual(row["mq135_1_count"], "")
        self.assertIn("i2c_conversion_read_failed", row["quality_flags"])
        self.assertEqual(report["values"]["mq135_1_voltage_v"]["valid_count"], 0)
        self.assertEqual(report["values"]["mq3_1_voltage_v"]["valid_count"], 1)

    def test_invalid_gas_remains_raw_but_is_not_in_valid_stats(self):
        p = demo_sample(15, faults=True)
        self.r.receive(encoded(p))
        report = self.r.finalize("user_stop")
        with (self.r.directory / "samples.csv").open(encoding="utf-8-sig", newline="") as f:
            row = next(csv.DictReader(f))
        self.assertEqual(float(row["bme688_gas_ohm"]), p["bme688_gas_ohm"])
        self.assertEqual(report["values"]["bme688_gas_ohm"]["valid_count"], 0)
        self.assertEqual(report["values"]["temperature_c"]["valid_count"], 1)

    def test_sequence_gap_duplicate_reset_and_invalid_line_are_distinct(self):
        for seq in (0, 1, 4, 4, 5):
            self.r.receive(encoded(demo_sample(seq)))
        p = demo_sample(0)
        p["boot_id"] = "NEW_BOOT"
        self.r.receive(encoded(p))
        self.r.receive(b"ROM boot log")
        report = self.r.finalize("user_stop")
        self.assertEqual(report["sample_count"], 6)
        self.assertEqual(report["missing_sequence_numbers"], 2)
        self.assertEqual(report["duplicate_or_out_of_order"], 1)
        self.assertEqual(report["device_boot_changes"], 1)
        self.assertEqual(report["parse_errors"], 1)

    def test_failure_finalizes_error_and_exact_transport_is_saved(self):
        exact = b"boot\r\n" + encoded(demo_sample(0)) + b"\r\n"
        self.r.transport(exact)
        self.r.receive(encoded(demo_sample(0)))
        self.r.finalize("acquisition_error")
        metadata = json.loads((self.r.directory / "metadata.json").read_text())
        self.assertEqual(metadata["status"], "ERROR")
        self.assertEqual((self.r.directory / "serial_bytes.bin").read_bytes(), exact)
        self.assertEqual(metadata["firmware"]["device_id"], "SIMULATED")


if __name__ == "__main__":
    unittest.main()
