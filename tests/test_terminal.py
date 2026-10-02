"""Real PTY + VT100 screen, not just piped stdin or ANSI substring matching."""
import codecs
import csv
import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from types import SimpleNamespace
import pyte
import pytest
from robonose.cli import parser
from robonose.config import load
from robonose.session import Session
from robonose.state import StateMachine
from scripts.verify_interactive import GUARD

ROOT = Path(__file__).resolve().parents[1]

def rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

class TerminalProcess:
    def __init__(self, root, mode="monitor"):
        self.root = root
        self.master, slave = pty.openpty()
        self.original_termios = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 60, 220, 0, 0))
        self.screen = pyte.Screen(220, 60)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.text = ""
        self.proof = []
        env = dict(os.environ, TERM="xterm-256color", PROMPT_TOOLKIT_NO_CPR="1")
        self.p = subprocess.Popen([sys.executable, "-u", "-c", GUARD, mode, "--sim", "--pump-disabled",
            "--sample-hz", "20", "--display-interval", ".08", "--baseline", "2", "--exposure", "2",
            "--recovery", "2", "--output", str(root / "data")],
            cwd=ROOT, env=env, stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)

    def read_for(self, seconds):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.master], [], [], min(.03, max(0.,deadline-time.monotonic())))
            if ready:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                text = self.decoder.decode(chunk)
                self.text += text
                self.stream.feed(text)

    def wait(self, condition, timeout=40):
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            self.read_for(.04)
            if condition():
                return
            if self.p.poll() is not None:
                pytest.fail(f"PTY process stopped: {self.p.returncode}\n{self.text[-5000:]}")
        pytest.fail(f"PTY timeout\n{self.text[-5000:]}\n{self.screen.display[-5:]}")

    def prompt_line(self):
        return self.screen.display[self.screen.cursor.y].rstrip()

    def send(self, text):
        os.write(self.master, text.encode("utf-8") if isinstance(text,str) else text)

    def meta_paths(self):
        return list((self.root / "data").glob("simulation/*/*/metadata.json"))

    def session_path(self):
        return next(p.parent for p in self.meta_paths() if json.loads(p.read_text())["kind"] in ("monitor", "session"))

    def type_and_check(self, key, expected, phase="MONITOR"):
        path = self.session_path()
        before = len(rows(path / "raw.csv"))
        status_before = self.text.count(phase+" |")
        self.send(key)
        self.read_for(.5)  # >= 6 status intervals; actual proxy prints in batches
        self.wait(lambda: self.prompt_line() == "robonose> "+expected, timeout=3)
        after = len(rows(path / "raw.csv"))
        printed = self.text.count(phase+" |")-status_before
        assert after > before and printed >= 2, self.text
        assert "MONITOR" not in self.prompt_line()
        self.proof.append({"typed":expected,"display":self.prompt_line(),"rows_before":before,
                           "rows_after":after,"status_lines":printed})

    def finish(self, key):
        self.send(key)
        until = time.monotonic()+40
        while self.p.poll() is None and time.monotonic() < until:
            self.read_for(.05)  # drain PTY so cleanup output never blocks the child
        assert self.p.poll() == 0, self.text
        self.read_for(.1)
        # Input must restore termios after interrupt, EOF and external cancellation.
        assert termios.tcgetattr(self.master)[3] & (termios.ICANON | termios.ECHO) == self.original_termios[3] & (termios.ICANON | termios.ECHO)

    def close(self):
        if self.p.poll() is None:
            self.p.send_signal(signal.SIGTERM)
            until = time.monotonic()+40
            while self.p.poll() is None and time.monotonic()<until:
                self.read_for(.05)
            if self.p.poll() is None:
                self.p.kill()
                self.p.wait()
        os.close(self.master)
        (self.root / "pty_console.txt").write_text(self.text, encoding="utf-8")
        (self.root / "pty_proof.json").write_text(json.dumps(self.proof,ensure_ascii=False,indent=2),encoding="utf-8")

@pytest.mark.parametrize("mode", ["monitor", "collect"])
def test_slow_tty_start_backspace_unicode_and_ctrl_c(tmp_path, mode):
    app = TerminalProcess(tmp_path, mode)
    try:
        app.wait(lambda: "MONITOR |" in app.text and app.prompt_line()=="robonose>")
        typed = ""
        for char in "start":
            typed += char
            app.type_and_check(char, typed)
        app.type_and_check("x", "startx")
        app.type_and_check(b"\x7f", "start")
        app.send("\r")
        app.wait(lambda: "Pha BASELINE" in app.text)
        app.send("mark thử nghiệm")
        app.read_for(.5)
        app.wait(lambda: app.prompt_line()=="robonose> mark thử nghiệm")
        app.send("\r")
        app.wait(lambda: any(e["event"] == "marker" for e in rows(app.session_path()/"events.csv")))
        app.wait(lambda: "Pha WAIT_EXPOSURE" in app.text)
        app.finish(b"\x03")
        session_events = rows(app.session_path()/"events.csv")
        starts = [json.loads(e["details_json"]) for e in session_events
                  if e["event"] == "command_received" and json.loads(e["details_json"])["raw"] == "start"]
        assert len(starts)==1 and starts[0]["normalized"]=="start"
        transitions = [e for e in session_events if e["event"]=="phase_change"
                       and json.loads(e["details_json"]).get("to")=="BASELINE"]
        assert len(transitions)==1
        assert app.text.count("Pha BASELINE")==1
        assert any(json.loads(e["details_json"]).get("text")=="thử nghiệm" for e in session_events if e["event"]=="marker")
        run_meta = next(json.loads(p.read_text()) for p in app.meta_paths() if json.loads(p.read_text())["kind"]=="collect")
        assert run_meta["status"]=="ABORTED" and run_meta["end_reason"]=="Ctrl+C"
        assert run_meta["durations"]["BASELINE"]["actual_s"]==pytest.approx(2,abs=1e-9)
    finally:
        app.close()

@pytest.mark.parametrize("ending", [b"\x04", "quit\r"])
def test_tty_eof_and_quit_restore_terminal(tmp_path, ending):
    app = TerminalProcess(tmp_path)
    try:
        app.wait(lambda: "MONITOR |" in app.text and app.prompt_line()=="robonose>")
        app.read_for(.25)
        app.finish(ending)
        meta = json.loads((app.session_path()/"metadata.json").read_text())
        assert meta["status"]=="COMPLETE" and meta["rows"]>0
        if ending==b"\x04":
            assert meta["end_reason"]=="stdin EOF"
    finally:
        app.close()

@pytest.mark.parametrize("line", ["start", " start \r\n", "\tStArT\t\r\n"])
def test_start_normalization_and_deadline(line):
    args = parser().parse_args(["collect", "--sim"])
    session = Session(args, load(), reader=object())
    session.acq = SimpleNamespace(thread=SimpleNamespace(is_alive=lambda:True))
    session.run = SimpleNamespace(meta={})
    session.state = StateMachine(time.monotonic(),session.duration_map)
    changes = []
    session.change = lambda change: changes.append(change) if change else None
    session.command(line)
    assert session.state.phase=="BASELINE" and changes==[("MONITOR","BASELINE")]
    assert session.state.deadline-session.state.since==pytest.approx(30)
    with pytest.raises(ValueError,match="start chỉ hợp lệ trong MONITOR"):
        session.command("start")

def test_start_not_ready_has_specific_reason():
    session = Session(parser().parse_args(["collect","--sim"]),load())
    with pytest.raises(ValueError,match="Chưa sẵn sàng: reader/vòng thu"):
        session.command("start")
