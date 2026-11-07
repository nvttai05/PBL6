import csv
import hashlib
import json
import threading
import time
import pytest

from robonose_s3.analysis import summarize
from robonose_s3.clock import FakeClock
from robonose_s3.config import CHANNELS, LSB_V, Config
from robonose_s3.recorder import Recorder, RecorderError, find_partial_sessions
from robonose_s3.schema import COLUMNS, SCHEMA, SIGNALS
from robonose_s3.session import Engine
from robonose_s3.storage_layout import trial_directory
from conftest import drain, wait_until


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sample(engine, seconds=1):
    engine.step()
    drain(engine)
    engine.clock.advance(seconds)


def test_continuous_context_exports_two_same_named_trials(engine):
    sample(engine)
    ids = []
    for _ in range(2):
        assert engine.command("start")["accepted"]
        ids.append(engine.state.trial.trial_id)
        sample(engine, 60)
        sample(engine, 10)
        assert engine.state.phase == "WAIT_EXPOSURE"
        engine.command("expose")
        sample(engine, 120)
        sample(engine, 10)
        assert engine.state.phase == "WAIT_RECOVERY" and engine.state.route == "SAMPLE"
        engine.command("recover")
        sample(engine, 60)
        sample(engine, 10)
        engine.command("finish")
        sample(engine)
        engine.command('name Mẫu trùng, "cà phê"')
        engine.command('notes dòng 1, "ghi chú"\ndòng 2')
        sample(engine)
        assert engine.state.trial.name == 'Mẫu trùng, "cà phê"'
        engine.command("next")
        sample(engine)
    engine.command("quit")
    engine.shutdown()
    assert engine.device.init_count == 1 and engine.state.pump_start_count == 1
    rows = read_rows(engine.recorder.path / "session/raw.csv")
    assert list(rows[0]) == COLUMNS and rows[0]["schema"] == SCHEMA
    assert {r["phase"] for r in rows} >= {"MONITOR", "WAIT_EXPOSURE", "WAIT_RECOVERY", "WAIT_FINISH", "WAIT_NAME"}
    assert all(r["pump_pwm_pct"] == "80" for r in rows)
    assert all("mq135_1" not in key for key in COLUMNS)
    assert ids[0] != ids[1]
    for trial_id in ids:
        folder = trial_directory(engine.recorder.path, trial_id)
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["name"] == 'Mẫu trùng, "cà phê"'
        assert metadata["notes"].endswith("dòng 2")
        assert metadata["status"] == "COMPLETE" and metadata["export_finalized"]
        exported = read_rows(folder / "raw.csv")
        assert exported == [r for r in rows if r["trial_id"] == trial_id]
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["raw_unchanged"] and summary["process_status"] == "COMPLETE"
        assert summary["quality"] == "INSUFFICIENT"  # sparse fixture is not good data
    events = [json.loads(line) for line in (engine.recorder.path / "session/events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e["event"] == "baseline_started_without_stability" for e in events)
    assert any(e["event"] == "host_command_received" and "received_mono_s" in e for e in events)
    assert engine.shutdown_count == 1


def test_inflight_and_nulls_keep_original_context_and_count_voltage(engine):
    engine.command("start")
    engine.clock.advance(59.95)
    row = engine.capture({"tgs2602": "ERROR", "mq135_2": "SUSPECT_JUMP", "bme688": "STALE"})
    original_epoch = row["context_epoch"]
    engine.clock.advance(.2)
    engine.commit(row)
    drain(engine)
    assert engine.state.phase == "WAIT_EXPOSURE"
    engine.shutdown()
    saved = read_rows(engine.recorder.path / "session/raw.csv")[0]
    assert saved["phase"] == "BASELINE" and int(saved["context_epoch"]) == original_epoch
    assert saved["context_straddled"] == "True"
    assert saved["tgs2602_adc_count"] == saved["tgs2602_voltage_v"] == ""
    assert saved["gas_resistance_ohm"] == "" and saved["bme688_fresh"] == "False"
    assert saved["mq135_2_status"] == "SUSPECT_JUMP" and saved["mq135_2_valid"] == "True"
    for sensor in ("mq3_1", "mq135_2", "mq3_2"):
        assert float(saved[f"{sensor}_voltage_v"]) == int(saved[f"{sensor}_adc_count"]) * LSB_V


def test_late_schedule_records_one_sample_and_skips_without_backfill(engine):
    sample(engine)
    engine.clock.advance(99)
    engine.step()
    drain(engine)
    assert len(engine.history) == 2 and engine.history[-1]["skipped_cycles"] == 99
    assert engine.history[-1]["mono_s"] == 100


def test_writer_failure_stops_outputs_and_keeps_error_metadata(tmp_path):
    config, clock = Config(), FakeClock()
    def fail_io(_):
        raise OSError("injected disk full")
    recorder = Recorder(tmp_path / "simulation", config, clock, io_hook=fail_io)
    engine = Engine(config, clock, recorder)
    engine.step()
    wait_until(lambda: recorder.fault_reason is not None)
    engine.step()
    assert engine.state.phase == "ERROR" and engine.state.pwm == 0
    assert engine.state.route == "FILTERED_AIR"
    assert not engine.command("start")["accepted"]
    engine.shutdown()
    metadata = json.loads((recorder.path / "session/metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "ERROR" and "disk full" in metadata["reason"]


def test_queue_full_fault_does_not_wait_for_writer(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def block_io(_):
        entered.set()
        release.wait(3)
    config, clock = Config(writer_queue_size=4), FakeClock()
    recorder = Recorder(tmp_path / "simulation", config, clock, io_hook=block_io)
    engine = Engine(config, clock, recorder)
    drain(engine)
    engine.step()
    assert entered.wait(1)
    for _ in range(4):
        recorder.submit("event", {"event": "fill", "mode": "SIMULATED"})
    started = time.monotonic()
    engine.command("mark overflow")
    assert time.monotonic() - started < .2
    assert engine.state.pwm == 0 and engine.state.phase == "ERROR"
    release.set()
    engine.shutdown()
    assert recorder.health()["status"] == "ERROR"


def test_existing_partial_is_not_modified_or_reused(tmp_path):
    root = tmp_path / "simulation"
    folder = root / "2026-11-06/old/session"
    folder.mkdir(parents=True)
    meta = folder / "metadata.json"
    meta.write_text('{"status":"PARTIAL"}', encoding="utf-8")
    before = meta.read_bytes()
    assert find_partial_sessions(root) == [str(meta)]
    recorder = Recorder(root, Config(), FakeClock())
    recorder.close()
    assert meta.read_bytes() == before and recorder.session_id != "old"


def test_periodic_checkpoint_distinguishes_written_and_synced(tmp_path):
    config, clock = Config(checkpoint_s=.02), FakeClock()
    recorder = Recorder(tmp_path / "simulation", config, clock)
    engine = Engine(config, clock, recorder)
    engine.step()
    wait_until(lambda: recorder.synced_seq == 1)
    checkpoint = json.loads((recorder.path / "session/checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["synced_seq"] == checkpoint["rows_written"] == 1
    engine.shutdown()
    assert recorder.done.is_set() and recorder.health()["status"] == "CLOSED"


def test_streaming_summary_baseline_matches_hand_calculation(tmp_path):
    path = tmp_path / "raw.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS)
        writer.writeheader()
        for t, value in enumerate((1, 3, 5)):
            row = {"segment_id": 1, "mono_s": t, "gas_valid": True}
            row.update({signal: value for signal in SIGNALS})
            for sensor in (*CHANNELS.values(), "bme688"):
                row.update({f"{sensor}_valid": True, f"{sensor}_fresh": True})
            writer.writerow(row)
    trial = {"trial_id": "fixture", "status": "ABORTED", "intervals": [
        {"segment_id": 1, "phase": "BASELINE", "start_mono_s": 0, "end_mono_s": 3}]}
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = summarize(path, trial, Config())
    stats = result["baseline_statistics"]["tgs2602_voltage_v"]
    assert stats["mean"] == 3 and stats["std"] == 2 and stats["slope_per_min"] == 120
    assert stats["coverage"] == 1 and stats["invalid_n"] == 0
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["deferred_analysis"]["auc"] == "NOT_IMPLEMENTED_STAGE02"
