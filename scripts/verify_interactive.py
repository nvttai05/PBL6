"""Short interactive sim audit. Keeps stdin open, records CSV growth, blocks hardware.

Run from repo: .venv/bin/python scripts/verify_interactive.py
All artifacts stay in data/simulation and logs; existing runs are preserved.
"""
import csv
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
GUARD = """import builtins, os, ctypes
original_import = builtins.__import__
def guarded_import(name, *a, **kw):
    if name.split('.')[0] in ('gpiozero', 'lgpio', 'smbus2', 'board', 'busio'):
        raise AssertionError('Hardware import forbidden: ' + name)
    return original_import(name, *a, **kw)
builtins.__import__ = guarded_import
original_open = os.open
def guarded_open(path, *a, **kw):
    if str(path).startswith(('/dev/i2c-', '/dev/gpiochip', '/dev/gpiomem')):
        raise AssertionError('Hardware device forbidden: ' + str(path))
    return original_open(path, *a, **kw)
os.open = guarded_open
original_cdll = ctypes.CDLL
def guarded_cdll(name, *a, **kw):
    if name is not None and 'robonose_bme' in str(name):
        raise AssertionError('Bosch hardware library forbidden')
    return original_cdll(name, *a, **kw)
ctypes.CDLL = guarded_cdll
from robonose.cli import main
raise SystemExit(main())
"""

def rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def main():
    audit_id = uuid.uuid4().hex[:12]
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    console = log_dir / f"interactive_review_{audit_id}.log"
    report_path = log_dir / f"interactive_review_{audit_id}.json"
    report = {"hardware_guard": True, "auto_mode": False, "stdin_kept_open": True, "growth": []}
    with console.open("x", encoding="utf-8") as capture:
        proc = subprocess.Popen([sys.executable, "-c", GUARD, "collect", "--sim", "--pump-disabled",
            "--sample-hz", "20", "--baseline", ".8", "--exposure", ".8", "--recovery", ".8",
            "--sim-fail-every", "7", "--display-interval", ".2", "--output", str(ROOT / "data")],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=capture, stderr=subprocess.STDOUT)
        def text():
            return console.read_text(encoding="utf-8")
        def wait(phrase, count=1):
            deadline = time.monotonic()+40
            while time.monotonic() < deadline:
                if text().count(phrase) >= count:
                    return
                if proc.poll() is not None:
                    raise RuntimeError(f"Process stopped {proc.returncode}; see {console}")
                time.sleep(.02)
            raise TimeoutError(f"Waiting {phrase}; see {console}")
        def send(command):
            proc.stdin.write((command+"\n").encode("utf-8"))
            proc.stdin.flush()
        def path_from(prefix):
            return Path(next(line[len(prefix):] for line in text().splitlines() if line.startswith(prefix)))
        def pause(phase, path, seconds=.7):
            before = len(rows(path / "raw.csv"))
            time.sleep(seconds)
            after_rows = rows(path / "raw.csv")
            added = after_rows[before:]
            item = {"phase": phase, "wait_s": seconds, "before": before, "after": len(after_rows),
                    "added_in_phase": sum(r["phase"] == phase for r in added), "stdin_open": not proc.stdin.closed}
            assert item["after"] > before and item["added_in_phase"] > 0 and item["stdin_open"], item
            report["growth"].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
        try:
            wait("MONITOR |")
            run_path = path_from("Lượt mới: ")
            session_path = path_from("Session log: ")
            pause("MONITOR", run_path)
            send("start")
            wait("Pha WAIT_EXPOSURE")
            marker = "mark áo thử, đang chờ nhập lệnh".encode("utf-8")
            split = marker.index("á".encode("utf-8"))+1
            proc.stdin.write(marker[:split])
            proc.stdin.flush()
            pause("WAIT_EXPOSURE", run_path)  # partial UTF-8 and no newline
            proc.stdin.write(marker[split:]+b"\n")
            proc.stdin.flush()
            send("pump on")
            send("expose")
            wait("Pha WAIT_RECOVERY")
            pause("WAIT_RECOVERY", run_path)
            send("recover")
            wait("Pha WAIT_FINISH")
            pause("WAIT_FINISH", run_path)
            send("extend .5")
            wait("Pha WAIT_FINISH", count=2)
            send("finish")
            wait("Đặt tên:")
            pause("WAIT_NAME", session_path)
            send("name ../../Rà soát áo")
            wait("Ghi chú:")
            pause("WAIT_NOTES", session_path, .4)
            send("notes kiểm tra nhập lệnh không chặn vòng thu")
            wait("next để thu lượt mới")
            final_path = path_from("File: ")
            send("quit")
            code = proc.wait(timeout=40)
            assert code == 0, text()
            meta = json.loads((final_path / "metadata.json").read_text())
            raw = rows(final_path / "raw.csv")
            events = rows(final_path / "events.csv")
            assert meta["status"] == "COMPLETE"
            assert meta["original_name"] == "../../Rà soát áo" and final_path.parent == run_path.parent
            assert any(e["event"] == "marker" and json.loads(e["details_json"]).get("text") == "áo thử, đang chờ nhập lệnh" for e in events)
            assert all(r["pump_command"] == "DISABLED" for r in raw)
            assert any(r["bme_status"] == "ERROR" and r["gas_resistance_ohm"] == "" for r in raw)
            assert "Điều khiển bơm disabled" in text()
            assert all((final_path / f).stat().st_size > 0 for f in
                       ("raw.csv", "events.csv", "metadata.json", "summary.json", "signals.png", "normalized.png"))
            source_names = ("raw.csv", "events.csv", "metadata.json")
            hashes = {n: hashlib.sha256((final_path/n).read_bytes()).hexdigest() for n in source_names}
            offline = subprocess.run([sys.executable, "-m", "robonose", "analyze", str(final_path)],
                                     cwd=ROOT, capture_output=True, text=True, timeout=40)
            assert offline.returncode == 0, offline.stderr
            assert all(hashlib.sha256((final_path/n).read_bytes()).hexdigest() == h for n,h in hashes.items())
            report.update(status=meta["status"], run_path=str(final_path), session_path=str(session_path), rows=len(raw),
                          durations=meta["durations"], error_rows=sum(r["bme_status"] == "ERROR" for r in raw),
                          offline_exit=offline.returncode, source_hashes_unchanged=True, console=str(console))
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            proc.stdin.close()
    with report_path.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report: {report_path}\nRun: {report['run_path']}", flush=True)

if __name__ == "__main__":
    main()
