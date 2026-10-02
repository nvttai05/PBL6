"""Offline analysis reads raw without modification. JSON never contains NaN."""
import csv
import json
import math
import os
from pathlib import Path
from .writer import atomic_json

SIGNALS = {"gas_resistance_ohm": "bme", "mq135_voltage_v": "mq135", "mq3_voltage_v": "mq3"}
ENV = {"temperature_c": "bme", "humidity_pct": "bme", "pressure_hpa": "bme"}

def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def yes(value):
    return str(value).lower() in ("true", "1")

def valid(row, key):
    device = (SIGNALS | ENV)[key]
    ok = row.get(device + "_status") == "OK" and yes(row.get(device + "_fresh"))
    if key == "gas_resistance_ohm":
        ok = ok and all(yes(row.get(k)) for k in ("gas_valid", "heater_stable", "new_data"))
    return ok and number(row.get(key)) is not None and number(row.get("elapsed_s")) is not None

def points(rows, key, phase):
    return [(float(r["elapsed_s"]), float(r[key])) for r in rows if r["phase"] == phase and valid(r, key)]

def slope(pts):
    if len(pts) < 2 or pts[-1][0] <= pts[0][0]:
        return None
    import numpy as np
    t, y = np.array(pts).T
    t = t - t.mean()
    return float((t @ (y - y.mean())) / (t @ t))

def basic(pts):
    import numpy as np
    y = np.array([p[1] for p in pts])
    if not len(y):
        return {"n": 0, "mean": None, "median": None, "std": None, "min": None, "max": None, "slope_per_s": None, "drift": None}
    return {"n": len(y), "mean": float(y.mean()), "median": float(np.median(y)),
        "std": float(y.std(ddof=1)) if len(y) > 1 else None, "min": float(y.min()), "max": float(y.max()),
        "slope_per_s": slope(pts), "drift": pts[-1][1] - pts[0][1] if len(pts) > 1 else None}

def analyze(path):
    path = Path(path).resolve()
    meta = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    with (path / "raw.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with (path / "events.csv").open(newline="", encoding="utf-8") as f:
        events = list(csv.DictReader(f))
    cfg = meta["config"]["analysis"]
    warnings = []
    if meta["status"] != "COMPLETE" and meta.get("kind") == "collect":
        warnings.append("Lượt thu/pha chưa hoàn thành: " + meta["status"])
    timed_intervals = [i for i in meta.get("phase_intervals", []) if i["planned_s"] is not None]
    completed = {p for p in ("BASELINE", "EXPOSURE", "RECOVERY")
                 if any(i["phase"] == p for i in timed_intervals)
                 and all(i["actual_s"] >= i["planned_s"] or math.isclose(i["actual_s"], i["planned_s"], rel_tol=1e-9, abs_tol=1e-9)
                         for i in timed_intervals if i["phase"] == p)}
    def baseline_stats(key):
        stats = basic(points(rows, key, "BASELINE"))
        reason = None
        if meta.get("kind") != "collect":
            reason = "Log session/monitor: dùng thống kê từng lượt collect, không gộp nền nhiều lượt"
        elif "BASELINE" not in completed or stats["n"] < cfg["min_baseline_samples"]:
            reason = "Baseline chưa hoàn thành hoặc không đủ mẫu hợp lệ"
        if reason:
            for field in stats:
                if field != "n":
                    stats[field] = None
        stats["reason"] = reason
        return stats
    summary = {"schema_version": "1.0", "run_id": meta["run_id"], "status": meta["status"], "rows": len(rows),
        "filter_rule": "status OK + fresh; BME gas additionally gas_valid + heater_stable + new_data",
        "auc_rule": "signed trapezoids over adjacent valid samples, no bridge across invalid rows or gap > max_gap_s",
        "signals": {}, "environment_baseline": {}, "warnings": warnings}
    for key in ENV:
        summary["environment_baseline"][key] = baseline_stats(key)
    for key, device in SIGNALS.items():
        baseline = baseline_stats(key)
        result = {"baseline": baseline, "exposure": None, "recovery": None, "reason": None}
        summary["signals"][key] = result
        valid_count = sum(valid(r, key) for r in rows)
        missing = 1 - valid_count / len(rows) if rows else 1.
        result["invalid_fraction"] = missing
        if missing > cfg["missing_fraction"]:
            warnings.append(f"{key}: thiếu/không hợp lệ {missing:.1%}")
        error_count = sum(r.get(device + "_status") == "ERROR" for r in rows)
        if error_count:
            warnings.append(f"{device}: {error_count} lỗi đọc")
        if device != "bme" and any(abs(number(r.get(device + "_adc_count")) or 0) >= cfg["adc_limit_count"] for r in rows):
            warnings.append(f"{device}: ADC gần/chạm giới hạn count")
        if baseline["reason"]:
            result["reason"] = baseline["reason"]
            continue
        base = baseline["mean"]
        denominator_ok = abs(base) > cfg["baseline_epsilon"]
        baseline["drift_pct"] = 100 * baseline["drift"] / abs(base) if denominator_ok else None
        if baseline["drift_pct"] is not None and abs(baseline["drift_pct"]) > cfg["baseline_drift_pct"]:
            warnings.append(f"{key}: baseline drift vượt ngưỡng")
        for phase in ("EXPOSURE", "RECOVERY"):
            pts = points(rows, key, phase)
            target = phase.lower()
            if phase not in completed or len(pts) < 2:
                result[target] = {"metrics": None, "reason": f"{phase} thiếu/chưa hoàn thành hoặc <2 mẫu hợp lệ"}
                warnings.append(f"{key}: {phase} chưa đủ dữ liệu")
                continue
            high, low = max(pts, key=lambda p: p[1]), min(pts, key=lambda p: p[1])
            segments, covered = [], 0.
            previous = None
            previous_interval = None
            phase_intervals = [i for i in meta.get("phase_intervals", []) if i["phase"] == phase]
            for row in rows:
                if row["phase"] != phase or not valid(row, key):
                    previous = None
                    continue
                point = (float(row["elapsed_s"]), float(row[key]))
                interval = next((index for index, span in enumerate(phase_intervals)
                                 if span["start_s"] <= point[0] < span["end_s"]), None)
                if previous and interval is not None and interval == previous_interval:
                    dt = point[0] - previous[0]
                    if 0 < dt <= cfg["max_gap_s"]:
                        segments.append(dt * ((previous[1] - base) + (point[1] - base)) / 2)
                        covered += dt
                previous = point
                previous_interval = interval
            metrics = {"n": len(pts), "maximum": high[1], "minimum": low[1],
                "maximum_at_elapsed_s": high[0], "minimum_at_elapsed_s": low[0],
                "delta_max": high[1] - base, "delta_min": low[1] - base,
                "delta_max_pct": 100 * (high[1] - base) / abs(base) if denominator_ok else None,
                "delta_min_pct": 100 * (low[1] - base) / abs(base) if denominator_ok else None,
                "slope_per_s": slope(pts), "auc_delta_signal_s": sum(segments) if segments else None,
                "auc_covered_s": covered, "percent_reason": None if denominator_ok else "Baseline gần 0"}
            if phase == "RECOVERY":
                deviation = pts[-1][1] - base
                phase_end = max(i["end_s"] for i in meta["phase_intervals"] if i["phase"] == phase)
                end_age = phase_end - pts[-1][0]
                end_ok = end_age <= cfg["max_gap_s"]
                metrics.update(end_sample_elapsed_s=pts[-1][0], end_sample_age_s=end_age,
                    end_deviation=deviation if end_ok else None,
                    end_deviation_pct=100 * deviation / abs(base) if denominator_ok and end_ok else None,
                    end_reason=None if end_ok else "Mẫu hợp lệ cuối quá xa cuối pha",
                    trend_toward_baseline=(abs(pts[-1][1] - base) < abs(pts[0][1] - base)))
                if not end_ok:
                    warnings.append(f"{key}: thiếu mẫu hợp lệ gần cuối RECOVERY")
                if denominator_ok and end_ok and abs(metrics["end_deviation_pct"]) > cfg["recovery_tolerance_pct"]:
                    warnings.append(f"{key}: chưa hồi phục về ngưỡng nền")
            result[target] = {"metrics": metrics, "reason": None}
    atomic_json(path / "summary.json", summary)
    plot(path, rows, events, meta, summary)
    return summary

def plot(path, rows, events, meta, summary):
    # Set cache path before importing matplotlib, and force a headless renderer.
    os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / ".cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"MONITOR": "#cccccc", "BASELINE": "#a2d5ab", "EXPOSURE": "#f7c28a", "RECOVERY": "#9cc6ef"}
    keys = list(SIGNALS) + list(ENV)
    fig, axes = plt.subplots(6, 1, sharex=True, figsize=(12, 14))
    for ax, key in zip(axes, keys):
        ax.plot([number(r["elapsed_s"]) for r in rows],
                [number(r.get(key)) if number(r.get(key)) is not None else float("nan") for r in rows], linewidth=1)
        bad = [r for r in rows if number(r.get(key)) is not None and not valid(r, key)]
        ax.scatter([float(r["elapsed_s"]) for r in bad], [float(r[key]) for r in bad], c="red", s=12, label="invalid/stale")
        ax.set_ylabel(key)
        ax.grid(alpha=.2)
        decorate(ax, meta, events, colors)
    axes[-1].set_xlabel("elapsed_s (monotonic)")
    fig.suptitle(f"RoboNose {meta['run_id']} | {meta['backend']} | {meta['status']}")
    fig.tight_layout()
    save_plot(fig, path / "signals.png", plt)
    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(12, 8))
    for ax, key in zip(axes, SIGNALS):
        s = summary["signals"][key]
        base = s["baseline"]["mean"]
        if s["reason"] is None and base is not None and abs(base) > meta["config"]["analysis"]["baseline_epsilon"]:
            ax.plot([float(r["elapsed_s"]) for r in rows],
                [100 * (float(r[key]) - base) / abs(base) if valid(r, key) else float("nan") for r in rows])
        else:
            ax.text(.02, .5, "No valid baseline: " + (s["reason"] or "baseline near zero"), transform=ax.transAxes)
        ax.set_ylabel(key + "\n% baseline")
        ax.grid(alpha=.2)
        decorate(ax, meta, events, colors)
    axes[-1].set_xlabel("elapsed_s (monotonic)")
    fig.tight_layout()
    save_plot(fig, path / "normalized.png", plt)

def decorate(ax, meta, events, colors):
    for i in meta.get("phase_intervals", []):
        ax.axvspan(i["start_s"], i["end_s"], color=colors.get(i["phase"], "#eeeeee"), alpha=.25)
        ax.text((i["start_s"] + i["end_s"]) / 2, .97, i["phase"], transform=ax.get_xaxis_transform(), fontsize=6, rotation=45, va="top")
    for event in events:
        if event["event"] in ("marker", "pump_command", "read_error"):
            t = number(event["elapsed_s"])
            if t is not None:
                ax.axvline(t, color="gray", linestyle=":", alpha=.4)

def save_plot(fig, destination, plt):
    temp = destination.with_name(destination.name + ".tmp")
    try:
        fig.savefig(temp, format="png", dpi=120)
        os.replace(temp, destination)
    finally:
        plt.close(fig)
