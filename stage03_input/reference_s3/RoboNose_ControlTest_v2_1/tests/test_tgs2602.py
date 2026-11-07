"""Protect sensor identity and the confirmed valve mapping in saved datasets."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from dashboard import read_recent_csv
from robonose_core import ProtocolError, SessionRecorder, demo_hello, demo_sample, parse_packet
from test_control import ack


class TgsDatasetTests(unittest.TestCase):
    def test_legacy_firmware_and_missing_tgs_are_rejected(self):
        packet = demo_sample(0)
        packet["schema"] = "robonose.control_test.v2"
        packet["mq135_2_count"] = packet.pop("tgs2602_count")
        packet["mq135_2_voltage_v"] = packet.pop("tgs2602_voltage_v")
        with self.assertRaisesRegex(ProtocolError, "Wrong firmware/schema"):
            parse_packet(json.dumps(packet).encode())
        packet["schema"] = demo_hello()["schema"]
        with self.assertRaisesRegex(ProtocolError, "tgs2602"):
            parse_packet(json.dumps(packet).encode())

    def test_a2_identity_and_valve_paths_in_samples_and_ack_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = SessionRecorder(Path(tmp), "DEMO")
            try:
                recorder.receive(json.dumps(demo_hello()).encode())
                for seq, energized in enumerate((False, True, False)):
                    packet = demo_sample(seq)
                    packet.update(tgs2602_count=4000 + seq,
                                  tgs2602_voltage_v=round((4000 + seq) * .0001875, 6),
                                  valve_energized=energized)
                    recorder.receive(json.dumps(packet).encode())
                    reply = ack({"request_id": seq + 1, "command": "VALVE"},
                                stamp=seq + 1, valve=energized)
                    recorder.receive(json.dumps(reply).encode())
            finally:
                report = recorder.finalize("user_stop")
            with (recorder.directory / "samples.csv").open(encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                self.assertNotIn("mq135_2_voltage_v", reader.fieldnames)
                rows = list(reader)
            self.assertEqual([r["valve_air_path_commanded"] for r in rows],
                             ["FILTERED_AIR", "SAMPLE", "FILTERED_AIR"])
            self.assertEqual([int(r["tgs2602_count"]) for r in rows], [4000, 4001, 4002])
            self.assertEqual(float(rows[0]["tgs2602_voltage_v"]), .75)
            self.assertEqual(report["values"]["tgs2602_voltage_v"]["valid_count"], 3)
            with (recorder.directory / "control_events.csv").open(encoding="utf-8-sig", newline="") as f:
                events = list(csv.DictReader(f))
            self.assertEqual([e["valve_air_path_commanded"] for e in events],
                             ["FILTERED_AIR", "SAMPLE", "FILTERED_AIR"])
            metadata = json.loads((recorder.directory / "metadata.json").read_text())
            self.assertEqual(metadata["channel_map"]["A2"], "tgs2602")
            self.assertEqual(metadata["valve_air_path_map"], {"OFF": "FILTERED_AIR", "ON": "SAMPLE"})
            saved, total = read_recent_csv(recorder.directory / "samples.csv")
            self.assertEqual(total, 3)
            self.assertEqual(saved[1]["tgs2602_count"], 4001)

    def test_old_mq135_csv_is_not_silently_relabelled_as_tgs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "samples.csv"
            path.write_text("host_elapsed_s,mq135_2_count,mq135_2_voltage_v\n0,4000,0.75\n")
            with self.assertRaisesRegex(ValueError, "does not match v2.1"):
                read_recent_csv(path)
