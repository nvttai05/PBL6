import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from control_link import ControlLink
from robonose_core import SCHEMA, demo_hello, demo_sample, parse_packet, ProtocolError


def ack(request, stamp=100, pump=0, valve=False, ok=True, boot="SIMULATED"):
    return {"type": "ack", "schema": SCHEMA, "boot_id": boot,
            "request_id": request["request_id"], "command": request["command"], "ok": ok,
            "error": "" if ok else "test_rejection", "device_ms": stamp,
            "pump_pwm_pct": pump, "pump_pwm_duty": (pump * 1023 + 50) // 100,
            "valve_energized": valve, "control_ready": True, "failsafe_active": False,
            "control_revision": stamp, "lease_remaining_ms": 15000}


def synchronized_link():
    link = ControlLink()
    link.on_packet(demo_hello(), now=1)
    wire, request = link.next_wire(1)
    assert request["command"] == "ALL_OFF"
    link.on_packet(ack(request), now=1.1)
    return link


class ControlProtocolTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("g++"), "Optional hardware API test needs g++")
    def test_pwm_core_2_and_3_api_and_inactive_fallback(self):
        root = Path(__file__).resolve().parents[1]
        firmware, stubs = root / "firmware/RoboNose_SensorTest", root / "tests/output_stubs"
        with tempfile.TemporaryDirectory() as tmp:
            for major in (2, 3):
                program = Path(tmp) / f"pwm_api_{major}"
                subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                                f"-DESP_ARDUINO_VERSION_MAJOR={major}", "-I", str(stubs), "-I", str(firmware),
                                str(stubs / "test_output_hardware.cpp"), str(firmware / "output_hardware.cpp"),
                                "-o", str(program)], check=True, capture_output=True)
                subprocess.run([str(program)], check=True, capture_output=True)

    def test_initial_sync_is_off_and_ack_required(self):
        link = ControlLink()
        self.assertFalse(link.request("PUMP", 100))
        # First sample can arrive before INFO response; initial sync must still work.
        link.on_packet(demo_sample(0), now=1)
        link.on_packet(demo_hello(), now=1.1)
        wire, request = link.next_wire(1.2)
        self.assertIn(b"ALL_OFF", wire)
        self.assertFalse(link.snapshot()["enabled"])
        link.on_packet(ack(request), now=1.3)
        self.assertTrue(link.snapshot()["enabled"])

    def test_all_off_cancels_queued_restart_commands(self):
        link = synchronized_link()
        self.assertTrue(link.request("PUMP", 75))
        self.assertTrue(link.request("VALVE", 1))
        self.assertTrue(link.request("ALL_OFF"))
        wire, request = link.next_wire(2)
        self.assertEqual(request["command"], "ALL_OFF")
        link.on_packet(ack(request, 200), now=2.1)
        self.assertIsNone(link.next_wire(2.2))
        self.assertEqual(link.snapshot()["confirmed"]["pump_pwm_pct"], 0)

    def test_all_off_is_accepted_even_when_queue_is_full(self):
        link = synchronized_link()
        for i in range(16):
            self.assertTrue(link.request("PUMP", i))
        self.assertFalse(link.request("PUMP", 90))
        self.assertTrue(link.request("ALL_OFF"))
        self.assertEqual(link.next_wire(2)[1]["command"], "ALL_OFF")

    def test_ack_with_wrong_output_value_forces_off(self):
        link = synchronized_link()
        link.request("PUMP", 60)
        _, request = link.next_wire(2)
        link.on_packet(ack(request, 300, pump=20), now=2.1)
        self.assertFalse(link.snapshot()["enabled"])
        self.assertEqual(link.next_wire(2.2)[1]["command"], "ALL_OFF")

    def test_stale_connection_cannot_accept_new_on_request(self):
        link = synchronized_link()
        link.last_live_rx = 0
        self.assertFalse(link.request("PUMP", 100))
        self.assertTrue(link.request("ALL_OFF"))

    def test_acknowledged_changes_and_stale_sensor_snapshot(self):
        link = synchronized_link()
        link.request("PUMP", 60)
        _, request = link.next_wire(2)
        link.on_packet(ack(request, 300, pump=60), now=2.1)
        old = demo_sample(0)
        old["device_cycle_end_ms"] = 200
        link.on_packet(old, now=2.2)
        self.assertEqual(link.snapshot()["confirmed"]["pump_pwm_pct"], 60)

    def test_timeout_requests_off_and_never_retries_on(self):
        link = synchronized_link()
        link.request("PUMP", 100)
        link.next_wire(2)
        wire, request = link.next_wire(5.1)
        self.assertEqual(request["command"], "ALL_OFF")
        self.assertFalse(link.snapshot()["enabled"])

    def test_reboot_does_not_restore_previous_targets(self):
        link = synchronized_link()
        link.request("PUMP", 100)
        link.request("VALVE", 1)
        new = demo_hello(); new["boot_id"] = "REBOOT"
        link.on_packet(new, now=3)
        self.assertFalse(link.snapshot()["enabled"])
        self.assertIsNone(link.next_wire(3.1))
        self.assertFalse(link.request("PUMP", 100))
        link.request("ALL_OFF")
        _, request = link.next_wire(3.2)
        link.on_packet(ack(request, 100, boot="REBOOT"), now=3.3)
        self.assertTrue(link.snapshot()["enabled"])

    def test_invalid_types_and_ack_rejected(self):
        link = synchronized_link()
        for command, value in (("PUMP", True), ("PUMP", -1), ("PUMP", 101), ("VALVE", 2)):
            with self.subTest(command=command, value=value), self.assertRaises(ValueError):
                link.request(command, value)
        invalid = ack({"request_id": 1, "command": "PUMP"})
        invalid["valve_energized"] = "True"
        with self.assertRaises(ProtocolError):
            parse_packet(json.dumps(invalid).encode())

    @unittest.skipUnless(shutil.which("g++"), "Optional native control test needs g++")
    def test_native_watchdog_pwm_and_strict_parser(self):
        root = Path(__file__).resolve().parents[1]
        firmware = root / "firmware/RoboNose_SensorTest"
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "actuators"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I", str(firmware),
                            str(root / "tests/native/test_actuators.cpp"), str(firmware / "actuators.cpp"),
                            str(firmware / "command_parser.cpp"), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)
