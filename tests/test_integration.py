import json
import os
import sys
import threading
import time

from robonose_s3.clock import FakeClock
from robonose_s3.config import Config
from robonose_s3.session import Session
from robonose_s3.terminal import Terminal
from conftest import wait_until


def test_qt_terminal_partial_input_pause_zoom_and_close(qapp, tmp_path):
    from robonose_s3.dashboard import Dashboard
    clock = FakeClock()
    session = Session(tmp_path / "data/simulation", clock=clock)
    reader, writer = os.pipe()
    stream = os.fdopen(reader, "rb", buffering=0)
    terminal = Terminal(session, stream)
    window = Dashboard(session)
    session.start()
    terminal.start()
    window.show()
    pump = qapp.processEvents
    def wait(predicate):
        wait_until(predicate, pump=pump)
    try:
        wait(lambda: session.snapshot()["writer"]["rows_written"] >= 1)
        os.write(writer, b"sta")  # No Enter: input reader waits while everything else progresses.
        clock.advance(1)
        wait(lambda: session.snapshot()["writer"]["rows_written"] >= 2)
        window.refresh()
        before = len(window.curves[0].getData()[0])
        window.toggle_pause()
        window.resize(1200, 800)
        window.plots[0].setXRange(0, 30)
        clock.advance(1)
        wait(lambda: session.snapshot()["writer"]["rows_written"] >= 3)
        window.refresh()
        assert len(window.curves[0].getData()[0]) == before
        assert window.plots[0].viewRange()[0][1] < 40
        assert session.snapshot()["simulated_heartbeat_healthy"]
        window.toggle_pause()
        os.write(writer, b"rt\n")
        wait(lambda: session.snapshot()["phase"] == "BASELINE")
        clock.advance(60)
        wait(lambda: session.snapshot()["phase"] == "WAIT_EXPOSURE")
        os.write(writer, b"expose\n")
        wait(lambda: session.snapshot()["phase"] == "EXPOSURE")
        clock.advance(120)
        wait(lambda: session.snapshot()["phase"] == "WAIT_RECOVERY")
        assert session.snapshot()["air_path_commanded"] == "SAMPLE"
        os.write(writer, b"recover\n")
        wait(lambda: session.snapshot()["phase"] == "RECOVERY")
        clock.advance(60)
        wait(lambda: session.snapshot()["phase"] == "WAIT_FINISH")
        os.write(writer, b"finish\n")
        wait(lambda: session.snapshot()["phase"] == "WAIT_NAME")
        name = "name Mẫu thử tiếng Việt\n"
        os.write(writer, name.encode("utf-8"))
        wait(lambda: session.snapshot()["trial"]["name"] == "Mẫu thử tiếng Việt")
        os.write(writer, b"notes still typing")
        written = session.snapshot()["writer"]["rows_written"]
        clock.advance(1)
        wait(lambda: session.snapshot()["writer"]["rows_written"] > written)
        window.refresh()
        assert len(window.plots) == 8 and window.marker_items
        assert window.refresh_count > 3 and qapp.platformName() == "offscreen"
        assert window.grab().save(str(tmp_path / "dashboard.png"))
        window.close()  # stdin is still blocked on the incomplete notes command.
        wait(lambda: session.finished.is_set())
        assert session.snapshot()["pump_pwm_pct"] == 0
        assert session.snapshot()["writer"]["status"] == "CLOSED"
        assert session.engine.shutdown_count == 1
    finally:
        terminal.stop()
        session.request_stop("test cleanup")
        os.close(writer)
        terminal.thread.join(1)
        session.thread.join(5)
        stream.close()
        window.close()


def test_pipe_eof_processes_queued_commands_and_stops(tmp_path):
    session = Session(tmp_path / "simulation")
    reader, writer = os.pipe()
    stream = os.fdopen(reader, "rb", buffering=0)
    terminal = Terminal(session, stream)
    session.start()
    terminal.start()
    os.write(writer, b"start\nmark piped command\n")
    os.close(writer)
    assert session.finished.wait(5)
    terminal.stop()
    stream.close()
    assert session.engine.state.trial_count == 1
    assert session.snapshot()["phase"] == "CLOSED" and session.snapshot()["pump_pwm_pct"] == 0
    events = [json.loads(line) for line in (session.engine.recorder.path / "session/events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e["event"] == "marker" for e in events)


def test_ctrl_c_stop_policy_preserves_reason_and_off(tmp_path):
    session = Session(tmp_path / "simulation")
    session.start()
    wait_until(lambda: session.snapshot()["writer"]["rows_written"] >= 1)
    session.request_stop("Ctrl+C")
    session.request_stop("Qt-exit")
    assert session.finished.wait(5)
    assert session.snapshot()["pump_pwm_pct"] == 0
    metadata = json.loads((session.engine.recorder.path / "session/metadata.json").read_text(encoding="utf-8"))
    assert metadata["reason"] == "Ctrl+C" and metadata["status"] == "CLOSED"


def test_demo_import_and_runtime_never_import_serial(monkeypatch, tmp_path):
    import builtins
    original = builtins.__import__
    def guard(name, *args, **kwargs):
        if name == "serial" or name.startswith("serial."):
            raise AssertionError("Demo attempted to import hardware serial")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guard)
    session = Session(tmp_path / "simulation")
    session.start()
    wait_until(lambda: session.snapshot()["writer"]["rows_written"] >= 1)
    assert session.post("quit")
    assert session.finished.wait(5)
    assert session.snapshot()["writer"]["status"] == "CLOSED"
