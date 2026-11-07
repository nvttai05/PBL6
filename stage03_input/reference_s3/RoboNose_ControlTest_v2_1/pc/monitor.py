#!/usr/bin/env python3
"""RoboNose v2.1: MQ/TGS2602 sensor monitor, pump PWM and 3/2 valve control."""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path

from robonose_core import LineFramer, SessionRecorder, demo_hello, demo_sample, parse_packet, ProtocolError, SCHEMA
from control_link import ControlLink


def list_ports():
    try:
        import serial.tools.list_ports
    except ImportError as exc:
        raise RuntimeError("Install dependencies: python -m pip install -r requirements.txt") from exc
    ports = list(serial.tools.list_ports.comports())
    for index, port in enumerate(ports, 1):
        print(f"  {index}. {port.device}: {port.description} [{port.hwid}]")
    if not ports:
        print("No serial ports found. Check USB cable, USB connector, and board driver.")
    return ports


def choose_port() -> str:
    ports = list_ports()
    if not ports:
        raise RuntimeError("No COM port available")
    choice = input("Enter port number or COM name (example COM5): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(ports):
        return ports[int(choice) - 1].device
    if choice:
        return choice
    raise RuntimeError("No port selected")


class Acquisition(threading.Thread):
    def __init__(self, args, recorder: SessionRecorder, stop: threading.Event):
        super().__init__(name="robonose-acquisition", daemon=True)
        self.args, self.recorder, self.stop = args, recorder, stop
        self.ui = queue.Queue(maxsize=2000)
        self.error = ""
        self.reason = "user_stop"
        self.serial = None
        self.hello_received = False
        self.control = ControlLink()
        self.framer = LineFramer()
        self.ui_last_alive = time.monotonic()
        self.ui_suspended = False
        self.link_suspended = False
        self.off_acks = set()
        self.demo_state = {"pump_pwm_pct": 0, "pump_pwm_duty": 0, "valve_energized": False,
                           "failsafe_active": False, "control_ready": True, "control_revision": 0,
                           "lease_remaining_ms": 15000}

    def ui_alive(self):
        self.ui_last_alive = time.monotonic()

    def process(self, line: bytes):
        # Observe ACK before disk writes: an I/O failure must not prevent shutdown.
        try:
            packet = parse_packet(line)
        except ProtocolError:
            packet = None
        if packet is not None:
            self.control.on_packet(packet)
            if (packet["type"] == "ack" and packet["command"] == "ALL_OFF" and packet["ok"]
                    and packet["pump_pwm_pct"] == 0 and packet["valve_energized"] is False):
                self.off_acks.add(packet["request_id"])
        row = self.recorder.receive(line)
        if row is not None:
            # Only drawing updates may be dropped. Every row is already on disk.
            if self.ui.full():
                try: self.ui.get_nowait()
                except queue.Empty: pass
            self.ui.put_nowait(row)
        self.hello_received = self.recorder.metadata["firmware"] is not None

    def reached_duration(self):
        return self.args.duration > 0 and time.monotonic() - self.recorder.started >= self.args.duration

    def run(self):
        try:
            if self.args.demo:
                self.run_demo()
            else:
                self.run_serial()
            if self.reached_duration():
                self.reason = "duration_reached"
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.reason = "acquisition_error"
            try: self.recorder.event("acquisition_error", error=self.error)
            except OSError: pass
        finally:
            try:
                confirmed = self.shutdown_outputs()
                self.recorder.metadata["shutdown_all_off_acknowledged"] = confirmed
                if not confirmed and not self.error:
                    self.error = "ALL OFF was not acknowledged. Firmware heartbeat timeout is 15 seconds."
                    self.reason = "shutdown_off_unconfirmed"
            except Exception as exc:
                self.recorder.metadata["shutdown_all_off_acknowledged"] = False
                self.error = self.error or f"Output shutdown error: {exc}"
                self.reason = "shutdown_off_unconfirmed"
            if self.serial is not None:
                try: self.serial.close()
                except Exception: pass
            self.stop.set()

    def log_command(self, request):
        self.recorder.control_event("command_sent", **{k: request.get(k) for k in (
            "request_id", "command", "requested_value")})

    def handle_demo_wire(self, wire):
        parts = wire.decode("ascii").strip().split()
        request_id, command = int(parts[0][1:]), parts[1]
        previous = dict(self.demo_state)
        if command == "PUMP":
            percent = int(parts[2])
            self.demo_state.update(pump_pwm_pct=percent, pump_pwm_duty=(percent * 1023 + 50) // 100)
        elif command == "VALVE":
            self.demo_state["valve_energized"] = bool(int(parts[2]))
        elif command == "ALL_OFF":
            self.demo_state.update(pump_pwm_pct=0, pump_pwm_duty=0, valve_energized=False)
        if previous != self.demo_state:
            self.demo_state["control_revision"] += 1
        packet = {"schema": SCHEMA, "type": "ack", "boot_id": "SIMULATED", "request_id": request_id,
                  "command": command, "ok": True, "error": "",
                  "device_ms": round((time.monotonic() - self.recorder.started) * 1000), **self.demo_state}
        line = json.dumps(packet).encode()
        self.recorder.transport(line + b"\n")
        self.process(line)

    def send_control(self):
        item = self.control.next_wire(time.monotonic())
        if item is None:
            return
        wire, request = item
        if self.args.demo:
            self.log_command(request)
            self.handle_demo_wire(wire)
        else:
            if self.serial.write(wire) != len(wire):
                raise RuntimeError("Incomplete serial command write")
            self.log_command(request)

    def shutdown_outputs(self):
        if not self.args.demo and (self.serial is None or not self.serial.is_open):
            return False
        self.control.request("ALL_OFF")
        item = self.control.next_wire(time.monotonic())
        if item is None:
            return False
        wire, request = item
        request_id = request["request_id"]
        if self.args.demo:
            self.log_command(request)
            self.handle_demo_wire(wire)
            return request_id in self.off_acks
        self.serial.write(wire)
        try: self.log_command(request)
        except OSError: pass
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and request_id not in self.off_acks:
            chunk = self.serial.read(min(max(self.serial.in_waiting, 1), 4096))
            if chunk:
                try: self.recorder.transport(chunk)
                except OSError: pass
                for line in self.framer.feed(chunk):
                    try: self.process(line)
                    except OSError: pass
        return request_id in self.off_acks

    def watch_ui(self):
        healthy = self.args.headless or time.monotonic() - self.ui_last_alive < 4
        if not healthy and not self.ui_suspended:
            self.control.suspend("UI stalled; ALL OFF requested")
            self.ui_suspended = True
        elif healthy:
            self.ui_suspended = False
        return healthy

    def run_demo(self):
        first = json.dumps(demo_hello(self.args.demo_interval)).encode() + b"\n"
        self.recorder.transport(first)
        self.process(first.rstrip())
        sequence, deadline = 0, time.monotonic()
        while not self.stop.is_set() and not self.reached_duration():
            self.watch_ui()
            self.send_control()
            if time.monotonic() >= deadline:
                packet = demo_sample(sequence, time.monotonic() - self.recorder.started, self.args.demo_faults)
                packet.update(self.demo_state)
                packet["control_revision_start"] = self.demo_state["control_revision"]
                raw = json.dumps(packet, allow_nan=False).encode() + b"\n"
                self.recorder.transport(raw)
                self.process(raw.rstrip())
                sequence += 1
                deadline += self.args.demo_interval
            self.stop.wait(.03)

    def run_serial(self):
        import serial
        self.serial = serial.Serial()
        self.serial.port, self.serial.baudrate = self.args.port, self.args.baud
        self.serial.timeout, self.serial.write_timeout = .1, 1
        # Native USB CDC commonly needs DTR asserted to indicate an open host.
        # A USB-UART board may reset once on open; boot_id records the reset.
        # --dtr off is available for USB-UART adapters that require it.
        self.serial.dtr, self.serial.rts = self.args.dtr == "on", False
        self.serial.open()
        self.recorder.event("serial_opened", port=self.args.port, baud=self.args.baud)
        last_info, last_ping = -10.0, -10.0
        while not self.stop.is_set() and not self.reached_duration():
            current = time.monotonic()
            healthy = self.watch_ui()
            last_rx = self.control.snapshot()["last_live_rx"]
            link_healthy = not self.hello_received or current - last_rx < 4
            if not link_healthy and not self.link_suspended:
                self.control.suspend("No valid device packets; ALL OFF requested; heartbeat stopped")
                self.link_suspended = True
            elif link_healthy:
                self.link_suspended = False
            if not self.hello_received and current - last_info >= 2:
                self.serial.write(b"INFO\n")
                last_info = current
            if self.hello_received and healthy and link_healthy and current - last_ping >= 2:
                self.serial.write(self.control.ping_wire())
                last_ping = current
            self.send_control()
            chunk = self.serial.read(min(max(self.serial.in_waiting, 1), 4096))
            if chunk:
                self.recorder.transport(chunk)
                for line in self.framer.feed(chunk):
                    self.process(line)
            else:
                self.recorder.sync()
        if self.framer.buffer or self.framer.discarding:
            self.recorder.event("partial_line_at_stop", bytes_buffered=len(self.framer.buffer),
                                oversized_line=self.framer.discarding)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial port, e.g. COM5. Omit to choose interactively.")
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--dtr", choices=("on", "off"), default="on", help="Default on for native USB CDC; try off only for a USB-UART adapter.")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    parser.add_argument("--window", type=float, default=600, help="Visible chart window, seconds (default 600).")
    parser.add_argument("--duration", type=float, default=0, help="Stop after N seconds; 0 means until closed/Ctrl+C.")
    parser.add_argument("--headless", action="store_true", help="Record with terminal output instead of a live window.")
    parser.add_argument("--note", default="", help="Description of this diagnostic run, saved in metadata.")
    parser.add_argument("--demo", action="store_true", help="SIMULATED DATA ONLY; no serial device opened.")
    parser.add_argument("--demo-faults", action="store_true", help="Inject MQ/BME failures into --demo.")
    parser.add_argument("--demo-interval", type=float, default=1, help="Demo timing only; does not change hardware firmware.")
    args = parser.parse_args(argv)
    if args.duration < 0 or args.window <= 0 or args.demo_interval <= 0:
        parser.error("duration must be >= 0; window and demo-interval must be > 0")
    if args.demo_faults and not args.demo:
        parser.error("--demo-faults requires --demo")
    try:
        if args.list_ports:
            list_ports()
            return 0
        if args.demo and args.port:
            parser.error("Choose either --demo or --port")
        if not args.demo and not args.port:
            args.port = choose_port()
    except (RuntimeError, EOFError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    mode = "DEMO" if args.demo else "HARDWARE"
    if args.demo:
        print("*** DEMO: SIMULATED DATA, NOT SENSOR MEASUREMENTS ***", flush=True)
    try:
        recorder = SessionRecorder(args.output.resolve(), mode, args.port, args.note)
    except OSError as exc:
        print(f"Cannot create recording: {exc}", file=sys.stderr)
        return 2
    print(f"Saving to: {recorder.directory}", flush=True)
    print("Sampling continues until Stop & Save, closing the window, or Ctrl+C.", flush=True)
    stop = threading.Event()
    worker = Acquisition(args, recorder, stop)
    dashboard = None
    worker.start()
    ui_error = ""
    try:
        if args.headless:
            last_print = 0.0
            while not stop.wait(.15):
                latest = None
                while True:
                    try: latest = worker.ui.get_nowait()
                    except queue.Empty: break
                if latest is not None and time.monotonic() - last_print >= 1:
                    print(f"[{latest['host_elapsed_s']:.1f}s] seq={latest['seq']} "
                          f"MQ/TGS={[latest[k] for k in ('mq135_1_voltage_v', 'mq3_1_voltage_v', 'tgs2602_voltage_v', 'mq3_2_voltage_v')]} "
                          f"gas={latest['bme688_gas_ohm']} Ohm | {latest['quality_flags'] or 'OK'}", flush=True)
                    last_print = time.monotonic()
        else:
            from dashboard import Dashboard
            dashboard = Dashboard(args.window, mode, stop_callback=stop.set,
                                  control_request=worker.control.request)

            def tick():
                worker.ui_alive()
                while True:
                    try: dashboard.append(worker.ui.get_nowait())
                    except queue.Empty: break
                interval = (recorder.metadata.get("firmware") or {}).get("sample_interval_ms", 1000) / 1000
                elapsed = time.monotonic() - recorder.started
                message = worker.error or f"Waiting for valid sensor packets... {elapsed:.0f}s; parse errors: {recorder.parse_errors}"
                dashboard.refresh(recorder.sample_count, recorder.bad_samples, recorder.parse_errors,
                                  recorder.missing_seq, str(recorder.directory), message,
                                  stale_after_s=max(3, interval * 3))
                dashboard.refresh_controls(worker.control.snapshot())
                if stop.is_set():
                    dashboard.plt.close(dashboard.figure)

            timer = dashboard.figure.canvas.new_timer(interval=500)
            timer.add_callback(tick)
            timer.start()
            tick()
            dashboard.plt.show()
            timer.stop()
    except KeyboardInterrupt:
        print("Stopping...", flush=True)
    except Exception as exc:
        ui_error = f"{type(exc).__name__}: {exc}"
        print(f"Display error: {ui_error}. Try --headless.", file=sys.stderr)
    finally:
        stop.set()
        worker.join(timeout=3)
        if worker.is_alive() and worker.serial is not None:
            try: worker.serial.cancel_read()
            except Exception: pass
            worker.join(timeout=2)
    if worker.is_alive():
        print("Acquisition did not stop cleanly. Keep the files; metadata remains IN_PROGRESS.", file=sys.stderr)
        return 2
    reason = "display_error" if ui_error else worker.reason
    try:
        summary = recorder.finalize(reason)
    except OSError as exc:
        print(f"ERROR finalizing files: {exc}. Keep the existing raw files.", file=sys.stderr)
        return 2
    try:
        if dashboard is not None:
            while True:
                try: dashboard.append(worker.ui.get_nowait())
                except queue.Empty: break
            dashboard.refresh(recorder.sample_count, recorder.bad_samples, recorder.parse_errors,
                              recorder.missing_seq, str(recorder.directory))
            dashboard.status.set_text(f"STOPPED  |  {recorder.sample_count:,} samples saved  |  {reason}")
            dashboard.refresh_controls(worker.control.snapshot())
            dashboard.save(recorder.directory / "dashboard.png")
        elif recorder.sample_count:
            from dashboard import export_saved
            export_saved(recorder.directory / "samples.csv", recorder.directory / "dashboard.png",
                         args.window, mode)
    except Exception as exc:
        print(f"Chart export unavailable: {exc}. CSV/raw files are saved.", file=sys.stderr)
    print(f"Saved {summary['sample_count']} samples; flagged={summary['samples_with_flags']}; "
          f"parse errors={summary['parse_errors']}; missing seq={summary['missing_sequence_numbers']}", flush=True)
    print(f"Files: {recorder.directory}", flush=True)
    if worker.error:
        print(worker.error, file=sys.stderr)
    if not recorder.sample_count:
        print("NO VALID SENSOR SAMPLES. Check firmware, selected USB port, and events.jsonl.", file=sys.stderr)
        return 2
    return 2 if worker.error or ui_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
