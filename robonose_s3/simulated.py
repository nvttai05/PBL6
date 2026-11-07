import math
import uuid
from .config import CHANNELS, LSB_V, PROFILE
from .schema import SCHEMA


class SimDevice:
    """Deterministic signals. Status injection preserves nulls and soft suspect peaks."""
    def __init__(self, config, session_id, clock):
        self.config, self.session_id, self.clock = config, session_id, clock
        self.boot_id = str(uuid.uuid4())
        self.seq = 0
        self.init_count = 1
        self.closed = False

    def read(self, now, context, errors=None):
        if self.closed:
            raise RuntimeError("SimDevice closed")
        self.seq += 1
        errors = errors or {}
        response = 0.25 * (1 - math.exp(-context["phase_elapsed_s"] / 15)) if context["phase"] == "EXPOSURE" else 0
        row = {"schema": SCHEMA, "mode": "SIMULATED", "session_id": self.session_id,
               "boot_id": self.boot_id, "seq": self.seq, "timestamp": self.clock.timestamp(now),
               "mono_s": now, "received_at": self.clock.timestamp(now + .16),
               "received_mono_s": now + .16, "cycle_end_mono_s": now + .16,
               "schedule_lag_s": 0, "skipped_cycles": 0, **context,
               "context_straddled": False, "config_hash": self.config.config_hash,
               "profile_id": PROFILE["id"], "quality_flags": "SIMULATED",
               "gas_resistance_ohm": 100000 * (1 - response) + 100 * math.sin(now / 10),
               "temperature_c": 25 + .02 * math.sin(now / 20),
               "humidity_pct": 50 + .1 * math.sin(now / 30), "pressure_hpa": 1013 + .1 * math.sin(now / 25),
               "new_data": True, "gas_valid": True, "heater_stable": True,
               "bme_status_bits": 176, "bme_meas_index": self.seq % 256}
        for index, sensor in enumerate(CHANNELS.values()):
            count = round((1.0 + .3 * index + response + .003 * math.sin(now / 4 + index)) / LSB_V)
            row[f"{sensor}_adc_count"] = count
            row[f"{sensor}_voltage_v"] = count * LSB_V
        for index, sensor in enumerate([*CHANNELS.values(), "bme688"]):
            status = errors.get(sensor, "OK")
            row.update({f"{sensor}_read_started_mono_s": now + index * .01,
                        f"{sensor}_read_duration_s": .1 if sensor == "bme688" else .008,
                        f"{sensor}_status": status, f"{sensor}_error": None if status == "OK" else status,
                        f"{sensor}_fresh": status != "STALE", f"{sensor}_valid": status not in ("ERROR", "STALE")})
            if status in ("ERROR", "STALE"):
                keys = ["gas_resistance_ohm", "temperature_c", "humidity_pct", "pressure_hpa"] if sensor == "bme688" else [f"{sensor}_adc_count", f"{sensor}_voltage_v"]
                for key in keys:
                    row[key] = None
                if sensor == "bme688":
                    row.update(new_data=False, gas_valid=False, heater_stable=False, bme_status_bits=None)
            if status != "OK":
                row["quality_flags"] += f";{sensor}:{status}"
        return row

    def close(self):
        self.closed = True
