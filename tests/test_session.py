import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import pytest
from robonose.cli import parser
from robonose.config import load
from robonose.pump import Pump
from robonose.readers import SimReader
from robonose.session import Session

ROOT = Path(__file__).resolve().parents[1]

class Process:
    def __init__(self, root, extra=()):
        self.root = root
        self.output = root / "console.txt"
        self.f = self.output.open("w")
        self.p = subprocess.Popen([sys.executable, "-m", "robonose", "collect", "--sim", "--pump-disabled",
            "--sample-hz", "20", "--baseline", ".4", "--exposure", ".4", "--recovery", ".4",
            "--display-interval", ".1", "--output", str(root / "data"), *extra],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=self.f, stderr=subprocess.STDOUT, text=True)

    def text(self):
        return self.output.read_text()

    def wait(self, phrase, count=1, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.text().count(phrase) >= count:
                return
            if self.p.poll() is not None:
                pytest.fail(f"Process stopped {self.p.returncode}: {self.text()}")
            time.sleep(.02)
        pytest.fail(f"Timeout waiting {phrase}: {self.text()}")

    def send(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def runs(self):
        result = []
        for meta in (self.root / "data").glob("simulation/*/*/metadata.json"):
            m = json.loads(meta.read_text())
            if m["kind"] == "collect":
                result.append((meta.parent, m))
        return result

    def close(self):
        if self.p.poll() is None:
            self.p.send_signal(signal.SIGTERM)
            try:
                self.p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()
        self.p.stdin.close()
        self.f.close()

def csv_rows(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def test_interactive_waits_extensions_names_and_multiple_runs(tmp_path):
    app = Process(tmp_path, ["--sim-fail-every", "7"])
    try:
        app.wait("MONITOR |")
        path, _ = app.runs()[0]
        app.send("info sampling_method mở nắp đặt bông")
        app.send("durations .4 .4 .4")
        app.send("start")
        app.wait("Pha WAIT_EXPOSURE")
        n = len(csv_rows(path / "raw.csv"))
        time.sleep(.35)  # stdin deliberately stays open; no command
        rows = csv_rows(path / "raw.csv")
        assert len(rows) > n and any(r["phase"] == "WAIT_EXPOSURE" for r in rows)
        app.send("mark đưa mẫu bằng tay")
        app.send("expose")
        app.wait("Pha WAIT_RECOVERY")
        n = len(csv_rows(path / "raw.csv"))
        time.sleep(.3)
        assert len(csv_rows(path / "raw.csv")) > n
        app.send("recover")
        app.wait("Pha WAIT_FINISH")
        time.sleep(.25)
        app.send("extend .3")
        app.wait("Pha WAIT_FINISH", count=2)
        app.send("finish")
        app.wait("Đặt tên:")
        # Reads continue while naming; session log grows with WAIT_NAME.
        session_path = next(p.parent for p in (tmp_path / "data").glob("simulation/*/*/metadata.json")
                            if json.loads(p.read_text())["kind"] == "session")
        n = len(csv_rows(session_path / "raw.csv"))
        time.sleep(.3)
        assert len(csv_rows(session_path / "raw.csv")) > n
        assert any(r["phase"] == "WAIT_NAME" for r in csv_rows(session_path / "raw.csv"))
        app.send("name ../../mẫu áo")
        app.send("notes thu linh hoạt")
        app.wait("next để thu lượt mới")
        app.send("next")
        app.wait("Lượt mới:", count=2)
        app.send("start")
        app.wait("Pha BASELINE", count=2)
        time.sleep(.1)
        app.send("abort")
        app.wait("Đặt tên:", count=2)
        app.send("skip")
        app.send("skip")
        app.wait("next để thu lượt mới", count=2)
        app.send("quit")
        assert app.p.wait(timeout=40) == 0, app.text()
        runs = app.runs()
        assert len(runs) == 2
        completed = next((p,m) for p,m in runs if m["status"] == "COMPLETE")
        path, meta = completed
        assert path.name.startswith("mẫu_áo_")
        assert meta["original_name"] == "../../mẫu áo" and meta["notes"] == "thu linh hoạt"
        assert meta["sample"]["sampling_method"] == "mở nắp đặt bông"
        assert meta["extensions"][0]["duration_s"] == .3
        assert meta["durations"]["RECOVERY"]["planned_s"] == pytest.approx(.7)
        rows = csv_rows(path / "raw.csv")
        assert {r["phase"] for r in rows} >= {"MONITOR", "BASELINE", "WAIT_EXPOSURE", "EXPOSURE", "WAIT_RECOVERY", "RECOVERY", "WAIT_FINISH"}
        assert any(r["bme_status"] == "ERROR" and r["gas_resistance_ohm"] == "" for r in rows)
        assert [int(r["seq"]) for r in rows] == list(range(1, len(rows)+1))
        assert all(r["timestamp"].endswith("+07:00") and r["pump_command"] == "DISABLED" for r in rows)
        assert all(float(r["mq135_voltage_v"]) == int(r["mq135_adc_count"]) * 4.096 / 32768 for r in rows)
        for p,m in runs:
            assert m["rows"] == len(csv_rows(p / "raw.csv"))
            for file in ("raw.csv", "metadata.json", "events.csv", "summary.json", "signals.png", "normalized.png"):
                assert (p / file).stat().st_size > 0
        assert any(m["status"] == "ABORTED" for _,m in runs)
    finally:
        app.close()

@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signal_saves_partial_run(tmp_path, sig):
    app = Process(tmp_path)
    try:
        app.wait("MONITOR |")
        app.send("durations 30 60 60")
        app.send("start")
        app.wait("Pha BASELINE")
        time.sleep(.2)
        app.p.send_signal(sig)
        assert app.p.wait(timeout=40) == 0, app.text()
        path, meta = app.runs()[0]
        assert meta["status"] == "ABORTED" and meta["rows"] > 0
        assert "signal" in meta["end_reason"]
        assert (path / "signals.png").exists()
        assert any(r["event"] == "run_end" for r in csv_rows(path / "events.csv"))
    finally:
        app.close()

def test_cancel_naming_preserves_complete(tmp_path):
    app = Process(tmp_path)
    try:
        app.wait("MONITOR |")
        app.send("start")
        app.wait("Pha WAIT_EXPOSURE")
        app.send("expose")
        app.wait("Pha WAIT_RECOVERY")
        app.send("recover")
        app.wait("Pha WAIT_FINISH")
        app.send("finish")
        app.wait("Đặt tên:")
        app.p.send_signal(signal.SIGINT)
        assert app.p.wait(timeout=40) == 0, app.text()
        path, meta = app.runs()[0]
        assert meta["status"] == "COMPLETE"
        assert (path / "summary.json").exists()
    finally:
        app.close()

def test_worker_exception_cleanup_and_off(tmp_path, monkeypatch):
    from tests.test_core import FakeDevice
    class Broken(SimReader):
        def read(self, *args):
            raise OSError("fatal reader failure")
    monkeypatch.setattr("robonose.session.analyze", lambda p: None)
    args = parser().parse_args(["collect", "--sim", "--auto", "--output", str(tmp_path)])
    cfg = load()
    pump = Pump({"enabled": True, "confirmed": True, "gpio_bcm": 12, "active_high": True}, "hardware", FakeDevice)
    pump.set(True)
    session = Session(args, cfg, Broken(cfg), pump)
    assert session.run_session() == 1
    assert pump.device.commands[-2:] == ["OFF", "CLOSE"]
    assert session.run.meta["status"] == "ERROR"

def test_sim_cli_without_any_hardware_import(tmp_path):
    script = '''import builtins
original = builtins.__import__
def guard(name, *a, **kw):
    if name.split('.')[0] in ('smbus2','gpiozero','lgpio','board','busio'):
        raise AssertionError('hardware import in sim: ' + name)
    return original(name, *a, **kw)
builtins.__import__ = guard
from robonose.cli import main
raise SystemExit(main())
'''
    result = subprocess.run([sys.executable, "-c", script, "collect", "--sim", "--auto", "--baseline", ".2",
        "--exposure", ".2", "--recovery", ".2", "--sample-hz", "30", "--auto-warmup", ".1", "--auto-wait", ".1",
        "--output", str(tmp_path)], cwd=ROOT, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr

def test_auto_rejected_for_hardware_before_open(tmp_path):
    result = subprocess.run([sys.executable, "-m", "robonose", "collect", "--hardware", "--auto"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1 and "chỉ dùng mô phỏng" in result.stderr
