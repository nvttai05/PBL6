from copy import deepcopy
import math
from pathlib import Path
import tomllib

DEFAULT = {
    "sample_hz": 1.0, "fsync_interval_s": 5.0,
    "baseline_s": 30.0, "exposure_s": 60.0, "recovery_s": 60.0,
    "seed": 688,
    "hardware": {"i2c_bus": 1, "bme_address": 0x77, "ads_address": 0x48,
        "heater_c": 320, "heater_ms": 150, "temperature_oversampling": 8,
        "humidity_oversampling": 2, "pressure_oversampling": 4,
        "ads_gain": 1.0, "ads_data_rate": 128, "mq135_channel": 0,
        "mq3_channel": 1, "mq135_divider_factor": None, "mq3_divider_factor": None,
        "mq135_divider_description": "Chưa xác nhận; dự kiến 10 kΩ/10 kΩ",
        "mq3_divider_description": "Chưa xác nhận; dự kiến 10 kΩ/10 kΩ"},
    "pump": {"enabled": False, "confirmed": False, "gpio_bcm": 17, "active_high": None},
    "stability": {"window_s": 30.0, "min_samples": 5, "min_window_fraction": .8,
        "max_gap_s": 3.0, "max_invalid_fraction": .2, "gas_epsilon_ohm": 1e-9,
        "gas_pct_per_min": 5.0, "gas_range_pct": 5.0,
        "temperature_per_min": .3, "temperature_range": .2,
        "humidity_per_min": 1.0, "humidity_range": 1.0, "temperature_warning_c": 35.0},
    "analysis": {"min_baseline_samples": 3, "baseline_epsilon": 1e-9,
        "baseline_drift_pct": 5.0, "recovery_tolerance_pct": 10.0,
        "missing_fraction": 0.1, "adc_limit_count": 32700, "max_gap_s": 3.0},
}

def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} phải là số hữu hạn > 0")

def load(path=None, check=True):
    cfg = deepcopy(DEFAULT)
    if path:
        with Path(path).open("rb") as f:
            supplied = tomllib.load(f)
        for k, v in supplied.items():
            if k not in cfg:
                raise ValueError(f"Cấu hình không biết: {k}")
            if isinstance(cfg[k], dict):
                if not isinstance(v, dict) or set(v) - set(cfg[k]):
                    raise ValueError(f"Trường cấu hình không biết trong {k}")
                cfg[k].update(v)
            else:
                cfg[k] = v
    if check:
        validate(cfg)
    return cfg

def validate(cfg):
    for name in ("sample_hz", "fsync_interval_s", "baseline_s", "exposure_s", "recovery_s"):
        positive(cfg[name], name)
    h = cfg["hardware"]
    for name in ("bme_address", "ads_address"):
        if type(h[name]) is not int or not 0x08 <= h[name] <= 0x77:
            raise ValueError(f"{name}: địa chỉ I2C không hợp lệ")
    if type(h["i2c_bus"]) is not int or h["i2c_bus"] < 0:
        raise ValueError("i2c_bus không hợp lệ")
    for name in ("temperature_oversampling", "humidity_oversampling", "pressure_oversampling"):
        if h[name] not in (1, 2, 4, 8, 16):
            raise ValueError(f"{name}: chỉ hỗ trợ 1/2/4/8/16")
    if type(h["heater_c"]) is not int or not 200 <= h["heater_c"] <= 400:
        raise ValueError("heater_c phải là số nguyên 200..400")
    if type(h["heater_ms"]) is not int or not 1 <= h["heater_ms"] <= 4032:
        raise ValueError("heater_ms phải là số nguyên 1..4032")
    if h["ads_gain"] not in (2/3, 1, 2, 4, 8, 16):
        raise ValueError("ads_gain không hợp lệ")
    if h["ads_data_rate"] not in (8, 16, 32, 64, 128, 250, 475, 860):
        raise ValueError("ADS1115 data_rate không hợp lệ")
    for sensor in ("mq135", "mq3"):
        if type(h[sensor + "_channel"]) is not int or h[sensor + "_channel"] not in range(4):
            raise ValueError("Kênh ADS phải là 0..3")
        if h[sensor + "_divider_factor"] is not None:
            positive(h[sensor + "_divider_factor"], sensor + "_divider_factor")
    if h["mq135_channel"] == h["mq3_channel"]:
        raise ValueError("MQ135 và MQ3 phải dùng kênh khác nhau")
    p = cfg["pump"]
    if type(p["enabled"]) is not bool or type(p["confirmed"]) is not bool:
        raise ValueError("pump enabled/confirmed phải là boolean")
    if p["enabled"]:
        if not p["confirmed"] or type(p["gpio_bcm"]) is not int or not 0 <= p["gpio_bcm"] <= 27 or type(p["active_high"]) is not bool:
            raise ValueError("Enable pump cần confirmed=true, gpio_bcm và active_high đã xác nhận")
    a = cfg["analysis"]
    for k in ("baseline_epsilon", "baseline_drift_pct", "recovery_tolerance_pct", "max_gap_s"):
        positive(a[k], k)
    if type(a["min_baseline_samples"]) is not int or a["min_baseline_samples"] < 2:
        raise ValueError("min_baseline_samples >= 2")
    if not 0 <= a["missing_fraction"] <= 1 or not 1 <= a["adc_limit_count"] <= 32767:
        raise ValueError("Ngưỡng missing_fraction/adc_limit_count không hợp lệ")

    stability = cfg["stability"]
    for k in ("window_s", "max_gap_s", "gas_epsilon_ohm", "gas_pct_per_min", "gas_range_pct",
              "temperature_per_min", "temperature_range", "humidity_per_min", "humidity_range", "temperature_warning_c"):
        positive(stability[k], "stability."+k)
    if type(stability["min_samples"]) is not int or stability["min_samples"]<2:
        raise ValueError("stability.min_samples >= 2")
    for k in ("min_window_fraction", "max_invalid_fraction"):
        if not isinstance(stability[k], (int,float)) or isinstance(stability[k],bool) or not math.isfinite(stability[k]) or not 0<=stability[k]<=1:
            raise ValueError("stability."+k+" phải trong 0..1")
    for sensor in ("mq135", "mq3"):
        if not isinstance(h[sensor+"_divider_description"],str):
            raise ValueError("divider_description phải là văn bản")
