import math
import pytest
from robonose_s3.config import Config
from robonose_s3.state import StateMachine


def machine():
    state = StateMachine(Config())
    state.start_session(0)
    state.drain_events()
    return state


def complete(state, start=0):
    assert state.command("start", start)["accepted"]
    state.advance(start + 70)
    assert state.phase == "WAIT_EXPOSURE"
    assert state.command("expose", start + 80)["accepted"]
    state.advance(start + 210)
    assert state.phase == "WAIT_RECOVERY"
    assert state.route == "SAMPLE"
    assert state.command("recover", start + 220)["accepted"]
    assert state.route == "FILTERED_AIR"
    state.advance(start + 290)
    assert state.command("finish", start + 300)["accepted"]


def test_two_trials_keep_pwm_sensor_independent_and_names():
    state = machine()
    assert state.pwm == 80 and state.route == "SAMPLE"
    ids = []
    for offset in (0, 400):
        complete(state, offset)
        ids.append(state.trial.trial_id)
        assert state.trial.status == "COMPLETE"
        assert state.phase == "WAIT_NAME" and state.route == "FILTERED_AIR"
        assert state.command("name Mẫu cà phê 1", offset + 301)["accepted"]
        assert state.trial.name == "Mẫu cà phê 1"
        assert state.command("next", offset + 302)["accepted"]
        assert state.phase == "MONITOR" and state.route == "SAMPLE"
        assert state.pwm == 80 and state.pump_start_count == 1
    assert ids[0] != ids[1]


def test_late_deadlines_enter_wait_only_and_preserve_effective_time():
    state = machine()
    state.command("start", 0)
    state.advance(10000)
    assert state.phase == "WAIT_EXPOSURE" and state.phase_started == 60
    state.advance(20000)
    assert state.phase == "WAIT_EXPOSURE"
    assert state.trial.intervals[0]["end_mono_s"] == 60
    events = state.drain_events()
    late = [e for e in events if e["event"] == "phase_change"][-1]
    assert late["effective_mono_s"] == 60 and late["processed_mono_s"] == 10000
    state.command("expose", 20000)
    state.advance(50000)
    assert state.phase == "WAIT_RECOVERY" and state.route == "SAMPLE"
    assert state.trial.intervals[2]["end_mono_s"] - state.trial.intervals[2]["start_mono_s"] == 120


@pytest.mark.parametrize("command", ["expose", "recover", "next", "finish", "abort", "name early", "notes early", "extend 3", "start extra", "unknown", "status extra", "help nope", "durations 1", "info extra"])
def test_invalid_monitor_commands_do_not_change_context(command):
    state = machine()
    before = state.context(1)
    result = state.command(command, 1)
    assert not result["accepted"] and result["reason"]
    assert state.context(1) == before


def test_request_dedup_rejects_reuse_with_other_command():
    state = machine()
    first = state.command("start", 0, "req-1")
    trial_id = state.trial.trial_id
    state.drain_events()
    assert state.command("start", 0, "req-1") == first
    assert not state.events and state.trial_count == 1
    assert not state.command("recover", 0, "req-1")["accepted"]
    assert state.trial.trial_id == trial_id
    assert not state.command("start", 0)["accepted"]


@pytest.mark.parametrize("seconds", ["0", "-1", "nan", "inf", "3601", "abc", ""])
def test_invalid_extension_does_not_change_wait(seconds):
    state = machine()
    complete(state)
    # New trial: leave it at WAIT_FINISH.
    state.command("next", 301)
    state.command("start", 302)
    state.advance(362)
    state.command("expose", 363)
    state.advance(483)
    state.command("recover", 484)
    state.advance(544)
    before = state.context(544)
    assert not state.command(f"extend {seconds}", 544)["accepted"]
    assert state.context(544) == before


def test_extension_is_separate_segment_and_early_finish_abort():
    state = machine()
    complete(state)
    state.command("next", 301)
    state.command("start", 302)
    state.command("finish", 303)
    assert state.trial.status == "ABORTED" and state.route == "FILTERED_AIR" and state.pwm == 80
    state.command("next", 304)
    state.command("start", 305)
    state.command("abort", 306)
    assert state.trial.status == "ABORTED"
    other = machine()
    other.command("start", 0)
    other.advance(60)
    other.command("expose", 70)
    other.advance(190)
    other.command("recover", 200)
    other.advance(260)
    old_segment = other.segment
    assert other.command("extend 10", 300)["accepted"]
    assert other.segment != old_segment and other.deadline == 310
    other.advance(999)
    assert other.phase == "WAIT_FINISH" and other.phase_started == 310
    recoveries = [i for i in other.trial.intervals if i["phase"] == "RECOVERY"]
    assert [i["end_mono_s"] - i["start_mono_s"] for i in recoveries] == [60, 10]


@pytest.mark.parametrize("fault", [None, "disk full"])
def test_stop_is_idempotent_and_fault_is_latched(fault):
    state = machine()
    state.command("start", 0)
    state.stop(1, fault=fault)
    assert state.pwm == 0 and state.route == "FILTERED_AIR"
    assert state.phase == ("ERROR" if fault else "CLOSED")
    state.stop(2)
    assert not state.command("start", 3)["accepted"]
    assert state.pwm == 0


@pytest.mark.parametrize("kwargs", [{"sampling_hz": math.nan}, {"checkpoint_s": 0}, {"writer_queue_size": 1.5}, {"min_coverage": 2}])
def test_config_rejects_nonfinite_or_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)
