"""Canonical v1 columns and strict finite/null serialization."""
import math
from .config import CHANNELS

SCHEMA = "robonose.dataset.v1"
SIGNALS = [f"{sensor}_voltage_v" for sensor in CHANNELS.values()] + [
    "gas_resistance_ohm", "temperature_c", "humidity_pct", "pressure_hpa"]
DEVICES = list(CHANNELS.values()) + ["bme688"]
BASE_COLUMNS = [
    "schema", "mode", "session_id", "boot_id", "seq", "timestamp", "mono_s",
    "received_at", "received_mono_s", "cycle_end_mono_s", "schedule_lag_s", "skipped_cycles",
    "trial_id", "phase", "segment_id", "context_epoch", "phase_elapsed_s",
    "context_straddled", "pump_pwm_pct", "valve_energized", "air_path_commanded",
    "config_hash", "profile_id", "quality_flags",
    "gas_resistance_ohm", "temperature_c", "humidity_pct", "pressure_hpa",
    "new_data", "gas_valid", "heater_stable", "bme_status_bits", "bme_meas_index",
]
COLUMNS = BASE_COLUMNS + [f"{s}_{suffix}" for s in CHANNELS.values() for suffix in ("adc_count", "voltage_v")] + [
    f"{s}_{suffix}" for s in DEVICES for suffix in
    ("read_started_mono_s", "read_duration_s", "status", "error", "fresh", "valid")]


def finite_or_none(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite_or_none(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_or_none(val) for val in value]
    return value


def valid_signal(row, signal):
    device = next((name for name in CHANNELS.values() if signal.startswith(name + "_")), "bme688")
    valid = row.get(f"{device}_valid")
    fresh = row.get(f"{device}_fresh")
    if valid not in (True, "True", "true", 1) or fresh not in (True, "True", "true", 1):
        return False
    if signal == "gas_resistance_ohm" and row.get("gas_valid") not in (True, "True", "true", 1):
        return False
    try:
        return row.get(signal) not in (None, "") and math.isfinite(float(row[signal]))
    except (ValueError, TypeError):
        return False
