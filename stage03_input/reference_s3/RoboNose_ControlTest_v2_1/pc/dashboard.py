"""Live Matplotlib dashboard. Acquisition/recording runs in a separate thread."""
from __future__ import annotations

import csv
import math
import time
from collections import deque
from pathlib import Path

from robonose_core import (VALUE_FIELDS, COUNT_FIELDS, FLAG_FIELDS, TIME_FIELDS, ERROR_FIELDS,
                           CONTROL_BOOL_FIELDS, valid_value)

CARDS = [
    ("mq135_1_voltage_v", "MQ135 #1 / A0", "V", 1.0, "#2563eb"),
    ("mq3_1_voltage_v", "MQ3 #1 / A1", "V", 1.0, "#059669"),
    ("tgs2602_voltage_v", "TGS2602 / A2", "V", 1.0, "#d97706"),
    ("mq3_2_voltage_v", "MQ3 #2 / A3", "V", 1.0, "#9333ea"),
    ("bme688_gas_ohm", "BME688 GAS", "k\u03a9", 0.001, "#0891b2"),
    ("temperature_c", "TEMPERATURE", "\u00b0C", 1.0, "#e05a47"),
    ("humidity_pct", "HUMIDITY", "%RH", 1.0, "#0284c7"),
    ("pressure_hpa", "PRESSURE", "hPa", 1.0, "#475569"),
]


class Dashboard:
    def __init__(self, window_s: float, mode: str, stop_callback=None, control_request=None):
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
        from matplotlib.ticker import FuncFormatter
        from matplotlib.widgets import Button, Slider

        self.plt = plt
        self.window_s = window_s
        self.mode = mode
        self.rows = deque(maxlen=100000)
        self.latest = None
        self.control_request = control_request
        self.figure = plt.figure(figsize=(15.5, 9.8), facecolor="#f3f6fb")
        try:
            self.figure.canvas.manager.set_window_title("RoboNose - Sensors + Pump + Valve")
        except AttributeError:
            pass
        self.figure.text(.055, .960, "RoboNose  /  Control Test v2.1", fontsize=21, weight="bold", color="#12213a")
        self.figure.text(.055, .931, "MQ135 + 2 MQ3 + TGS2602 + BME688  |  pump PWM / air path  |  continuous recording", fontsize=10, color="#52657d")
        self.mode_text = self.figure.text(.945, .960, "DEMO - SIMULATED" if mode == "DEMO" else "HARDWARE",
                                         ha="right", fontsize=11, weight="bold",
                                         color="#b45309" if mode == "DEMO" else "#059669")
        self.card_artists = {}
        for i, (key, label, unit, scale, color) in enumerate(CARDS):
            col, row = i % 4, i // 4
            x, y = .055 + col * .228, .822 - row * .112
            box = FancyBboxPatch((x, y), .212, .095, transform=self.figure.transFigure,
                                 boxstyle="round,pad=0.007,rounding_size=0.008",
                                 linewidth=.7, edgecolor="#dce4ef", facecolor="white")
            self.figure.add_artist(box)
            self.figure.text(x + .009, y + .072, label, fontsize=9, color="#52657d", weight="bold")
            value = self.figure.text(x + .009, y + .036, "--", fontsize=20, color=color, weight="bold")
            detail = self.figure.text(x + .009, y + .009, "Waiting for a sample", fontsize=8, color="#64748b")
            self.card_artists[key] = (value, detail)
        grid = self.figure.add_gridspec(3, 2, left=.075, right=.94, bottom=.32, top=.655,
                                       hspace=.88, wspace=.24)
        self.axes = [self.figure.add_subplot(grid[0, 0])]
        self.axes.extend(self.figure.add_subplot(grid[r, c], sharex=self.axes[0])
                         for r, c in ((0, 1), (1, 0), (1, 1), (2, 0), (2, 1)))
        specs = [("MQ + TGS2602 analog outputs", "V"), ("BME688 gas resistance", "k\u03a9"),
                 ("Temperature", "\u00b0C"), ("Relative humidity", "%RH"), ("Pressure", "hPa"),
                 ("Sampled output commands", "Pump PWM %")]
        for axis, (title, unit) in zip(self.axes, specs):
            axis.set_facecolor("white")
            axis.set_title(title, loc="left", fontsize=10, weight="bold", color="#263b55")
            axis.set_ylabel(unit, fontsize=9, color="#52657d")
            axis.grid(True, color="#e4eaf2", linewidth=.7)
            axis.tick_params(labelsize=8, colors="#52657d")
            for spine in axis.spines.values():
                spine.set_color("#dce4ef")
            axis.xaxis.set_major_formatter(FuncFormatter(lambda val, _: f"{val / 60:.2f}".rstrip("0").rstrip(".")))
            axis.ticklabel_format(axis="y", style="plain", useOffset=False)
            axis.set_xlabel("Elapsed (min)", fontsize=8, color="#52657d")
        self.lines = {}
        for key, label, unit, scale, color in CARDS[:4]:
            self.lines[key], = self.axes[0].plot([], [], color=color, label=label, linewidth=1.4)
        for axis, spec in zip(self.axes[1:], CARDS[4:]):
            key, label, unit, scale, color = spec
            self.lines[key], = axis.plot([], [], color=color, linewidth=1.4)
        self.axes[0].legend(loc="lower right", bbox_to_anchor=(1, 1.02),
                            ncol=2, fontsize=7, frameon=False, borderaxespad=0)
        self.pump_line, = self.axes[5].step([], [], where="post", color="#be123c", label="PWM", linewidth=1.4)
        self.valve_axis = self.axes[5].twinx()
        self.valve_axis.set_ylim(-.08, 1.08)
        self.valve_axis.set_yticks([0, 1], labels=["AIR/OFF", "SAMPLE/ON"])
        self.valve_axis.tick_params(labelsize=8, colors="#7c3aed")
        self.valve_axis.set_ylabel("Valve coil", fontsize=8, color="#7c3aed")
        self.valve_line, = self.valve_axis.step([], [], where="post", color="#7c3aed", label="Valve", linewidth=1.2, alpha=.75)
        self.axes[5].set_ylim(-8, 108)
        self.status = self.figure.text(.055, .267, "Waiting for USB data...", fontsize=9, color="#52657d")
        self.footer = self.figure.text(.055, .244, "", fontsize=8, color="#64748b")
        panel = FancyBboxPatch((.055, .049), .9, .173, transform=self.figure.transFigure,
                               boxstyle="round,pad=0.007,rounding_size=0.008",
                               linewidth=.7, edgecolor="#dce4ef", facecolor="white")
        self.figure.add_artist(panel)
        panel.set_zorder(-1)
        self.figure.text(.075, .203, "OUTPUT CONTROLS  |  GPIO5 pump / GPIO4 valve", fontsize=10, weight="bold", color="#263b55")
        slider_axis = self.figure.add_axes([.17, .157, .35, .024])
        self.pump_slider = Slider(slider_axis, "Pump PWM %", 0, 100, valinit=0, valstep=1, valfmt="%0.0f%%", color="#be123c")
        self.control_buttons = []
        for bounds, label, command, value in [
            ([.58, .147, .095, .039], "Apply Pump", "PUMP", None),
            ([.69, .147, .095, .039], "Pump OFF", "PUMP", 0),
            ([.58, .090, .095, .039], "Kh\u00ed l\u1ecdc\nA / OFF", "VALVE", 0),
            ([.69, .090, .095, .039], "L\u1ea5y m\u1eabu\nB / ON", "VALVE", 1),
            ([.82, .095, .12, .09], "ALL OFF", "ALL_OFF", None),
        ]:
            axis = self.figure.add_axes(bounds)
            button = Button(axis, label, color="#fee2e2" if command == "ALL_OFF" else "#e5edfa",
                            hovercolor="#fecaca" if command == "ALL_OFF" else "#c7dcfa")
            button.label.set_fontsize(9)
            if command == "ALL_OFF":
                button.label.set_color("#b91c1c"); button.label.set_weight("bold")
            if control_request:
                button.on_clicked(lambda _, cmd=command, val=value: control_request(
                    cmd, int(self.pump_slider.val) if cmd == "PUMP" and val is None else val))
            else:
                button.set_active(False)
            self.control_buttons.append((command, button))
        self.output_feedback = self.figure.text(.075, .115, "Firmware state: waiting for ACK", fontsize=10, color="#52657d")
        self.command_feedback = self.figure.text(.075, .068, "Output values are commands, not measured speed/flow/position.", fontsize=8, color="#64748b")
        self.button = None
        if stop_callback:
            button_axis = self.figure.add_axes([.82, .006, .13, .03])
            self.button = Button(button_axis, "Stop & Save", color="#dceafe", hovercolor="#bfd5ff")
            self.button.on_clicked(lambda _: stop_callback())
            self.figure.canvas.mpl_connect("close_event", lambda _: stop_callback())

    def append(self, row: dict) -> None:
        if self.latest is not None and (row.get("seq_gap_before", 0) or row.get("order_flag") != "ok"):
            gap = dict(row)
            gap["host_elapsed_s"] = (row["host_elapsed_s"] + self.latest["host_elapsed_s"]) / 2
            for key in VALUE_FIELDS:
                gap[key] = None
            gap["pump_pwm_pct"] = gap["valve_energized"] = None
            self.rows.append(gap)
        self.rows.append(row)
        self.latest = row
        minimum_t = row["host_elapsed_s"] - self.window_s
        while len(self.rows) > 1 and self.rows[1]["host_elapsed_s"] < minimum_t:
            self.rows.popleft()

    def refresh(self, samples: int, bad: int, parse_errors: int, missing: int,
                save_directory: str, message: str = "", stale_after_s: float = 3.0) -> None:
        row = self.latest
        if row is not None:
            age = time.monotonic() - row.get("_received_monotonic", time.monotonic())
            stale = age > stale_after_s
            for key, label, unit, scale, color in CARDS:
                value_artist, detail_artist = self.card_artists[key]
                value = row[key]
                ok = valid_value(row, key)
                text = "--" if value is None else f"{value * scale:.4f} {unit}" if key.endswith("voltage_v") \
                    else f"{value * scale:.2f} {unit}"
                value_artist.set_text(text)
                value_artist.set_color("#9a3412" if stale or not ok else color)
                if key.endswith("voltage_v"):
                    name = key.removesuffix("_voltage_v")
                    index = [x[0] for x in CARDS[:4]].index(key)
                    error = row[f"ads_a{index}_error"]
                    raw_count = row[name + '_count']
                    detail = error or (f"raw count: {raw_count:.0f}" if raw_count is not None else "raw count: --")
                elif key == "bme688_gas_ohm":
                    detail = row["bme_error"] or f"valid={row['gas_valid']}  heater={row['heater_stable']}"
                else:
                    detail = row["bme_error"] or "New calibrated sensor reading"
                detail_artist.set_text(("STALE | " if stale else "") + detail[:51])
            xs = [r["host_elapsed_s"] for r in self.rows]
            for key, label, unit, scale, color in CARDS:
                ys = [r[key] * scale if valid_value(r, key) else math.nan for r in self.rows]
                self.lines[key].set_data(xs, ys)
            right = max(10.0, row["host_elapsed_s"])
            self.axes[0].set_xlim(max(0.0, right - self.window_s), right)
            for axis in self.axes[:5]:
                axis.relim(); axis.autoscale_view(scalex=False, scaley=True)
                axis.margins(y=.12)
            self.pump_line.set_data(xs, [r.get("pump_pwm_pct", math.nan) for r in self.rows])
            self.valve_line.set_data(xs, [int(r["valve_energized"]) if r.get("valve_energized") is not None else math.nan for r in self.rows])
            if self.control_request is None:
                self.refresh_controls({"enabled": False, "pending": False, "message": "Recorded commanded outputs; read-only",
                                       "confirmed": row})
            state = f"NO NEW DATA ({age:.1f}s)" if stale else "RECEIVING"
            self.status.set_text(f"{state}   |   samples: {samples:,}   |   flagged: {bad:,}   |   parse errors: {parse_errors:,}   |   missing seq: {missing:,}")
            self.status.set_color("#9a3412" if stale else "#263b55")
        elif message:
            self.status.set_text(message[:150])
            self.status.set_color("#9a3412")
        self.footer.set_text(str(save_directory)[-145:])
        self.figure.canvas.draw_idle()

    def refresh_controls(self, snapshot):
        state = snapshot.get("confirmed", {})
        if state:
            age = time.monotonic() - state.get("received_at", time.monotonic())
            coil = "SAMPLE (B/ON)" if state.get("valve_energized") else "FILTERED AIR (A/OFF)"
            text = f"Firmware ACK/state: pump {state.get('pump_pwm_pct', '--')}% | valve {coil}"
            if age > 3: text += " | STALE"
            self.output_feedback.set_text(text)
            self.output_feedback.set_color("#9a3412" if age > 3 or state.get("failsafe_active") else "#263b55")
        self.command_feedback.set_text(snapshot.get("message", "")[:125])
        for command, button in self.control_buttons:
            button.set_active(self.control_request is not None and (command == "ALL_OFF" or snapshot.get("enabled", False)))
            button.label.set_alpha(1 if button.active else .4)

    def save(self, path: Path) -> None:
        self.figure.savefig(path, dpi=140, facecolor=self.figure.get_facecolor())


def read_recent_csv(path: Path, window_s: float = 600) -> tuple[list[dict], int]:
    rows = deque(maxlen=100000)
    count = 0
    numeric = set(VALUE_FIELDS + COUNT_FIELDS + TIME_FIELDS + ("seq", "seq_gap_before", "bme_status_raw",
                  "pump_pwm_pct", "pump_pwm_duty", "control_revision", "control_revision_start", "lease_remaining_ms"))
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not set(VALUE_FIELDS + COUNT_FIELDS).issubset(reader.fieldnames or ()):
            raise ValueError("CSV does not match v2.1 with TGS2602 on A2. Use the matching program for older MQ135 recordings.")
        for source in reader:
            row = dict(source)
            row["host_elapsed_s"] = float(row["host_elapsed_s"])
            for key in numeric:
                value = row.get(key, "")
                row[key] = float(value) if value else None
            for key in FLAG_FIELDS + CONTROL_BOOL_FIELDS:
                row[key] = None if row.get(key, "") == "" else row[key] == "True"
            for key in ERROR_FIELDS:
                row[key] = row.get(key, "") or ""
            row["_received_monotonic"] = time.monotonic()
            rows.append(row)
            count += 1
            while len(rows) > 1 and rows[1]["host_elapsed_s"] < row["host_elapsed_s"] - window_s:
                rows.popleft()
    return list(rows), count


def export_saved(csv_path: Path, destination: Path, window_s: float = 600, mode="HARDWARE") -> None:
    import matplotlib
    matplotlib.use("Agg", force=True)
    rows, total = read_recent_csv(csv_path, window_s)
    dashboard = Dashboard(window_s, mode)
    for row in rows:
        dashboard.append(row)
    dashboard.refresh(total, sum(bool(r.get("quality_flags")) for r in rows), 0, 0,
                      str(csv_path.parent), message="Saved sensor data")
    dashboard.status.set_text(f"SAVED DATA  |  {total:,} samples in file  |  last {window_s / 60:g} min shown")
    dashboard.save(destination)
    dashboard.plt.close(dashboard.figure)
