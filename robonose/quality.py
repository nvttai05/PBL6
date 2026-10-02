"""Trend assessment shared by live UI and offline analysis; raw is untouched."""
import math
from .config import DEFAULT

KEYS = ("gas_resistance_ohm", "temperature_c", "humidity_pct")

def finite(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None

def valid(row, key):
    ok = row.get("bme_status") == "OK" and str(row.get("bme_fresh")).lower() in ("true", "1")
    if key == "gas_resistance_ohm":
        ok = ok and all(str(row.get(k)).lower() in ("true", "1") for k in ("gas_valid", "heater_stable", "new_data"))
    return ok and finite(row.get(key)) is not None and finite(row.get("elapsed_s")) is not None

def assess(rows, config=None, now=None, live=False):
    cfg = DEFAULT["stability"] | (config or {})
    if now is None:
        now = max((finite(r.get("elapsed_s")) or 0 for r in rows), default=0)
    if live:
        rows = [r for r in rows if finite(r.get("elapsed_s")) is not None
                and now-cfg["window_s"] <= float(r["elapsed_s"]) <= now]
    result = {"stable": None, "reasons": [], "advisories": [], "signals": {},
              "window_s": cfg["window_s"] if live else None, "evaluated_at_elapsed_s": now,
              "criteria": cfg}
    unknown, drifting = False, False
    for key in KEYS:
        pts = [(float(r["elapsed_s"]),float(r[key])) for r in rows if valid(r,key)]
        pts.sort()
        span = pts[-1][0]-pts[0][0] if pts else 0
        invalid_fraction = 1-len(pts)/len(rows) if rows else 1
        insufficient = len(pts)<cfg["min_samples"] or span<=0 or (live and span<cfg["window_s"]*cfg["min_window_fraction"])
        stale = not pts or now-pts[-1][0]>cfg["max_gap_s"]
        gap = any(b[0]-a[0]>cfg["max_gap_s"] for a,b in zip(pts,pts[1:]))
        mean = sum(y for _,y in pts)/len(pts) if pts else None
        rate = change = relative_rate = relative_range = None
        if len(pts)>=2 and span>0:
            mt = sum(t for t,_ in pts)/len(pts)
            denom = sum((t-mt)**2 for t,_ in pts)
            rate = 60*sum((t-mt)*(y-mean) for t,y in pts)/denom
            change = max(y for _,y in pts)-min(y for _,y in pts)
            if abs(mean)>cfg["gas_epsilon_ohm"]:
                relative_rate = rate/abs(mean)*100
                relative_range = change/abs(mean)*100
        reasons = []
        if insufficient: reasons.append("không đủ mẫu/cửa sổ quan sát")
        if stale: reasons.append("thiếu mẫu mới gần thời điểm đánh giá")
        if gap: reasons.append("khoảng trống dữ liệu vượt ngưỡng")
        if invalid_fraction>cfg["max_invalid_fraction"]: reasons.append("tỷ lệ dữ liệu không hợp lệ vượt ngưỡng")
        if key=="gas_resistance_ohm":
            if relative_rate is None: reasons.append("gas gần 0 hoặc không có hệ số xu hướng")
            is_drift = relative_rate is not None and (abs(relative_rate)>cfg["gas_pct_per_min"] or relative_range>cfg["gas_range_pct"])
        else:
            prefix = "temperature" if key=="temperature_c" else "humidity"
            is_drift = rate is not None and (abs(rate)>cfg[prefix+"_per_min"] or change>cfg[prefix+"_range"])
        if is_drift:
            reasons.append("đang trôi: slope/range vượt ngưỡng")
            drifting = True
        unknown = unknown or insufficient or stale or gap or invalid_fraction>cfg["max_invalid_fraction"] or (key=="gas_resistance_ohm" and relative_rate is None)
        result["signals"][key] = {"n":len(pts),"span_s":span,"mean":mean,"slope_per_min":rate,
            "range":change,"slope_pct_per_min":relative_rate if key=="gas_resistance_ohm" else None,
            "range_pct":relative_range if key=="gas_resistance_ohm" else None,
            "invalid_fraction":invalid_fraction,"drifting":is_drift,"reasons":reasons}
        result["reasons"].extend(key+": "+r for r in reasons)
    result["stable"] = False if drifting else None if unknown else True
    temperatures = [float(r["temperature_c"]) for r in rows if valid(r,"temperature_c")]
    if temperatures and max(temperatures)>cfg["temperature_warning_c"]:
        result["advisories"].append(f"Nhiệt độ BME vượt {cfg['temperature_warning_c']} °C; kiểm tra ảnh hưởng nhiệt/vị trí cảm biến, không suy ra nhiệt độ môi trường đã bù")
    return result

def baseline_quality(rows, config=None, complete=True):
    result = assess(rows, config)
    if not complete:
        result["stable"] = None
        result["reasons"].append("BASELINE thiếu hoặc chưa hoàn thành")
    return result
