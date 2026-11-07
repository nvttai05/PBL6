from dataclasses import asdict, dataclass
import hashlib
import json
import math

CHANNELS = {"A0": "tgs2602", "A1": "mq3_1", "A2": "mq135_2", "A3": "mq3_2"}
LSB_V = 0.0001875
PROFILE = {"id": "s3_bringup_simulated", "heater_c": 300, "heater_ms": 100,
           "os_t": 2, "os_h": 2, "os_p": 4}


@dataclass(frozen=True)
class Config:
    baseline_s: float = 60
    exposure_s: float = 120
    recovery_s: float = 60
    sampling_hz: float = 1
    max_extend_s: float = 3600
    checkpoint_s: float = 5
    writer_queue_size: int = 256
    command_queue_size: int = 64
    history_size: int = 1800
    quality_window_s: float = 30
    min_coverage: float = 0.8
    max_gap_s: float = 3
    max_invalid_fraction: float = 0.2
    gas_slope_pct_per_min: float = 5
    gas_range_pct: float = 5
    temperature_slope_c_per_min: float = 0.3
    temperature_range_c: float = 0.2
    humidity_slope_pct_per_min: float = 1
    humidity_range_pct: float = 1
    temperature_advisory_c: float = 35
    quality_version: str = "quality.v1"

    def __post_init__(self):
        for key, value in asdict(self).items():
            if isinstance(value, (float, int)) and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{key} must be finite and positive")
        if self.sampling_hz > 10 or self.min_coverage > 1 or self.max_invalid_fraction > 1:
            raise ValueError("Unsupported sampling rate or invalid quality fraction")
        for key in ("writer_queue_size", "command_queue_size", "history_size"):
            if not isinstance(getattr(self, key), int):
                raise ValueError(f"{key} must be an integer")

    def snapshot(self):
        values = asdict(self)
        values.update(channel_map=CHANNELS, ads_lsb_v=LSB_V, divider_factor=1,
                      bme_requested=PROFILE, bme_applied_simulated=PROFILE,
                      bme_pi_reference={"heater_c": 320, "heater_ms": 150, "os_t": 8, "os_h": 2, "os_p": 4},
                      production_profile=None, pump_pwm_pct=80,
                      route_rules={"valve_on": "SAMPLE", "valve_off": "FILTERED_AIR"})
        return values

    @property
    def config_hash(self):
        return hashlib.sha256(json.dumps(self.snapshot(), sort_keys=True).encode()).hexdigest()
