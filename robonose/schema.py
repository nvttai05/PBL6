from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

def iso_now():
    return datetime.now(TZ).isoformat(timespec="microseconds")

BME_VALUES = ["temperature_c", "humidity_pct", "pressure_hpa", "gas_resistance_ohm",
              "gas_valid", "heater_stable", "new_data", "bme_status_bits",
              "bme_meas_index", "bme_gas_index", "bme_res_heat", "bme_idac", "bme_gas_wait"]
FIELDS = ["run_id", "seq", "timestamp", "elapsed_s", "phase_elapsed_s", "phase",
          "sensor_uptime_s", "loop_interval_s", "loop_duration_s", "schedule_lag_s",
          "pump_command"] + BME_VALUES
for device in ("bme", "mq135", "mq3"):
    FIELDS += [device + s for s in ("_read_started_at", "_read_elapsed_s", "_read_duration_s", "_status", "_error", "_fresh")]
    if device != "bme":
        FIELDS += [device + s for s in ("_adc_count", "_voltage_v", "_ao_voltage_v")]

def blank_sample():
    return {k: None for k in FIELDS}
