"""Qt presentation only: bounded snapshots and the shared command mailbox."""
import os
from pathlib import Path
import numpy as np

os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .config import CHANNELS
from .schema import SIGNALS, valid_signal

LABELS = ["TGS2602 · A0", "MQ3 #1 · A1", "MQ135 #2 · A2", "MQ3 #2 · A3",
          "BME688 · Gas", "Temperature", "Humidity", "Pressure"]
UNITS = ["V", "V", "V", "V", "kΩ", "°C", "%RH", "hPa"]
COLORS = ["#60d5ca", "#89b4ff", "#e9bb70", "#d6a5ed", "#6bd5a0", "#f08b86", "#65c8e5", "#b4bfda"]


def configure_qt_font(app):
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
    if font_path.is_file():
        index = QtGui.QFontDatabase.addApplicationFont(str(font_path))
        families = QtGui.QFontDatabase.applicationFontFamilies(index) if index >= 0 else []
        if families:
            app.setFont(QtGui.QFont(families[0], 10))


class Dashboard(QtWidgets.QMainWindow):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.mode = getattr(session, "mode", "SIMULATED")
        self.paused = False
        self.refresh_count = 0
        self.last_marker_signature = None
        self.marker_items = []
        self.setWindowTitle(f"RoboNose | {self.mode} DATA")
        self.resize(1480, 920)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #101923; color: #dbe6ef; }
            QGroupBox { border: 1px solid #304252; border-radius: 7px; margin-top: 10px; padding: 9px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #acbdcb; }
            QPushButton, QComboBox { padding: 7px; background: #243748; border: 1px solid #476277; border-radius: 4px; }
            QLabel#banner { color: #f7d890; background: #3c3220; padding: 10px; font-weight: bold; }
        """)
        pg.setConfigOptions(background="#14212d", foreground="#90a7b9", antialias=True)
        widget = QtWidgets.QWidget()
        self.setCentralWidget(widget)
        layout = QtWidgets.QVBoxLayout(widget)
        banner_text = ("SIMULATED DATA  /  Terminal controls  /  No physical device connected" if self.mode == "SIMULATED"
                       else f"{self.mode} DATA  /  MCU phase owner  /  Output reports are commanded state")
        banner = QtWidgets.QLabel(banner_text)
        banner.setObjectName("banner")
        layout.addWidget(banner)
        self.phase_label = QtWidgets.QLabel()
        self.phase_label.setStyleSheet("font-size: 21px; font-weight: bold; padding: 5px")
        layout.addWidget(self.phase_label)
        self.trial_label = QtWidgets.QLabel()
        self.output_label = QtWidgets.QLabel()
        self.phase_history_label = QtWidgets.QLabel()
        self.phase_history_label.setWordWrap(True)
        layout.addWidget(self.trial_label)
        layout.addWidget(self.output_label)
        layout.addWidget(self.phase_history_label)
        toolbar = QtWidgets.QHBoxLayout()
        self.pause_button = QtWidgets.QPushButton("Pause plots")
        self.pause_button.clicked.connect(self.toggle_pause)
        toolbar.addWidget(self.pause_button)
        self.window_combo = QtWidgets.QComboBox()
        self.window_combo.addItems(["120 s", "600 s", "1800 s"])
        toolbar.addWidget(self.window_combo)
        toolbar.addStretch()
        toolbar.addWidget(QtWidgets.QLabel("start → expose → recover → finish → name → next | quit"))
        close = QtWidgets.QPushButton("Quit session")
        close.clicked.connect(self.close)
        toolbar.addWidget(close)
        layout.addLayout(toolbar)
        grid = QtWidgets.QGridLayout()
        layout.addLayout(grid, stretch=1)
        self.cards, self.curves, self.plots, self.quality_labels = [], [], [], []
        for i, (title, unit, color) in enumerate(zip(LABELS, UNITS, COLORS)):
            group = QtWidgets.QGroupBox(title)
            card = QtWidgets.QVBoxLayout(group)
            number = QtWidgets.QLabel("--")
            number.setStyleSheet(f"color: {color}; font-size: 23px; font-weight: bold")
            quality_label = QtWidgets.QLabel("WARMING_UP")
            quality_label.setWordWrap(True)
            plot = pg.PlotWidget()
            plot.setLabel("left", unit)
            plot.setLabel("bottom", "Session monotonic", units="s")
            plot.showGrid(x=True, y=True, alpha=.15)
            plot.setMinimumHeight(165)
            curve = plot.plot(pen=pg.mkPen(color, width=2), connect="finite")
            card.addWidget(number)
            card.addWidget(quality_label)
            card.addWidget(plot, stretch=1)
            grid.addWidget(group, i // 4, i % 4)
            self.cards.append(number)
            self.quality_labels.append(quality_label)
            self.plots.append(plot)
            self.curves.append(curve)
        self.health_label = QtWidgets.QLabel()
        self.health_label.setWordWrap(True)
        self.path_label = QtWidgets.QLabel()
        self.path_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.health_label)
        layout.addWidget(self.path_label)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.setText("Resume plots" if self.paused else "Pause plots")

    def refresh(self):
        self.refresh_count += 1
        snap = self.session.snapshot()
        phase = snap["phase"]
        waiting = {"MONITOR": "warm-up / chờ start", "WAIT_EXPOSURE": "chờ expose",
                   "WAIT_RECOVERY": "chờ recover", "WAIT_FINISH": "chờ finish / extend",
                   "WAIT_NAME": "name / notes tùy chọn → next"}.get(phase, "")
        countdown = f"{snap['remaining_s']:.1f} s remaining" if snap["remaining_s"] is not None else waiting
        self.phase_label.setText(f"{phase}   ·   {countdown}")
        trial = snap["trial"]
        self.trial_label.setText(f"Trial {trial['index']} · {trial['name'] or '(chưa đặt tên)'} · {trial['trial_id']} · {trial['status']}" if trial else "Warm-up / between trials · UUID is assigned by start")
        confirmation = "" if self.mode == "SIMULATED" else " | OFF confirmed" if snap.get('off_confirmed') else " | last reported command state"
        self.output_label.setText(f"{self.mode} outputs: PWM {snap['pump_pwm_pct']}%  ·  valve {'ON / B' if snap['valve_energized'] else 'OFF / A'}  ·  {snap['air_path_commanded']}  |  Quality: {snap['quality']['overall']}" + confirmation)
        latest = snap["latest"]
        window = int(self.window_combo.currentText().split()[0])
        rows = [row for row in snap["history"] if row["mono_s"] >= snap["now"] - window]
        for i, signal in enumerate(SIGNALS):
            quality = snap["quality"]["signals"][signal]
            self.quality_labels[i].setText(f"{quality['status']} · n={quality['valid_n']}/{quality['n']} · cover {quality['coverage']:.0%}\ngap {quality['max_gap_s']:.1f}s · invalid {quality['invalid_fraction']:.0%}")
            self.quality_labels[i].setToolTip(
                f"slope/min: {quality['slope_per_min']}\nrange: {quality['range']}\n"
                f"noise (detrended sample std): {quality['noise']}\nReasons: {', '.join(quality['reasons']) or 'none'}")
            scale = 1000 if i == 4 else 1
            usable = latest and valid_signal(latest, signal) and snap["now"] - latest["mono_s"] < 3
            value = float(latest[signal]) / scale if usable else None
            text = f"{value:.4f} {UNITS[i]}" if value is not None else "-- (missing / stale)"
            if i < 4 and usable:
                text += f"  /  {latest[f'{list(CHANNELS.values())[i]}_adc_count']} ct"
            self.cards[i].setText(text)
            if not self.paused:
                xs, ys, previous = [], [], None
                for row in rows:
                    t = row["mono_s"]
                    if previous is not None and t - previous > 1.5 / self.session.config.sampling_hz:
                        xs.append((t + previous) / 2)
                        ys.append(np.nan)
                    xs.append(t)
                    ys.append(float(row[signal]) / scale if valid_signal(row, signal) else np.nan)
                    previous = t
                self.curves[i].setData(xs, ys, connect="finite")
        if not self.paused:
            events = [e for e in snap["events"] if e["event"] in ("phase_change", "marker")
                      and e["effective_mono_s"] >= snap["now"] - window][-16:]
            self.phase_history_label.setText("Mốc (s): " + "  |  ".join(
                f"{e['effective_mono_s']:.0f} {e['details'].get('next', e['details'].get('text', 'mark'))}"
                for e in events[-5:]))
            signature = tuple((e["event"], e["effective_mono_s"], str(e["details"])) for e in events)
            if signature != self.last_marker_signature:
                for plot, item in self.marker_items:
                    plot.removeItem(item)
                self.marker_items.clear()
                for index, event in enumerate(events):
                    label = event["details"].get("next", event["details"].get("text", "mark"))
                    for plot_index, plot in enumerate(self.plots):
                        color = "#aa8b58" if "WAIT" in label else "#896ba5" if event["event"] == "marker" else "#496876"
                        line = pg.InfiniteLine(event["effective_mono_s"], angle=90, movable=False,
                                               pen=pg.mkPen(color, style=QtCore.Qt.PenStyle.DashLine),
                                               label=label[:20] if plot_index == 0 and index == len(events) - 1 else None,
                                               labelOpts={"position": .5,
                                               "rotateAxis": (1, 0), "color": "#b1bdc9"})
                        plot.addItem(line, ignoreBounds=True)
                        self.marker_items.append((plot, line))
                self.last_marker_signature = signature
        writer = snap["writer"]
        healthy = snap.get('heartbeat_healthy', snap['simulated_heartbeat_healthy'])
        self.health_label.setText(f"Samples {snap['sample_count']} · skipped {snap['gaps']} · device errors {snap['errors']} · stale {snap['stale']} | Writer {writer['status']}: {writer['rows_written']} rows · synced seq {writer['synced_seq']} · queue {writer['queue_depth']} | {self.mode} heartbeat {'healthy' if healthy else 'waiting / stopped'}" + (f" | {writer['error']}" if writer['error'] else ""))
        self.path_label.setText(writer["path"])
        if self.session.finished.is_set():
            self.timer.stop()
            self.close()

    def closeEvent(self, event):
        self.session.request_stop("GUI-close")
        self.timer.stop()
        event.accept()
