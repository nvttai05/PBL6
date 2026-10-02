import csv
import hashlib
import json
from pathlib import Path
import pytest
from robonose.analysis import analyze
from robonose.config import load
from robonose.schema import blank_sample
from robonose.state import StateMachine
from robonose.writer import RunWriter

def dataset(root, values=None, partial_extension=False):
    cfg = load()
    cfg.update(baseline_s=3., exposure_s=3., recovery_s=3.)
    w = RunWriter(root, "sim", cfg, {"backend": "sim"}, run_start=0)
    s = StateMachine(0, {"BASELINE": 3, "EXPOSURE": 3, "RECOVERY": 3})
    s.command("start", 1)
    s.tick(4)
    s.command("expose", 5)
    s.tick(8)
    s.command("recover", 9)
    s.tick(12)
    vals = values or [10, 10, 10, 12, 14, 16, 15, 13, 11]
    for i, (t, phase, val) in enumerate(zip([1,2,3,5,6,7,9,10,11], ["BASELINE"]*3 + ["EXPOSURE"]*3 + ["RECOVERY"]*3, vals)):
        row = blank_sample()
        row.update(elapsed_s=t, phase=phase, phase_elapsed_s=i % 3, timestamp="2026-10-02T12:00:00+07:00",
            gas_resistance_ohm=val, mq135_voltage_v=val, mq3_voltage_v=val,
            temperature_c=25, humidity_pct=55, pressure_hpa=1008,
            gas_valid=True, heater_stable=True, new_data=True)
        for device in ("bme", "mq135", "mq3"):
            row[device + "_status"] = "OK"
            row[device + "_fresh"] = True
        w.row(row)
    if partial_extension:
        s.command("extend 5", 13)
        w.finish(s, "ABORTED", 14)
    else:
        w.finish(s, "COMPLETE", 13)
    return w.path

def test_real_time_statistics_pngs_and_raw_unchanged(tmp_path):
    path = dataset(tmp_path)
    before = hashlib.sha256((path / "raw.csv").read_bytes()).hexdigest()
    result = analyze(path)
    s = result["signals"]["gas_resistance_ohm"]
    assert s["baseline"]["mean"] == 10
    assert s["baseline"]["std"] == 0
    e = s["exposure"]["metrics"]
    assert e["delta_max"] == 6 and e["delta_min"] == 2
    assert e["slope_per_s"] == pytest.approx(2)
    assert e["auc_delta_signal_s"] == 8 and e["auc_covered_s"] == 2
    assert e["maximum_at_elapsed_s"] == 7
    assert s["recovery"]["metrics"]["end_deviation"] == 1
    assert s["recovery"]["metrics"]["trend_toward_baseline"]
    for name in ("signals.png", "normalized.png"):
        assert (path / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert (path / name).stat().st_size > 1000
    assert hashlib.sha256((path / "raw.csv").read_bytes()).hexdigest() == before
    assert (path / "summary.json").exists()

def test_partial_extension_returns_null_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr("robonose.analysis.plot", lambda *a: None)
    result = analyze(dataset(tmp_path, partial_extension=True))
    for s in result["signals"].values():
        assert s["recovery"]["metrics"] is None
        assert s["recovery"]["reason"]

def test_zero_baseline_percent_null(tmp_path):
    path = dataset(tmp_path, values=[0,0,0,1,2,3,2,1,0])
    result = analyze(path)
    for s in result["signals"].values():
        assert s["exposure"]["metrics"]["delta_max"] == 3
        assert s["exposure"]["metrics"]["delta_max_pct"] is None
        assert s["exposure"]["metrics"]["percent_reason"]
    assert (path / "normalized.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

def test_invalid_rows_not_bridged_or_used_as_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("robonose.analysis.plot", lambda *a: None)
    path = dataset(tmp_path)
    with (path / "raw.csv").open(newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    # Fixture mutation only: inject a heater-invalid measurement and keep its value.
    rows[4]["heater_stable"] = "False"
    rows[4]["gas_resistance_ohm"] = "999999"
    with (path / "raw.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    result = analyze(path)
    gas = result["signals"]["gas_resistance_ohm"]["exposure"]["metrics"]
    assert gas["n"] == 2 and gas["maximum"] == 16
    assert gas["auc_delta_signal_s"] is None
    assert any("không hợp lệ" in warning for warning in result["warnings"])

def test_missing_baseline(tmp_path):
    w = RunWriter(tmp_path, "sim", load(), {}, run_start=0)
    w.finish(StateMachine(0, {"BASELINE": 30, "EXPOSURE": 60, "RECOVERY": 60}), "ABORTED", 1)
    result = analyze(w.path)
    assert all(s["exposure"] is None and s["reason"] for s in result["signals"].values())
    assert (w.path / "signals.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (w.path / "normalized.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
