import csv
import json
import queue
import threading
import time
from pathlib import Path
import pytest
from robonose.analysis import analyze
from robonose.cli import parser
from robonose.config import load
from robonose.readers import ADS1115, FSR, SimReader, timing, BoschBME
from robonose.schema import blank_sample
from robonose.session import Acquisition, Context, Session
from robonose.state import StateMachine
from tests.test_analysis import dataset
from tests.test_session import Process, csv_rows

def test_late_tick_ends_phase_at_deadline():
    s = StateMachine(100, {"BASELINE": 1, "EXPOSURE": 2, "RECOVERY": 3})
    s.command("start", 100)
    s.tick(105)
    assert s.history[-1]["actual_s"] == 1
    assert s.phase == "WAIT_EXPOSURE" and s.since == 101
    s.command("expose", 106)
    s.tick(120)
    assert s.history[-1]["actual_s"] == 2 and s.since == 108

def test_worker_labels_deadline_without_ui_poll():
    reader = SimReader(load())
    now = time.monotonic()
    acq = Acquisition(reader, 100, now, Context(None, "BASELINE", now, "BASELINE", "DISABLED", now+.03))
    acq.thread.start()
    rows = []
    try:
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            _, row, ctx = acq.items.get(timeout=1)
            rows.append(row)
            if row["phase"] == "WAIT_EXPOSURE":
                assert row["phase_elapsed_s"] == pytest.approx(row["elapsed_s"]-.03)
                break
        assert any(r["phase"] == "WAIT_EXPOSURE" for r in rows)
        assert all(r["elapsed_s"] < .03 for r in rows if r["phase"] == "BASELINE")
    finally:
        acq.stop.set()
        acq.thread.join(timeout=2)

def test_fatal_reader_during_finish_preserves_error_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("robonose.session.analyze", lambda p: None)
    entered = threading.Event()
    class BrokenOnFinish(SimReader):
        calls = 0
        def read(self, *a):
            self.calls += 1
            if self.calls == 3:
                entered.set()
                end = time.monotonic()+2
                while session.acq.context.run is not None and time.monotonic() < end:
                    time.sleep(.001)
                raise OSError("failure while finishing")
            return super().read(*a)
    class EndingSession(Session):
        def auto(self, now):
            if entered.is_set() and self.run:
                self.command("abort")
    cfg = load()
    cfg["sample_hz"] = 50
    args = parser().parse_args(["collect", "--sim", "--auto", "--output", str(tmp_path)])
    session = EndingSession(args, cfg, reader=BrokenOnFinish(cfg))
    assert session.run_session() == 1
    meta_path = next(p for p in tmp_path.glob("simulation/*/*/metadata.json") if json.loads(p.read_text())["kind"] == "collect")
    meta = json.loads(meta_path.read_text())
    assert meta["status"] == "ERROR" and meta["rows"] == 2
    assert len(csv_rows(meta_path.parent / "raw.csv")) == 2
    assert session.finishing.closed
    assert any(r["event"] == "run_end" for r in csv_rows(meta_path.parent / "events.csv"))

@pytest.mark.parametrize("gain", list(FSR))
def test_negative_adc_count_and_voltage_same_conversion(gain):
    h = load()["hardware"]
    h["ads_gain"] = gain
    h["mq3_divider_factor"] = 2.5
    adc = ADS1115(None, h)
    written, conversions = [], []
    adc.write_reg = lambda reg, val: written.append(val)
    def read(reg):
        if reg == 1:
            return written[-1]
        conversions.append(reg)
        return 0xffff  # signed -1, not 65535
    adc.read_reg = read
    row = adc.read("mq3")
    assert conversions == [0]
    assert row["mq3_adc_count"] == -1
    assert row["mq3_voltage_v"] == -FSR[gain]/32768
    assert row["mq3_ao_voltage_v"] == row["mq3_voltage_v"]*2.5

def test_auc_never_bridges_recovery_segments_without_wait_sample(tmp_path, monkeypatch):
    monkeypatch.setattr("robonose.analysis.plot", lambda *a: None)
    path = dataset(tmp_path)
    rows = csv_rows(path / "raw.csv")
    fields = list(rows[0])
    for t, value in ((13,20), (14,18), (15,16)):
        row = dict(rows[-1], elapsed_s=t, phase_elapsed_s=t-13)
        for key in ("gas_resistance_ohm", "mq135_voltage_v", "mq3_voltage_v"):
            row[key] = value
        rows.append(row)
    with (path / "raw.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    meta = json.loads((path / "metadata.json").read_text())
    meta["phase_intervals"] += [{"phase":"RECOVERY", "start_s":13, "end_s":16, "actual_s":3, "planned_s":3}]
    (path / "metadata.json").write_text(json.dumps(meta))
    result = analyze(path)
    metrics = result["signals"]["gas_resistance_ohm"]["recovery"]["metrics"]
    assert metrics["auc_delta_signal_s"] == 22  # 6 + 16; no 11 from the unsampled wait
    assert metrics["auc_covered_s"] == 4

def test_partial_baseline_stats_have_reason_and_null_values(tmp_path, monkeypatch):
    monkeypatch.setattr("robonose.analysis.plot", lambda *a: None)
    path = dataset(tmp_path)
    meta = json.loads((path / "metadata.json").read_text())
    next(i for i in meta["phase_intervals"] if i["phase"] == "BASELINE")["actual_s"] = 1
    (path / "metadata.json").write_text(json.dumps(meta))
    result = analyze(path)
    for baseline in [s["baseline"] for s in result["signals"].values()] + list(result["environment_baseline"].values()):
        assert baseline["n"] == 3 and baseline["mean"] is None and baseline["reason"]

def test_float_roundoff_does_not_make_completed_phase_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr("robonose.analysis.plot", lambda *a: None)
    path = dataset(tmp_path)
    meta = json.loads((path / "metadata.json").read_text())
    for interval in meta["phase_intervals"]:
        if interval["planned_s"] is not None:
            interval["actual_s"] -= 1e-13
    (path / "metadata.json").write_text(json.dumps(meta))
    assert analyze(path)["signals"]["gas_resistance_ohm"]["exposure"]["metrics"] is not None

def test_session_does_not_mix_baselines_across_trials(tmp_path, monkeypatch):
    monkeypatch.setattr("robonose.analysis.plot", lambda *a: None)
    path = dataset(tmp_path)
    meta = json.loads((path / "metadata.json").read_text())
    meta["kind"] = "session"
    (path / "metadata.json").write_text(json.dumps(meta))
    result = analyze(path)
    assert all(s["baseline"]["mean"] is None and s["reason"] for s in result["signals"].values())

def test_split_utf8_command_and_waiting_does_not_block(tmp_path):
    app = Process(tmp_path)
    try:
        app.wait("MONITOR |")
        path, _ = app.runs()[0]
        n = len(csv_rows(path / "raw.csv"))
        text = "mark áo vải\n".encode("utf-8")
        split = text.index("á".encode("utf-8"))+1
        app.p.stdin.buffer.write(text[:split])
        app.p.stdin.buffer.flush()
        time.sleep(.3)  # incomplete command and incomplete UTF-8 character
        assert len(csv_rows(path / "raw.csv")) > n
        app.p.stdin.buffer.write(text[split:])
        app.p.stdin.buffer.flush()
        time.sleep(.1)
        app.send("quit")
        assert app.p.wait(timeout=40) == 0, app.text()
        marker = next(r for r in csv_rows(path / "events.csv") if r["event"] == "marker")
        assert json.loads(marker["details_json"])["text"] == "áo vải"
    finally:
        app.close()

def test_nonfinite_measurement_is_null_and_has_error():
    row = blank_sample()
    timing(row, "bme", lambda: {"temperature_c": float("nan"), "pressure_hpa": float("inf"),
        "humidity_pct": 55., "gas_resistance_ohm": 12345., "gas_valid": False}, time.monotonic())
    assert row["temperature_c"] is None and row["pressure_hpa"] is None
    assert row["humidity_pct"] == 55. and row["gas_resistance_ohm"] == 12345.
    assert row["bme_status"] == "ERROR" and not row["bme_fresh"]
    assert row["bme_error"] and row["gas_valid"] is False

def test_gas_invalid_value_is_preserved_with_actual_flags():
    class Lib:
        def rn_read(self, ptr, result):
            r = result._obj
            r.status = 0x90  # new + heater stable; no gas_valid
            r.gas_ohm, r.pressure_pa, r.temperature, r.humidity = 54321., 100000., 25., 50.
            return 0
    bme = BoschBME.__new__(BoschBME)
    bme.ptr, bme.lib = 1, Lib()
    row = blank_sample()
    timing(row, "bme", bme.read, time.monotonic())
    assert row["gas_resistance_ohm"] == 54321.
    assert row["bme_status"] == "OK" and row["bme_fresh"]
    assert row["gas_valid"] is False and row["heater_stable"] is True
