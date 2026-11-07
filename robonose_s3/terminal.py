"""Daemon input reader. Console editing never runs on Qt, engine or writer threads."""
import codecs
import os
import sys
import threading


class Terminal:
    def __init__(self, session, stream=None):
        self.session = session
        self.stream = stream or sys.stdin
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._read, name="terminal-input", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stopping.set()  # Never join a pipe/console waiting for Enter.

    def _dispatch(self, line):
        if line.strip() and not self.session.post(line.strip()):
            print("Command queue busy/closed; retry after status updates.", flush=True)

    def _read(self):
        try:
            if os.name == "nt" and self.stream.isatty():
                self._windows_console()
                return
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            pending = ""
            fd = self.stream.fileno()
            while not self.stopping.is_set():
                block = os.read(fd, 1024)  # No Python buffered stdin lock at interpreter shutdown.
                if not block:
                    if pending.strip():
                        self._dispatch(pending)
                    if getattr(self.session, "mode", "SIMULATED") != "SIMULATED":
                        self.session.request_stop("EOF")
                    elif not self.session.post("quit"):
                        self.session.request_stop("EOF")
                    return
                pending += decoder.decode(block)
                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    self._dispatch(line.rstrip("\r"))
                if len(pending) > 2048:
                    pending = ""
                    self.session.request_stop("Terminal input limit exceeded")
        except (OSError, ValueError, AttributeError) as error:
            if not self.stopping.is_set():
                self.session.request_stop(f"stdin unavailable: {error}")

    def _windows_console(self):
        import msvcrt
        pending = ""
        while not self.stopping.wait(.02):
            if not msvcrt.kbhit():
                continue
            character = msvcrt.getwch()
            if character in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue
            if character in ("\x03", "\x1a"):
                self.session.request_stop("Ctrl+C" if character == "\x03" else "EOF")
                return
            if character in ("\r", "\n"):
                print(flush=True)
                self._dispatch(pending)
                pending = ""
            elif character == "\b":
                if pending:
                    pending = pending[:-1]
                    print("\b \b", end="", flush=True)
            elif character.isprintable() and len(pending) < 2048:
                pending += character
                print(character, end="", flush=True)
