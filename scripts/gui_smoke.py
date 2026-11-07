"""Small Qt/pyqtgraph smoke check with simulated data and no hardware access."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offscreen", action="store_true")
    parser.add_argument("--auto-close-ms", type=int, default=0)
    parser.add_argument("--report", type=Path, default=ROOT / "runtime/gui_smoke_manual_report.json")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    if args.auto_close_ms and args.auto_close_ms < 500:
        parser.error("--auto-close-ms must be zero or at least 500")
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"
    report = {
        "generated_at": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "timezone": "Asia/Saigon",
        "data_kind": "SIMULATED",
        "hardware_access": False,
        "python_exe": sys.executable,
        "offscreen_requested": args.offscreen,
        "auto_close_ms": args.auto_close_ms,
        "native_windows_visual_check": "NOT_EXECUTED",
        "status": "FAIL",
    }
    try:
        import numpy as np
        import PySide6
        from PySide6 import QtCore, QtGui, QtWidgets
        import pyqtgraph as pg

        app = QtWidgets.QApplication([sys.argv[0]])
        # The offscreen platform may not discover Windows fonts automatically.
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
        if font_path.is_file():
            font_id = QtGui.QFontDatabase.addApplicationFont(str(font_path))
            families = QtGui.QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                app.setFont(QtGui.QFont(families[0], 10))
            report.update(application_font_source=str(font_path),
                          application_font_loaded=bool(families))
        report["font_family"] = app.font().family()
        report.update(pyside6_version=PySide6.__version__, qt_version=QtCore.qVersion(),
                      pyqtgraph_version=pg.__version__, qt_platform=app.platformName())
        counters = {"timer_ticks": 0, "close_event_seen": False, "about_to_quit_seen": False}

        class SmokeWindow(QtWidgets.QWidget):
            def closeEvent(self, event):
                counters["close_event_seen"] = True
                super().closeEvent(event)

        window = SmokeWindow()
        window.setWindowTitle("RoboNose GUI smoke | SIMULATED")
        layout = QtWidgets.QVBoxLayout(window)
        layout.addWidget(QtWidgets.QLabel("SIMULATED DATA - GUI smoke only - no hardware"))
        plot = pg.PlotWidget(title="SIMULATED sine wave")
        plot.setLabel("bottom", "Simulated time", units="s")
        plot.setLabel("left", "Synthetic amplitude", units="a.u.")
        plot.setYRange(-1.2, 1.2)
        layout.addWidget(plot)
        tick_label = QtWidgets.QLabel("Event loop starting")
        layout.addWidget(tick_label)
        close_button = QtWidgets.QPushButton("Close smoke window")
        close_button.clicked.connect(window.close)
        layout.addWidget(close_button)
        x = np.linspace(0, 10, 200)
        curve = plot.plot(x, np.sin(x), pen=pg.mkPen("c", width=2))

        def update_plot():
            counters["timer_ticks"] += 1
            curve.setData(x, np.sin(x + counters["timer_ticks"] / 10))
            tick_label.setText(f"SIMULATED | event loop ticks: {counters['timer_ticks']}")

        def capture_and_close():
            if args.snapshot:
                args.snapshot.parent.mkdir(parents=True, exist_ok=True)
                report["snapshot_saved"] = window.grab().save(str(args.snapshot))
                report["snapshot_path"] = str(args.snapshot.resolve())
            window.close()

        def on_quit():
            counters["about_to_quit_seen"] = True

        app.aboutToQuit.connect(on_quit)
        timer = QtCore.QTimer(window)
        timer.setInterval(100)
        timer.timeout.connect(update_plot)
        timer.start()
        if args.auto_close_ms:
            QtCore.QTimer.singleShot(args.auto_close_ms, capture_and_close)
        window.resize(800, 480)
        window.show()
        started = time.monotonic()
        event_loop_exit = app.exec()
        timer.stop()
        report.update(counters)
        report.update(event_loop_exit_code=event_loop_exit,
                      elapsed_s=round(time.monotonic() - started, 3),
                      window_hidden_after_exit=not window.isVisible())
        passed = (event_loop_exit == 0 and counters["timer_ticks"] >= 3
                  and counters["close_event_seen"] and counters["about_to_quit_seen"]
                  and not window.isVisible()
                  and (not args.offscreen or app.platformName() == "offscreen")
                  and (not args.snapshot or report.get("snapshot_saved") is True))
        report["status"] = "PASS" if passed else "FAIL"
    except Exception:
        report["error"] = traceback.format_exc()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
