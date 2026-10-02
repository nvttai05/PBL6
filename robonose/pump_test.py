"""Short on/off audit, no sensor initialization. Hardware only by explicit flags."""
import signal
import time
from .pump import Pump
from .schema import blank_sample, iso_now
from .state import StateMachine
from .writer import RunWriter, atomic_json

def run(args, cfg, factory=None):
    backend = "hardware" if args.hardware else "sim"
    if args.hardware and (not args.enable_pump or args.pump_disabled):
        raise ValueError("pump-test hardware cần --enable-pump và cấu hình cực tính đã xác nhận")
    pump, writer = None, None
    handlers = {}
    status, reason, code = "COMPLETE", "pump-test completed", 0
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, interrupted)
        pump = Pump(cfg["pump"], backend, factory)
        start = time.monotonic()
        writer = RunWriter(args.output, backend, cfg,
            {"pump": dict(cfg["pump"]), "sensor_access": False, "backend": backend,
             "purpose": "pump command test; no physical feedback"},
            run_start=start, kind="pump_test")
        state = StateMachine(start, {})
        state.transition("PUMP_TEST", start)
        def row():
            sample = blank_sample()
            sample.update(timestamp=iso_now(), elapsed_s=time.monotonic()-start,
                          phase_elapsed_s=time.monotonic()-start, phase="PUMP_TEST",
                          pump_command=pump.commanded)
            writer.row(sample)
        def command(on, label):
            if pump.enabled:
                pump.set(on)
            sent_at = time.monotonic()
            writer.event("pump_command", sent_at, "PUMP_TEST", start,
                {"command":pump.commanded, "requested_command":"ON" if on else "OFF",
                 "simulation":backend=="sim", "reason":label, "feedback":"none"})
            row()
            print(f"{label}: command={pump.commanded}; requested={'ON' if on else 'OFF'}; feedback=none",flush=True)
            return sent_at
        command(False, "initial OFF")
        on_at = command(True, "ON interval")
        deadline = on_at+args.seconds
        while time.monotonic()<deadline:
            time.sleep(min(.1, max(0,deadline-time.monotonic())))
            row()
        command(False, "final OFF")
    except KeyboardInterrupt as exc:
        status, reason = "ABORTED", str(exc) or "Ctrl+C"
    except Exception as exc:
        status, reason, code = "ERROR", f"{type(exc).__name__}: {exc}", 1
        if writer:
            try:
                writer.event("pump_error", time.monotonic(), "PUMP_TEST", start,
                             {"error":reason,"command":pump.commanded,"feedback":"none"})
            except Exception:
                pass # cleanup still attempts OFF even if disk logging failed
    finally:
        # OFF first, before disk finalization. Report failures rather than claiming OFF.
        if pump:
            error = pump.close()
            if error:
                status, reason, code = "ERROR", f"OFF/close: {error}", 1
        try:
            if writer:
                now = time.monotonic()
                final_row = blank_sample()
                final_row.update(timestamp=iso_now(),elapsed_s=now-start,phase_elapsed_s=now-start,
                                 phase="PUMP_TEST",pump_command=pump.commanded)
                writer.row(final_row)
                writer.event("pump_command", now, "PUMP_TEST", start,
                             {"command":pump.commanded, "reason":"cleanup", "feedback":"none"})
                writer.event("run_end", now, "PUMP_TEST", start, {"status":status,"reason":reason})
                writer.finish(state,status,now,reason)
                atomic_json(writer.path/"summary.json",{"status":status,"reason":reason,
                    "run_id":writer.run_id,"final_command":pump.commanded,"physical_feedback":None,
                    "purpose":"pump command audit; sensor data not acquired"})
                print(f"Đã giữ {status}: {writer.path}; {reason}",flush=True)
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig,handler)
    return code
