"""Streaming closed-trial summary. No raw modifications, delta/AUC deferred."""
import csv
import hashlib
import math
from .schema import SCHEMA, SIGNALS, valid_signal


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Accumulator:
    def __init__(self):
        self.n = 0
        self.mean = self.m2 = self.sum_t = self.sum_tt = self.sum_y = self.sum_ty = 0.0
        self.minimum = self.maximum = None
        self.first_t = None
        self.last_t = None
        self.coverage_end = None
        self.covered = 0.0
        self.max_gap = 0.0

    def add(self, t, y, period, start, end):
        self.n += 1
        delta = y - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (y - self.mean)
        self.minimum = y if self.minimum is None else min(y, self.minimum)
        self.maximum = y if self.maximum is None else max(y, self.maximum)
        self.first_t = t if self.first_t is None else self.first_t
        self.max_gap = max(self.max_gap, t - (start if self.last_t is None else self.last_t))
        self.last_t = t
        relative = t - start
        self.sum_t += relative
        self.sum_tt += relative * relative
        self.sum_y += y
        self.sum_ty += relative * y
        left = max(start, t, self.coverage_end if self.coverage_end is not None else start)
        right = min(end, t + period)
        self.covered += max(0, right - left)
        self.coverage_end = max(right, self.coverage_end or start)

    def result(self, start, end):
        duration = max(0, end - start)
        denominator = self.n * self.sum_tt - self.sum_t ** 2
        return {"valid_n": self.n, "mean": self.mean if self.n else None,
                "std": math.sqrt(max(0, self.m2 / (self.n - 1))) if self.n > 1 else None,
                "min": self.minimum, "max": self.maximum,
                "slope_per_min": 60 * (self.n * self.sum_ty - self.sum_t * self.sum_y) / denominator if denominator > 0 else None,
                "coverage": min(1, self.covered / duration) if duration else None,
                "max_gap_s": max(self.max_gap, end - (self.last_t if self.last_t is not None else start)),
                "null_reason": "NO_VALID_SAMPLES" if not self.n else None}


def summarize(raw_path, trial, config):
    before = file_hash(raw_path)
    intervals = {str(item["segment_id"]): item for item in trial["intervals"]}
    accumulators = {key: {signal: Accumulator() for signal in SIGNALS} for key in intervals}
    totals = {key: 0 for key in intervals}
    with raw_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row["segment_id"]
            if key not in intervals:
                raise ValueError("Export has unknown segment/context")
            totals[key] += 1
            interval = intervals[key]
            start, end = interval["start_mono_s"], interval["end_mono_s"]
            for signal in SIGNALS:
                if valid_signal(row, signal):
                    accumulators[key][signal].add(float(row["mono_s"]), float(row[signal]),
                                                 1 / config.sampling_hz, start, end)
    segments = []
    for key, interval in intervals.items():
        signals = {}
        for signal, accumulator in accumulators[key].items():
            stats = accumulator.result(interval["start_mono_s"], interval["end_mono_s"])
            stats.update(n=totals[key], invalid_n=totals[key] - accumulator.n,
                         invalid_fraction=(totals[key] - accumulator.n) / totals[key] if totals[key] else None)
            signals[signal] = stats
        segments.append({**interval, "signals": signals})
    after = file_hash(raw_path)
    if before != after:
        raise RuntimeError("Closed raw changed during analysis")
    baseline = next((s["signals"] for s in segments if s["phase"] == "BASELINE"), None)
    required = [next((s for s in segments if s["phase"] == phase), None)
                for phase in ("BASELINE", "EXPOSURE", "RECOVERY")]
    enough = all(segment and all((s["coverage"] or 0) >= config.min_coverage
                  and s["max_gap_s"] <= config.max_gap_s
                  and (s["invalid_fraction"] or 0) <= config.max_invalid_fraction
                  for s in segment["signals"].values()) for segment in required)
    return {"schema": SCHEMA, "mode": trial.get("mode", "SIMULATED"), "trial_id": trial["trial_id"],
            "process_status": trial["status"], "quality": "UNCONFIGURED" if enough else "INSUFFICIENT",
            "quality_reasons": ["ANALOG_THRESHOLDS_NOT_VALIDATED"] if enough else ["PHASE_COVERAGE_OR_VALIDITY_INSUFFICIENT"],
            "baseline_statistics": baseline, "segments": segments,
            "raw_sha256": before, "raw_unchanged": True,
            "deferred_analysis": {"median": "NOT_IMPLEMENTED_STREAMING_STAGE02", "delta": "NOT_IMPLEMENTED_STAGE02",
                                  "auc": "NOT_IMPLEMENTED_STAGE02", "pi_comparison": "NEEDS_INPUT"}}
