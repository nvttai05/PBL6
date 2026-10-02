"""One terminal renderer; commands queue to the timer/writer thread.

Only for an interactive TTY. Pipe/auto modes retain plain output and their
nonblocking decoder. Prompt toolkit owns raw input, editing and every redraw;
all print calls (including analysis/status/error output) go through its proxy.
"""
import asyncio
from contextlib import ExitStack
from contextvars import copy_context
import queue
import sys
import threading


class TerminalInput:
    def __init__(self):
        self.messages = queue.Queue()
        self.stack = ExitStack()
        self.loop = None
        self.task = None
        self.stop = threading.Event()
        self.thread = None

    def __enter__(self):
        from prompt_toolkit import PromptSession
        from prompt_toolkit.input.defaults import create_input
        from prompt_toolkit.output.defaults import create_output
        from prompt_toolkit.patch_stdout import patch_stdout
        try:
            terminal_input = create_input(stdin=sys.stdin)
            self.stack.callback(terminal_input.close)
            terminal_output = create_output(stdout=sys.stdout)
            # A CLI has exactly one terminal. Use toolkit's shared default
            # AppSession: StdoutProxy's flush thread must see the same active
            # application as the UI loop (a thread-local AppSession would not).
            self.prompt = PromptSession("robonose> ", input=terminal_input, output=terminal_output,
                                        enable_open_in_editor=False, enable_suspend=False, erase_when_done=True)
            self.prompt.default_buffer.accept_handler = self.accept
            self.stack.enter_context(patch_stdout())
            # All proxy output is scheduled on this application's event loop.
            context = copy_context()
            self.thread = threading.Thread(target=context.run, args=(self.read,), name="terminal-ui", daemon=True)
            self.thread.start()
            return self
        except BaseException:
            self.stack.close()
            raise

    def accept(self, buffer):
        line = buffer.document.text
        print("robonose> " + line, flush=True)
        self.messages.put(("line", line))
        return False  # clear only AFTER Enter; application remains running

    def read(self):
        asyncio.run(self.read_async())

    async def read_async(self):
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        try:
            if not self.stop.is_set():
                await self.prompt.app.run_async(handle_sigint=False)
        except KeyboardInterrupt:
            self.messages.put(("interrupt", None))
        except EOFError:
            self.messages.put(("eof", None))
        except asyncio.CancelledError:
            pass  # external quit/SIGTERM: restore raw terminal in run_async finally
        except Exception as exc:
            self.messages.put(("error", str(exc)))

    def poll(self, timeout=.02):
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def __exit__(self, *exc):
        self.stop.set()
        while self.thread and self.thread.is_alive():
            if self.loop and not self.loop.is_closed() and self.task:
                try:
                    self.loop.call_soon_threadsafe(self.task.cancel)
                except RuntimeError:
                    pass  # loop finished concurrently
            self.thread.join(timeout=.05)
        self.stack.close()  # proxy flush, app context reset, input close
