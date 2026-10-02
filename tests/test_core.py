import builtins
import csv
import json
from pathlib import Path
import time
import pytest
from robonose.config import load, validate
from robonose.pump import Pump
from robonose.readers import SimReader, ADS1115, BoschBME, BMEResult, FSR
from robonose.schema import blank_sample
from robonose.state import StateMachine
from robonose.writer import RunWriter, safe_name

def test_timer_waits_extensions_and_wall_clock_independence():
    s = StateMachine(100, {"BASELINE": 30, "EXPOSURE": 60, "RECOVERY": 60})
    s.command("start", 200)
    assert s.tick(229.999) is None
    assert s.tick(230) == ("BASELINE", "WAIT_EXPOSURE")
    assert s.tick(1000) is None
    s.command("expose", 1000)
    s.tick(1060)
    s.command("recover", 2000)
    s.tick(2060)
    s.command("extend 30", 3000)
    assert s.remaining(3010) == 20
    s.tick(3030)
    assert [i["planned_s"] for i in s.history if i["phase"] == "RECOVERY"] == [60, 30]
    assert s.durations["RECOVERY"] == 60
    assert s.history[1]["actual_s"] == 30

@pytest.mark.parametrize("command", ["expose", "recover", "extend 30"])
def test_phase_guard(command):
    with pytest.raises(ValueError):
        StateMachine(0, {"BASELINE": 1, "EXPOSURE": 1, "RECOVERY": 1}).command(command, 1)

@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_duration(value):
    cfg = load()
    cfg["baseline_s"] = value
    with pytest.raises(ValueError):
        validate(cfg)

def test_sim_and_disabled_never_import_hardware(monkeypatch, capsys):
    real_import = builtins.__import__
    def guard(name, *a, **kw):
        if name.split(".")[0] in ("smbus2", "gpiozero", "lgpio", "board", "busio"):
            raise AssertionError("hardware import in sim: " + name)
        return real_import(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", guard)
    cfg = load()
    row = SimReader(cfg).read("MONITOR", time.monotonic())
    assert row["bme_fresh"] is True
    assert Pump(cfg["pump"], "hardware").commanded == "DISABLED"
    cfg["pump"].update(enabled=True, confirmed=True, gpio_bcm=12, active_high=True)
    assert Pump(cfg["pump"], "sim").device is None
    from robonose.cli import doctor
    assert doctor(cfg) == 0

def test_sim_repeatable_and_error_is_null():
    cfg = load()
    a, b = SimReader(cfg, fail_every=2), SimReader(cfg, fail_every=2)
    for index in range(3):
        x, y = a.read("EXPOSURE", 0), b.read("EXPOSURE", 0)
        assert x["gas_resistance_ohm"] == y["gas_resistance_ohm"]
        assert x["mq135_adc_count"] == y["mq135_adc_count"]
        assert x["mq135_voltage_v"] == x["mq135_adc_count"] * FSR[1] / 32768
        assert x["mq135_ao_voltage_v"] is None
        if index == 1:
            assert x["temperature_c"] is None and x["gas_resistance_ohm"] is None
            assert x["bme_status"] == "ERROR" and x["bme_error"]
            assert x["bme_fresh"] is False

class FakeDevice:
    def __init__(self, **kwargs):
        self.kwargs, self.commands = kwargs, []
        self.fail = False
    def on(self):
        self.commands.append("ON")
    def off(self):
        self.commands.append("OFF")
        if self.fail:
            raise OSError("OFF failure")
    def close(self):
        self.commands.append("CLOSE")

def test_pump_off_and_failure():
    cfg = {"enabled": True, "confirmed": True, "gpio_bcm": 12, "active_high": False}
    p = Pump(cfg, "hardware", FakeDevice)
    assert p.device.kwargs == {"pin": 12, "active_high": False, "initial_value": False}
    p.set(True)
    assert p.commanded == "ON"
    p.close()
    assert p.device.commands == ["ON", "OFF", "CLOSE"]
    p.device.fail = True
    assert p.off_best_effort() == "OFF failure"
    assert p.commanded == "UNKNOWN"

def test_pump_config_required():
    cfg = load()
    cfg["pump"]["enabled"] = True
    with pytest.raises(ValueError, match="confirmed"):
        validate(cfg)

def test_ads_one_conversion_count_voltage_and_config():
    h = load()["hardware"]
    adc = ADS1115(None, h)
    writes, reads = [], []
    def write(reg, val):
        writes.append((reg, val))
    def read(reg):
        reads.append(reg)
        return writes[-1][1] if reg == 1 else 12345
    adc.write_reg, adc.read_reg = write, read
    x = adc.read("mq135")
    assert reads.count(0) == 1
    assert x["mq135_adc_count"] == 12345
    assert x["mq135_voltage_v"] == 12345 * 4.096 / 32768
    assert writes == [(1, 0xC383)]  # A0, PGA1, single-shot, 128 SPS, comparator disabled
    adc.read_reg = lambda reg: 0
    with pytest.raises(RuntimeError, match="readback"):
        adc.read("mq3")

def test_ads_timeout(monkeypatch):
    adc = ADS1115(None, load()["hardware"])
    adc.write_reg = lambda reg, val: None
    adc.read_reg = lambda reg: 0x4383
    ticks = iter([0., 1.])
    monkeypatch.setattr("robonose.readers.time.monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError):
        adc.read("mq135")

def test_bosch_units_flags_and_stale():
    class Lib:
        code = 0
        def rn_read(self, ptr, result):
            r = result._obj
            r.temperature, r.pressure_pa, r.humidity, r.gas_ohm = 25.5, 100800., 55.2, 123456.
            r.status, r.index = 0xB0, 7
            return self.code
    b = BoschBME.__new__(BoschBME)
    b.ptr, b.lib = 1, Lib()
    x = b.read()
    assert x["pressure_hpa"] == 1008 and x["humidity_pct"] == 55.2
    assert x["gas_resistance_ohm"] == 123456 and x["gas_valid"] and x["heater_stable"]
    b.lib.code = 2
    x = b.read()
    assert x["bme_status"] == "STALE" and x["bme_fresh"] is False
    assert "gas_resistance_ohm" not in x

def make_writer(tmp_path):
    cfg = load()
    return RunWriter(tmp_path, "sim", cfg, {"backend": "sim"}, run_start=0)

def test_incremental_writer_abort_and_traversal(tmp_path):
    w = make_writer(tmp_path)
    row = blank_sample()
    row.update(timestamp="2026-10-02T12:00:00+07:00", elapsed_s=.1, phase="MONITOR", phase_elapsed_s=.1)
    w.row(row)
    assert len(list(csv.DictReader((w.path / "raw.csv").open()))) == 1
    s = StateMachine(0, {"BASELINE": 30, "EXPOSURE": 60, "RECOVERY": 60})
    s.command("start", 1)
    w.finish(s, "ABORTED", 2, "test")
    old = w.path
    w.finalize_name("../../áo bông / ..", "ghi chú")
    assert w.path.parent == old.parent
    assert w.path.name.startswith("áo_bông_")
    meta = json.loads((w.path / "metadata.json").read_text())
    assert meta["status"] == "ABORTED" and meta["rows"] == 1
    assert meta["original_name"] == "../../áo bông / .."
    assert meta["durations"]["BASELINE"]["actual_s"] == 1

def test_duplicate_name_keeps_existing_and_run_id(tmp_path):
    w = make_writer(tmp_path)
    state = StateMachine(0, {"BASELINE": 1, "EXPOSURE": 1, "RECOVERY": 1})
    w.finish(state, "ABORTED", 1)
    old = w.path
    occupied = old.parent / ("trùng_" + w.base_name)
    occupied.mkdir()
    (occupied / "keep.txt").write_text("original")
    run_id = w.run_id
    w.finalize_name("trùng")
    assert w.path == old and w.path.exists()
    assert (occupied / "keep.txt").read_text() == "original"
    assert w.meta["rename_error"] and w.run_id == run_id

def test_same_display_names_create_distinct_runs(tmp_path):
    paths = []
    for _ in range(2):
        w = make_writer(tmp_path)
        w.finish(StateMachine(0, {"BASELINE": 1, "EXPOSURE": 1, "RECOVERY": 1}), "ABORTED", 1)
        paths.append(w.finalize_name("mẫu giống"))
    assert paths[0] != paths[1] and all(p.exists() for p in paths)

def test_long_unicode_name_has_valid_byte_length():
    assert len(safe_name("ậ" * 100).encode("utf-8")) <= 160
