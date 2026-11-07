"""Versioned descriptive quality; heuristic warnings never modify raw values."""
import math
import statistics
from .schema import SIGNALS, valid_signal


def statistics_for(points):
    if not points:
        return {key: None for key in ("mean", "median", "std", "min", "max", "slope_per_min", "range", "noise")}
    xs, ys = zip(*points)
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator if denominator else None
    residuals = [y - mean_y - (slope or 0) * (x - mean_x) for x, y in points]
    return {"mean": mean_y, "median": statistics.median(ys),
            "std": statistics.stdev(ys) if len(ys) > 1 else None, "min": min(ys), "max": max(ys),
            "slope_per_min": None if slope is None else slope * 60,
            "range": max(ys) - min(ys), "noise": statistics.stdev(residuals) if len(ys) > 1 else None}


def covered_seconds(times, start, end, period):
    """Union of forward sample-support intervals, clipped to the declared window."""
    covered, previous_end = 0.0, start
    for t in sorted(times):
        left, right = max(start, t, previous_end), min(end, t + period)
        if right > left:
            covered += right - left
            previous_end = right
    return covered


def evaluate(rows, now, config):
    start, period = now - config.quality_window_s, 1 / config.sampling_hz
    rows = [row for row in rows if start <= float(row["mono_s"]) <= now]
    output = {}
    for signal in SIGNALS:
        points = [(float(row["mono_s"]), float(row[signal])) for row in rows if valid_signal(row, signal)]
        times = [t for t, _ in points]
        stats = statistics_for(points)
        coverage = covered_seconds(times, start, now, period) / config.quality_window_s
        gaps = [b - a for a, b in zip([start, *times], [*times, now])]
        invalid = (len(rows) - len(points)) / len(rows) if rows else 1.0
        span = float(rows[-1]["mono_s"]) - float(rows[0]["mono_s"]) + period if rows else 0
        reasons = []
        if span < config.quality_window_s * config.min_coverage:
            status = "WARMING_UP"
            reasons.append("WINDOW_TOO_SHORT")
        elif len(points) < math.ceil(config.quality_window_s * config.sampling_hz * config.min_coverage) or coverage < config.min_coverage:
            status = "INSUFFICIENT"
            reasons.append("NOT_ENOUGH_VALID_COVERAGE")
        elif invalid > config.max_invalid_fraction or max(gaps, default=config.quality_window_s) > config.max_gap_s:
            status = "WARN"
            reasons.append("INVALID_FRACTION_OR_GAP")
        elif signal in ("gas_resistance_ohm", "temperature_c", "humidity_pct"):
            slope, value_range = abs(stats["slope_per_min"] or 0), stats["range"]
            if signal == "gas_resistance_ohm":
                if abs(stats["mean"]) < 1e-12:
                    status, reasons = "INSUFFICIENT", ["BASELINE_NEAR_ZERO"]
                else:
                    status = "WARN" if slope / abs(stats["mean"]) * 100 > config.gas_slope_pct_per_min or value_range / abs(stats["mean"]) * 100 > config.gas_range_pct else "STABLE"
            else:
                limits = ((config.temperature_slope_c_per_min, config.temperature_range_c)
                          if signal == "temperature_c" else (config.humidity_slope_pct_per_min, config.humidity_range_pct))
                status = "WARN" if slope > limits[0] or value_range > limits[1] else "STABLE"
            if status == "WARN":
                reasons.append("DRIFT_OR_RANGE")
        else:
            status = "UNCONFIGURED"
            reasons.append("NO_VALIDATED_THRESHOLD")
        if signal == "temperature_c" and points and points[-1][1] > config.temperature_advisory_c:
            reasons.append("TEMPERATURE_ABOVE_35_ADVISORY")
        output[signal] = {"status": status, "reasons": reasons, "n": len(rows), "valid_n": len(points),
                          "coverage": coverage, "invalid_fraction": invalid,
                          "max_gap_s": max(gaps, default=config.quality_window_s), **stats}
    statuses = {value["status"] for value in output.values()}
    overall = next((s for s in ("INSUFFICIENT", "WARMING_UP", "WARN", "UNCONFIGURED") if s in statuses), "STABLE")
    return {"version": config.quality_version, "window_s": config.quality_window_s,
            "overall": overall, "signals": output}
