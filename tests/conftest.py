import os
from pathlib import Path
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from robonose_s3.clock import FakeClock
from robonose_s3.config import Config
from robonose_s3.recorder import Recorder
from robonose_s3.session import Engine


def wait_until(predicate, timeout=3, pump=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pump:
            pump()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("Condition was not reached within timeout")


def drain(engine):
    wait_until(lambda: engine.recorder.queue.unfinished_tasks == 0 or engine.recorder.fault_reason)
    assert not engine.recorder.fault_reason


@pytest.fixture
def engine(tmp_path):
    config, clock = Config(), FakeClock()
    recorder = Recorder(tmp_path / "data/simulation", config, clock)
    instance = Engine(config, clock, recorder)
    yield instance
    instance.shutdown()


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    from robonose_s3.dashboard import configure_qt_font
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    configure_qt_font(app)
    yield app
