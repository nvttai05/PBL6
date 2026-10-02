"""Continuous acquisition worker + nonblocking terminal commands.

Reader stays initialized for the whole session. Each queued sample carries its
acquisition-time phase/run context; draining after a transition cannot relabel it.
"""
from dataclasses import dataclass
from dataclasses import replace
from collections import deque
from .quality import assess, baseline_quality
import codecs
import queue
import selectors
import signal
import sys
import threading
import time
from .analysis import analyze
from .config import positive
from .pump import Pump
from .readers import HardwareReader, SimReader
from .schema import iso_now
from .state import StateMachine, TIMED
from .writer import RunWriter

HELP = """Lệnh: start | expose | recover | extend 30/60/<giây> | finish | abort
mark <ghi chú> | status | pump on/off | durations <baseline> <exposure> <recovery>
info <sample_description/person_code/source/sampling_method/purge_method/lid_state/distance_cm> <văn bản>
Sau thu: name <tên> hoặc skip; notes <ghi chú> hoặc skip; next | quit.
Các khoảng chờ vẫn thu. Xả buồng/đưa mẫu là thao tác vật lý của bạn."""

@dataclass(frozen=True)
class Context:
    run: object
    phase: str
    since: float
    session_phase: str
    pump_command: str
    deadline: float | None = None

    def at(self, now):
        if self.deadline is not None and now >= self.deadline and self.phase in TIMED:
            phase = TIMED[self.phase]
            return replace(self, phase=phase, session_phase=phase, since=self.deadline, deadline=None)
        return self

class Acquisition:
    def __init__(self, reader, hz, session_start, context):
        self.reader, self.period, self.start = reader, 1 / hz, session_start
        self.context = context
        self.lock = threading.Lock()
        self.inflight = None
        self.stop = threading.Event()
        self.items = queue.Queue(maxsize=64)
        self.thread = threading.Thread(target=self.work, name="sensor-reader", daemon=True)

    def set_context(self, ctx):
        with self.lock:
            self.context = ctx

    def work(self):
        due, previous = time.monotonic(), None
        while not self.stop.is_set():
            if self.stop.wait(max(0., due - time.monotonic())):
                break
            with self.lock:
                if self.stop.is_set():
                    break
                began = time.monotonic()
                ctx = self.context.at(began)
                self.inflight = ctx.run
                timestamp = iso_now()
            try:
                row = self.reader.read(ctx.phase, self.start)
            except Exception as exc:
                self.items.put(("fatal", exc, ctx))
                with self.lock:
                    self.inflight = None
                return
            row.update(timestamp=timestamp, elapsed_s=began - self.start,
                phase_elapsed_s=began - ctx.since, phase=ctx.phase,
                sensor_uptime_s=began - self.reader.started,
                loop_interval_s=None if previous is None else began - previous,
                loop_duration_s=time.monotonic() - began, schedule_lag_s=max(0., began - due))
            previous = began
            # Bounded queue: backpressure rather than silently discard data.
            self.items.put(("row", row, ctx))
            with self.lock:
                self.inflight = None
            due += self.period
            if due < time.monotonic():
                due = time.monotonic()  # no catch-up burst; interval/lag show overruns

    def close(self, drain):
        self.stop.set()
        while self.thread.is_alive():
            drain()
            self.thread.join(timeout=.05)
        drain(time_budget=None)

class Session:
    def __init__(self, args, cfg, reader=None, pump=None):
        self.args, self.cfg = args, cfg
        self.backend = "hardware" if args.hardware else "sim"
        self.reader = reader
        self.pump = pump
        self.log = None
        self.run = None
        self.state = None
        self.acq = None
        self.pending = None
        self.finishing = None
        self.finishing_end = None
        self.ui = "ACTIVE"
        self.jobs = queue.Queue()
        self.analysis_thread = threading.Thread(target=self.analysis_worker, name="analysis", daemon=True)
        self.analysis_errors = []
        self.phase_error = None
        self.stopping, self.exit_code = False, 0
        self.latest = None
        self.saved_handlers = {}
        self.terminal = None
        self.collection_enabled = args.command == "collect"
        self.quality_window = deque()
        self.duration_map = {p: cfg[k] for p, k in (("BASELINE", "baseline_s"), ("EXPOSURE", "exposure_s"), ("RECOVERY", "recovery_s"))}
        self.sample_info = {k: getattr(args, k, None) for k in
            ("sample_description", "person_code", "source", "sampling_method", "purge_method", "lid_state", "distance_cm")}

    def context(self):
        if self.run:
            return Context(self.run, self.state.phase, self.state.since, self.state.phase, self.pump.commanded, self.state.deadline)
        now = self.ui_since
        return Context(None, self.ui, now, self.ui, self.pump.commanded)

    def update_context(self):
        if self.log and hasattr(self, "log_state"):
            ctx = self.context()
            phase = ctx.session_phase
            if self.log_state.phase != phase:
                self.log_state.transition(phase, ctx.since)
                self.log_state.phase_planned = self.state.phase_planned if self.run else None
        if self.acq:
            self.acq.set_context(self.context())

    def new_run(self):
        now = time.monotonic()
        self.state = StateMachine(now, self.duration_map)
        self.run = RunWriter(self.args.output, self.backend, self.cfg, self.reader.applied,
                             dict(self.sample_info), run_start=now)
        self.run.quality_rows = []
        self.run.meta["sensor_uptime_at_start_s"] = now - self.reader.started
        self.ui, self.ui_since = "ACTIVE", now
        self.run.event("run_start", now, "MONITOR", now, {"sensor_uptime_s": now - self.reader.started})
        self.update_context()
        print(f"Lượt mới: {self.run.path}\nMONITOR/warmup: dùng start khi bạn sẵn sàng.", flush=True)

    def analysis_worker(self):
        while True:
            path = self.jobs.get()
            try:
                if path is None:
                    return
                analyze(path)
                print(f"Đã phân tích và vẽ PNG: {path}", flush=True)
            except Exception as exc:
                self.analysis_errors.append((str(path), str(exc)))
                print(f"Phân tích lỗi, raw vẫn giữ ở {path}: {exc}", flush=True)
            finally:
                self.jobs.task_done()

    def event(self, name, details=None, at=None):
        now = time.monotonic() if at is None else at
        ctx = self.context()
        self.log.event(name, now, ctx.session_phase, ctx.since, details)
        if self.run:
            self.run.event(name, now, self.state.phase, self.state.since, details)

    def drain(self, time_budget=.02):
        budget = time.monotonic() + time_budget if time_budget is not None else float("inf")
        for _ in range(64):
            try:
                kind, item, ctx = self.acq.items.get_nowait()
            except queue.Empty:
                return
            if kind == "fatal":
                raise RuntimeError(f"Reader worker: {item}")
            row = item
            row["pump_command"] = ctx.pump_command
            self.latest = row
            self.quality_window.append(dict(row))
            cutoff = row["elapsed_s"] - self.cfg["stability"]["window_s"]
            while self.quality_window and self.quality_window[0]["elapsed_s"] < cutoff:
                self.quality_window.popleft()
            session_row = dict(row, phase=ctx.session_phase)
            self.log.row(session_row)
            if ctx.run and not ctx.run.closed:
                adjusted = dict(row, elapsed_s=row["elapsed_s"] + self.log.start - ctx.run.start)
                for device in ("bme", "mq135", "mq3"):
                    adjusted[device + "_read_elapsed_s"] = row[device + "_read_elapsed_s"] + self.log.start - ctx.run.start
                ctx.run.row(adjusted)
                if adjusted["phase"] == "BASELINE":
                    ctx.run.quality_rows.append(dict(adjusted))
            for device in ("bme", "mq135", "mq3"):
                if row[device + "_status"] != "OK":
                    now = self.log.start + row["elapsed_s"]
                    details = {"device": device, "status": row[device + "_status"], "error": row[device + "_error"]}
                    self.log.event("read_error", now, ctx.session_phase, ctx.since, details)
                    if ctx.run and not ctx.run.closed:
                        ctx.run.event("read_error", now, ctx.phase, ctx.since, details)
            if time.monotonic() >= budget:
                return

    def change(self, change):
        if change:
            self.update_context()
            self.event("phase_change", {"from": change[0], "to": change[1]}, at=self.state.since)
            print(f"Pha {change[1]}", flush=True)

    def live_quality(self):
        now = time.monotonic() - self.log.start if self.log else 0
        return assess(list(self.quality_window), self.cfg["stability"], now, live=True)

    def store_baseline_quality(self, writer):
        completed = any(i["phase"] == "BASELINE" and i["actual_s"] >= i["planned_s"]-1e-8
                        for i in self.state.history if i["planned_s"] is not None)
        quality = baseline_quality(getattr(writer, "quality_rows", []), self.cfg["stability"], completed)
        writer.meta["baseline_quality"] = quality
        writer.meta["baseline_unstable"] = None if quality["stable"] is None else not quality["stable"]

    def status(self):
        phase = self.state.phase if self.run else self.ui
        remain = self.state.remaining(time.monotonic()) if self.run else None
        values = self.latest or {}
        print(f"{phase} | còn {remain if remain is not None else '--'} s | "
              f"gas={values.get('gas_resistance_ohm')} Ω | MQ135={values.get('mq135_voltage_v')} V | "
              f"MQ3={values.get('mq3_voltage_v')} V | T={values.get('temperature_c')} °C | "
              f"H={values.get('humidity_pct')} % | P={values.get('pressure_hpa')} hPa | "
              f"BME={values.get('bme_status')}, gas_valid={values.get('gas_valid')}, heater_stable={values.get('heater_stable')} | "
              f"pump command={self.pump.commanded}", flush=True)
        if phase in ("MONITOR", "BASELINE"):
            quality = self.live_quality()
            label = "ỔN ĐỊNH THEO TIÊU CHÍ" if quality["stable"] is True else "ĐANG TRÔI" if quality["stable"] is False else "CHƯA ĐỦ DỮ LIỆU"
            trends = quality["signals"]
            def fmt(value):
                return "--" if value is None else f"{value:+.3g}"
            print(f"Ổn định [{self.cfg['stability']['window_s']:g}s]: {label} | "
                  f"gas={fmt(trends['gas_resistance_ohm']['slope_pct_per_min'])} %/phút | "
                  f"T={fmt(trends['temperature_c']['slope_per_min'])} °C/phút | "
                  f"H={fmt(trends['humidity_pct']['slope_per_min'])} điểm %RH/phút | "
                  + "; ".join(quality["reasons"] + quality["advisories"]), flush=True)


    def finish_run(self, status, reason):
        if not self.run:
            return
        old = self.run
        self.finishing = old
        with self.acq.lock:
            end_at = time.monotonic()
            ended_iso = iso_now()
            self.run = None
            self.ui, self.ui_since = "WAIT_NAME", end_at
            self.acq.context = self.context()
        self.finishing_end = (end_at, ended_iso)
        error = self.pump.off_best_effort()
        off_at = time.monotonic()
        self.log.event("pump_command", off_at, "WAIT_NAME", end_at,
                       {"command": self.pump.commanded, "reason": "run end", "error": error})
        old.event("pump_command", off_at, self.state.phase, self.state.since,
                  {"command": self.pump.commanded, "reason": "run end", "error": error})
        if error:
            status, reason = "ERROR", f"OFF lỗi: {error}; {reason}"
            self.exit_code = 1
        # Ensure acquisitions that began before finish are drained before closing raw.
        self.update_context()
        # Worker can still have one in-flight read. Barrier uses context identity.
        while True:
            self.drain()
            with self.acq.lock:
                inflight = getattr(self.acq, "inflight", None)
            if inflight is not old:
                break
            time.sleep(.01)
        # Once no old read is in flight, at most 64 queued items can belong to old.
        self.drain(time_budget=None)
        old.event("run_end", end_at, self.state.phase, self.state.since, {"status": status, "reason": reason})
        self.store_baseline_quality(old)
        old.finish(self.state, status, end_at, reason, ended_at=ended_iso)
        self.pending = old
        self.finishing = None
        self.finishing_end = None
        print(f"Đã giữ {status}: {old.path}\nĐặt tên: name <tên tùy ý> hoặc skip. Cảm biến vẫn hoạt động.", flush=True)

    def finalize_pending(self, name=None, notes=None):
        if not self.pending:
            return
        if name is not None:
            self.pending.meta["original_name"] = name
            self.ui, self.ui_since = "WAIT_NOTES", time.monotonic()
            print("Ghi chú: notes <văn bản> hoặc skip.", flush=True)
        if notes is not None:
            self.pending.finalize_name(self.pending.meta["original_name"] or "", notes)
            self.jobs.put(self.pending.path)
            print(f"File: {self.pending.path}\nnext để thu lượt mới; durations B E R đổi thời lượng; quit để kết thúc.", flush=True)
            self.pending = None
            self.ui, self.ui_since = "BETWEEN_RUNS", time.monotonic()
        self.update_context()

    def command(self, line):
        # Commands batched in one os.read may arrive after a timed boundary.
        if self.run:
            self.change(self.state.tick(time.monotonic()))
        line = line.strip()
        if not line:
            if self.ui in ("WAIT_NAME", "WAIT_NOTES"):
                line = "skip"
            else:
                return
        parts = line.split(maxsplit=1)
        cmd = parts[0].casefold()
        text = parts[1] if len(parts) == 2 else ""
        normalized = cmd + (" " + text if text else "")
        if cmd in ("help", "?"):
            print(HELP, flush=True)
        elif cmd == "status":
            self.status()
        elif cmd == "quit":
            self.stopping = True
        elif cmd == "mark":
            self.event("marker", {"text": text})
        elif cmd == "pump":
            if text not in ("on", "off"):
                raise ValueError("pump on hoặc pump off")
            try:
                self.pump.set(text == "on")
            except Exception as exc:
                self.event("pump_error", {"error": str(exc), "command": self.pump.commanded})
                raise
            self.event("pump_command", {"command": self.pump.commanded})
            self.update_context()
        elif cmd == "durations":
            if self.run and self.state.phase != "MONITOR":
                raise ValueError("Chỉ đổi thời lượng trước baseline hoặc giữa các lượt")
            parts = text.split()
            if len(parts) != 3:
                raise ValueError("durations <baseline_s> <exposure_s> <recovery_s>")
            values = list(map(float, parts))
            for x in values:
                positive(x, "duration")
            self.duration_map = dict(zip(("BASELINE", "EXPOSURE", "RECOVERY"), values))
            if self.run:
                self.state.durations = dict(self.duration_map)
            self.event("durations", self.duration_map)
        elif cmd == "info":
            if self.run and self.state.phase != "MONITOR":
                raise ValueError("Nhập mô tả mẫu trước baseline")
            field, _, value = text.partition(" ")
            if field not in self.sample_info:
                raise ValueError("Trường info không biết; xem help")
            self.sample_info[field] = value
            if self.run:
                self.run.meta["sample"] = dict(self.sample_info)
            self.event("sample_info", {field: value})
        elif cmd == "start":
            if text:
                raise ValueError("start không nhận tham số; nhập start rồi Enter")
            if self.reader is None or self.acq is None or not self.acq.thread.is_alive():
                raise ValueError("Chưa sẵn sàng: reader/vòng thu chưa hoạt động; chờ khởi tạo cảm biến và vòng đọc hoàn tất")
            if self.run is None and self.ui == "MONITOR" and self.args.command == "monitor":
                # Preserve continuous warmup in the existing session log, keep
                # the same reader/heater, open a new run with its own time basis.
                self.collection_enabled = True
                self.log.meta["kind"] = "session"
                self.new_run()
            if self.run is None:
                raise ValueError(f"start cần pha MONITOR; hiện đang {self.ui}. Dùng next để mở lượt mới")
            if self.state.phase != "MONITOR":
                raise ValueError(f"start chỉ hợp lệ trong MONITOR; hiện đang {self.state.phase}")
            quality = self.live_quality()
            self.run.meta["pre_baseline_quality"] = quality
            self.run.meta["baseline_started_without_stability"] = quality["stable"] is not True
            if self.log:
                self.event("baseline_quality_at_start", quality)
            if quality["stable"] is not True or quality["advisories"]:
                print("Cảnh báo bắt đầu BASELINE: " + "; ".join(quality["reasons"] + quality["advisories"])
                      + ". Vẫn bắt đầu theo lệnh người dùng; không suy ra phản ứng mùi.", flush=True)
            if hasattr(self.run, "sync"):
                self.run.sync(force=True)
            self.change(self.state.command("start", time.monotonic()))
        elif cmd == "next" and self.ui == "BETWEEN_RUNS" and self.collection_enabled:
            self.new_run()
        elif self.ui == "WAIT_NAME" and cmd in ("name", "skip"):
            self.finalize_pending(name=text if cmd == "name" else "")
        elif self.ui == "WAIT_NOTES" and cmd in ("notes", "skip"):
            self.finalize_pending(notes=text if cmd == "notes" else "")
        elif cmd in ("finish", "abort") and self.run:
            complete = cmd == "finish" and self.state.phase == "WAIT_FINISH"
            self.finish_run("COMPLETE" if complete else "ABORTED", "user " + cmd)
        elif self.run:
            self.change(self.state.command(normalized, time.monotonic()))
        else:
            raise ValueError(f"Lệnh không hợp lệ trong {self.ui}")

    def run_session(self):
        if not self.args.auto and sys.stdin.isatty() and sys.stdout.isatty():
            try:
                from .terminal import TerminalInput
            except ImportError as exc:
                raise RuntimeError("Thiếu prompt-toolkit: chạy .venv/bin/python -m pip install -r requirements-lock.txt") from exc
            with TerminalInput() as terminal:
                self.terminal = terminal
                return self._run_session()
        return self._run_session()

    def _run_session(self):
        status, reason = "COMPLETE", "user quit"
        selector = selectors.DefaultSelector()
        stdin_buffer = ""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            if self.reader is None:
                self.reader = HardwareReader(self.cfg) if self.backend == "hardware" else SimReader(self.cfg, self.args.sim_fail_every)
            if self.pump is None:
                self.pump = Pump(self.cfg["pump"], self.backend)
            self.reader.applied["pump"] = {"enabled": self.pump.enabled, "initial_command": self.pump.commanded,
                                          "feedback": "none; command only"}
            start = time.monotonic()
            self.ui_since = start
            self.log = RunWriter(self.args.output, self.backend, self.cfg, self.reader.applied,
                                 dict(self.sample_info), run_start=start, kind="session" if self.args.command == "collect" else "monitor")
            self.log.event("pump_command", start, "MONITOR", start,
                           {"command": self.pump.commanded, "reason": "initialization", "feedback": "none"})
            self.log_state = StateMachine(start, self.duration_map)
            self.analysis_thread.start()
            if self.args.command == "collect":
                self.new_run()
            else:
                self.ui = "MONITOR"
            self.acq = Acquisition(self.reader, self.cfg["sample_hz"], start, self.context())
            self.acq.thread.start()
            print(f"Session log: {self.log.path}\n{HELP}", flush=True)
            def on_signal(signum, frame):
                self.phase_error = f"signal {signum}"
                self.stopping = True
            for sig in (signal.SIGINT, signal.SIGTERM):
                self.saved_handlers[sig] = signal.signal(sig, on_signal)
            if not self.args.auto and self.terminal is None:
                try:
                    selector.register(sys.stdin, selectors.EVENT_READ)
                except (PermissionError, ValueError):
                    raise RuntimeError("stdin không poll được; dùng terminal/pipe hoặc --auto cho sim")
            last_display = 0.
            while not self.stopping:
                now = time.monotonic()
                if self.run:
                    self.change(self.state.tick(now))
                self.drain()
                if now - last_display >= self.args.display_interval:
                    self.status()
                    last_display = now
                if self.args.duration and self.ui == "MONITOR" and not self.run and now - start >= self.args.duration:
                    self.stopping = True
                    reason = "monitor duration"
                if self.args.auto:
                    self.auto(now)
                    time.sleep(.01)
                elif self.terminal is not None:
                    message = self.terminal.poll(timeout=.02)
                    if message:
                        kind, line = message
                        if kind == "line":
                            self.safe_command(line)
                        elif kind == "interrupt":
                            self.phase_error = "Ctrl+C"
                            self.stopping = True
                        elif kind == "eof":
                            reason = "stdin EOF"
                            self.stopping = True
                        else:
                            raise RuntimeError(f"Terminal input: {line}")
                else:
                    # os.read avoids TextIO readline buffering: multiple piped commands are not stranded.
                    import os
                    for key, _ in selector.select(timeout=.02):
                        chunk = os.read(key.fd, 4096)
                        if not chunk:
                            selector.unregister(sys.stdin)
                            stdin_buffer += decoder.decode(b"", final=True)
                            if stdin_buffer:
                                self.safe_command(stdin_buffer)
                                stdin_buffer = ""
                            self.stopping = True
                            reason = "stdin EOF"
                            break
                        stdin_buffer += decoder.decode(chunk)
                        while "\n" in stdin_buffer:
                            line, stdin_buffer = stdin_buffer.split("\n", 1)
                            self.safe_command(line)
                            if self.stopping:
                                break
            if self.phase_error:
                status, reason = "ABORTED", self.phase_error
        except KeyboardInterrupt:
            status, reason = "ABORTED", "Ctrl+C"
        except Exception as exc:
            status, reason = "ERROR", f"{type(exc).__name__}: {exc}"
            self.exit_code = 1
            print(reason, file=sys.stderr, flush=True)
        finally:
            if self.acq:
                with self.acq.lock:
                    self.acq.stop.set()
                    end_at, ended_iso = time.monotonic(), iso_now()
            else:
                end_at, ended_iso = time.monotonic(), iso_now()
            # OFF before waiting for any worker/analysis; cleanup remains best effort.
            if self.pump:
                error = self.pump.off_best_effort()
                if error:
                    status, reason, self.exit_code = "ERROR", f"OFF: {error}", 1
                if self.log:
                    try:
                        self.event("pump_command", {"command": self.pump.commanded, "reason": "session cleanup", "error": error})
                    except Exception as exc:
                        print(f"Ghi sự kiện OFF lỗi: {exc}", file=sys.stderr)
            if self.acq:
                try:
                    self.acq.close(self.drain)
                except Exception as exc:
                    status, reason, self.exit_code = "ERROR", str(exc), 1
            now = end_at
            active = self.run or self.finishing
            if active:
                try:
                    # Register any timed deadline reached before termination,
                    # even if the last UI poll happened earlier.
                    run_now, run_ended = self.finishing_end or (now, ended_iso)
                    self.state.tick(run_now)
                    if self.run:
                        self.update_context()
                    run_status = "ERROR" if status == "ERROR" else "ABORTED"
                    active.event("run_end", run_now, self.state.phase, self.state.since, {"status": run_status, "reason": reason})
                    self.store_baseline_quality(active)
                    active.finish(self.state, run_status, run_now, reason, ended_at=run_ended)
                    self.jobs.put(active.path)
                    print(f"Đã giữ {run_status}: {active.path}", flush=True)
                except Exception as exc:
                    print(f"Đóng lượt lỗi; kiểm tra {active.path}: {exc}", file=sys.stderr)
                    self.exit_code = 1
            if self.pending:
                try:
                    self.pending.finalize_name(self.pending.meta["original_name"] or "", self.pending.meta["notes"])
                    self.jobs.put(self.pending.path)
                except Exception as exc:
                    print(f"Finalize lỗi; giữ {self.pending.path}: {exc}", file=sys.stderr)
                    self.exit_code = 1
            if self.log:
                try:
                    self.log.event("session_end", now, "SESSION", self.log.start,
                                   {"status": status, "reason": reason, "pump_command": self.pump.commanded})
                    self.log.finish(self.log_state, status, now, reason, ended_at=ended_iso)
                    self.jobs.put(self.log.path)
                except Exception as exc:
                    print(f"Session log lỗi: {exc}", file=sys.stderr)
                    self.exit_code = 1
            if self.pump:
                error = self.pump.close()
                if error:
                    print(f"Pump cleanup lỗi: {error}", file=sys.stderr)
                    self.exit_code = 1
            if self.reader:
                try:
                    self.reader.close()
                except Exception as exc:
                    print(f"Reader close lỗi: {exc}", file=sys.stderr)
                    self.exit_code = 1
            selector.close()
            for sig, handler in self.saved_handlers.items():
                signal.signal(sig, handler)
            if self.analysis_thread.is_alive():
                self.jobs.put(None)
                while self.analysis_thread.is_alive():
                    self.analysis_thread.join(timeout=.1)
            if self.analysis_errors:
                self.exit_code = 1
            print(f"Kết thúc phiên: {status}; {reason}", flush=True)
        return self.exit_code

    def safe_command(self, line):
        try:
            if self.log:
                parts = line.strip().split(maxsplit=1)
                normalized = parts[0].casefold() + (" " + parts[1] if len(parts)==2 else "") if parts else ""
                self.event("command_received", {"raw": line, "normalized": normalized})
            self.command(line)
        except ValueError as exc:
            print(f"Lệnh bị từ chối: {exc}", flush=True)

    def auto(self, now):
        if self.args.command == "monitor":
            return
        if self.run:
            phase = self.state.phase
            elapsed = now - self.state.since
            if phase == "MONITOR" and elapsed >= self.args.auto_warmup:
                self.command("start")
            elif phase == "WAIT_EXPOSURE" and elapsed >= self.args.auto_wait:
                self.command("expose")
            elif phase == "WAIT_RECOVERY" and elapsed >= self.args.auto_wait:
                self.command("recover")
            elif phase == "WAIT_FINISH" and elapsed >= self.args.auto_wait:
                self.command("finish")
        elif self.ui in ("WAIT_NAME", "WAIT_NOTES"):
            self.command("skip")
        elif self.ui == "BETWEEN_RUNS":
            self.command("quit")
