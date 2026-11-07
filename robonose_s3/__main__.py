import argparse
import json
import math
import os
from pathlib import Path
import signal
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="RoboNose dataset host — explicit simulation or USB hardware")
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument("--demo", action="store_true", help="Run the simulation terminal and dashboard")
    backend.add_argument("--port", help="Explicit hardware port; valid startup automatically commands PWM 80%%")
    backend.add_argument("--find-sample", metavar="NAME", help="Find every trial with this name and print its folder; read-only, no COM/GUI")
    parser.add_argument("--serial-kind", choices=["native-cdc", "uart"], help="Required with --port; DTR/RTS deasserted before open")
    parser.add_argument("--offscreen", action="store_true", help="Qt offscreen integration check")
    parser.add_argument("--auto-close-s", type=float, default=0, help="Finite smoke run; zero keeps the window open")
    args = parser.parse_args(argv)
    if args.port and not args.serial_kind:
        parser.error("--port requires explicit --serial-kind native-cdc or uart")
    if args.serial_kind and not args.port:
        parser.error("--serial-kind applies only to --port")
    if not math.isfinite(args.auto_close_s) or args.auto_close_s < 0:
        parser.error("--auto-close-s must be finite and nonnegative")
    root = Path(__file__).resolve().parents[1]
    paths = json.loads((root / "configs/paths.local.json").read_text(encoding="utf-8"))
    if Path(sys.executable).resolve() != Path(paths["python_exe"]).resolve():
        parser.error(f"Use the configured interpreter: {paths['python_exe']}")
    if args.find_sample is not None:
        if args.offscreen or args.auto_close_s:
            parser.error("GUI options do not apply to --find-sample")
        # Windows redirected streams can default to cp1252, which cannot print
        # Vietnamese names. Keep lookup output UTF-8 for consoles and pipes.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        from .sample_catalog import find_samples, format_results
        try:
            result = find_samples(root / "data", args.find_sample)
        except ValueError as error:
            parser.error(str(error))
        print(format_results(args.find_sample, result))
        for warning in result.warnings:
            print(f"Cảnh báo đọc dữ liệu: {warning}", file=sys.stderr)
        return 0
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtWidgets
    from .dashboard import Dashboard, configure_qt_font
    from .recorder import find_partial_sessions
    from .session import Session
    from .terminal import Terminal

    app = QtWidgets.QApplication([sys.argv[0]])
    configure_qt_font(app)
    data_root = root / ("data/simulation" if args.demo else "data/hardware")
    partials = find_partial_sessions(data_root)
    if partials:
        print(f"Found {len(partials)} prior PARTIAL/ERROR sessions; kept unchanged, not resumed.", flush=True)
    try:
        if args.demo:
            session = Session(data_root, on_message=lambda text: print(text, flush=True))
        else:
            from .hardware import HardwareEngine
            from .usb_protocol import SerialOptions
            options = SerialOptions(args.port, args.serial_kind)
            session = Session(data_root, mode="HARDWARE", on_message=lambda text: print(text, flush=True),
                engine_factory=lambda config, clock, recorder: HardwareEngine(config, clock, recorder, options))
    except Exception as error:
        print(f"Host startup failed: {error}", file=sys.stderr)
        return 1
    terminal = Terminal(session)
    previous_signal = signal.signal(signal.SIGINT, lambda *_: session.request_stop("Ctrl+C"))
    window = Dashboard(session)
    app.aboutToQuit.connect(lambda: session.request_stop("Qt-exit"))
    session.start()
    # Finite offscreen smoke uses an idle terminal, not the tool runner's closed stdin.
    if not (args.offscreen and args.auto_close_s):
        terminal.start()
    if args.auto_close_s:
        QtCore.QTimer.singleShot(int(args.auto_close_s * 1000), window.close)
    print(f"{session.mode} DATA | session: {session.engine.recorder.path}\nCommands: help, start, expose, recover, finish, name Mau1, next, quit", flush=True)
    window.show()
    try:
        result = app.exec()
    finally:
        terminal.stop()
        session.request_stop("Qt-exit")
        session.thread.join(15 if not args.demo else 12)
        signal.signal(signal.SIGINT, previous_signal)
    snap = session.snapshot()
    print(f"Session {snap['writer']['status']} | last reported PWM {snap['pump_pwm_pct']}% | {snap['writer']['path']}" +
          (f" | commanded OFF acknowledged: {snap.get('off_confirmed', False)}" if not args.demo else "") +
          (f" | reason: {snap.get('fault') or snap['writer']['error']}" if snap.get('fault') or snap['writer']['error'] else ""), flush=True)
    return 1 if session.thread.is_alive() or snap["writer"]["error"] else result


if __name__ == "__main__":
    raise SystemExit(main())
