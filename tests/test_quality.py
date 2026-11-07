import pytest
from robonose_s3.clock import FakeClock
from robonose_s3.config import Config
from robonose_s3.quality import covered_seconds, evaluate, statistics_for
from robonose_s3.simulated import SimDevice
from robonose_s3.state import StateMachine


def fixtures(count=30):
    config, clock = Config(), FakeClock()
    state = StateMachine(config)
    state.start_session(0)
    device = SimDevice(config, "quality-fixture", clock)
    return [device.read(t, state.context(t)) for t in range(count)]


def test_live_quality_requires_window_and_analog_never_claims_stable():
    assert evaluate(fixtures(5), 4, Config())["overall"] == "WARMING_UP"
    quality = evaluate(fixtures(), 29, Config())
    assert quality["signals"]["tgs2602_voltage_v"]["status"] == "UNCONFIGURED"
    assert quality["signals"]["temperature_c"]["status"] == "STABLE"
    assert quality["signals"]["gas_resistance_ohm"]["status"] == "STABLE"
    assert quality["signals"]["pressure_hpa"]["status"] == "UNCONFIGURED"


def test_gaps_invalid_and_heater_stability_do_not_mask_drift():
    rows = fixtures()
    for row in rows:
        row["temperature_c"] = 25 + row["mono_s"] / 2
        row["heater_stable"] = True
    quality = evaluate(rows, 29, Config())
    assert quality["signals"]["temperature_c"]["status"] == "WARN"
    assert "TEMPERATURE_ABOVE_35_ADVISORY" in quality["signals"]["temperature_c"]["reasons"]
    for row in rows[:20]:
        row["gas_valid"] = False
    quality = evaluate(rows, 29, Config())
    assert quality["signals"]["gas_resistance_ohm"]["status"] == "INSUFFICIENT"
    assert quality["signals"]["gas_resistance_ohm"]["valid_n"] == 10


def test_union_coverage_and_noise_fixture():
    assert covered_seconds([0, 0, 1, 10], 0, 12, 1) == 3
    stats = statistics_for([(0, 1), (1, 3), (2, 5)])
    assert stats["mean"] == stats["median"] == 3
    assert stats["std"] == 2 and stats["range"] == 4
    assert stats["slope_per_min"] == 120 and stats["noise"] == 0


def test_zero_gas_baseline_returns_reason():
    rows = fixtures()
    for row in rows:
        row["gas_resistance_ohm"] = 0
    quality = evaluate(rows, 29, Config())
    assert quality["signals"]["gas_resistance_ohm"]["reasons"] == ["BASELINE_NEAR_ZERO"]
