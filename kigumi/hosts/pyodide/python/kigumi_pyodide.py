"""Kigumi's Python, inside Pyodide, for the browser version's worker (hosts/pyodide/worker/).

Kigumi's core runs Python as processes: one-shot commands (`python -c`, `-m module`, a script) and
the long-running runner (runner.py), which reads requests from stdin and writes replies to stdout.
In Pyodide there are no processes, so the worker's child_process stand-in calls these instead:
`run_command` for a one-shot command, and a `RunnerSession` per runner, fed one request at a time.

Pyodide has no threads either: the runner's background jobs run after each reply instead.
"""

import contextlib
import importlib.util
import io
import json
import os
import runpy
import sys
import threading
import traceback


def run_command(args_json, cwd):
    """Run a one-shot Python command (its argv after `python`); return its exit code and output, as JSON."""
    args = json.loads(args_json)
    out, err = io.StringIO(), io.StringIO()
    code = 0
    old_argv, old_cwd = sys.argv, os.getcwd()
    try:
        if cwd and os.path.isdir(cwd):
            os.chdir(cwd)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                if args[0] == "-c":
                    sys.argv = ["-c", *args[2:]]
                    exec(compile(args[1], "<string>", "exec"), {"__name__": "__main__"})
                elif args[0] == "-m":
                    sys.argv = [args[1], *args[2:]]
                    runpy.run_module(args[1], run_name="__main__", alter_sys=True)
                else:
                    sys.argv = list(args)
                    runpy.run_path(args[0], run_name="__main__")
            except SystemExit as exit_:
                if exit_.code is None or isinstance(exit_.code, int):
                    code = exit_.code or 0
                else:
                    print(exit_.code, file=sys.stderr)
                    code = 1
            except BaseException:  # noqa: BLE001 -- a command's failure is its exit code, as for a process
                traceback.print_exc()
                code = 1
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
    return json.dumps({"code": code, "stdout": out.getvalue(), "stderr": err.getvalue()})


class _Lines(io.TextIOBase):
    """A text stream that hands each complete line to `emit`."""

    def __init__(self, emit):
        self._emit = emit
        self._buffer = ""

    def writable(self):
        return True

    def write(self, text):
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit(line + "\n")
        return len(text)


class _Threads:
    """threading, but a Thread's work waits to run until the session runs it (after each reply)."""

    def __init__(self, pending):
        self._pending = pending

    def __getattr__(self, name):
        return getattr(threading, name)

    def Thread(self, target=None, args=(), kwargs=None, name=None, daemon=None):  # noqa: N802 -- threading's name
        pending = self._pending

        class _Deferred:
            def start(self):
                pending.append((target, args, kwargs or {}))

        return _Deferred()


class RunnerSession:
    """One runner (kigumi/runner.py), fed its stdin a line at a time; its stdout and stderr go to `out` and `err`."""

    _count = 0

    def __init__(self, runner_path, argv_json, out, err):
        RunnerSession._count += 1
        self._out = _Lines(out)
        self._err = _Lines(err)
        self._pending = []
        argv = json.loads(argv_json)
        old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
        sys.argv = [runner_path, *argv]
        sys.stdout, sys.stderr = self._err, self._err
        try:
            # Its own module per session, as each was its own process: the runner keeps state in globals.
            name = f"kigumi_runner_{RunnerSession._count}"
            spec = importlib.util.spec_from_file_location(name, runner_path)
            self._runner = importlib.util.module_from_spec(spec)
            # Registered before it runs, as an import does: dataclasses looks a class's module up there.
            sys.modules[name] = self._runner
            spec.loader.exec_module(self._runner)
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
        self._runner.threading = _Threads(self._pending)
        self._runner._protocol_out = self._out
        self._argv = argv
        self._state = None
        self.alive = True

    @contextlib.contextmanager
    def _streams(self):
        old_stdout, old_stderr, old_argv = sys.stdout, sys.stderr, sys.argv
        sys.stdout, sys.stderr = self._err, self._err
        sys.argv = [sys.argv[0], *self._argv]
        try:
            yield
        finally:
            sys.stdout, sys.stderr, sys.argv = old_stdout, old_stderr, old_argv

    def start(self):
        """Load the target file and say ready, as main() does; False if it could not."""
        runner = self._runner
        with self._streams():
            try:
                initial = runner.load_slot_state(self._argv[0])
                self._state = runner.RunnerState(slots={"main": initial}, active_slot="main")
            except Exception as exc:  # noqa: BLE001 -- reported as the runner reports it
                runner.emit_message({"type": "fatal_error", "error": {
                    "message": str(exc), "type": type(exc).__name__, "traceback": traceback.format_exc()}})
                self.alive = False
                return False
            runner.emit_message(runner.make_ready_event(self._state))
        return True

    def handle(self, line):
        """Answer one request line, then run the background jobs it started; False once the runner exits."""
        runner = self._runner
        line = line.strip()
        if not line or not self.alive:
            return self.alive
        with self._streams():
            request = {}
            try:
                request = json.loads(line)
                self._state, response, should_exit = runner.handle_request(self._state, request)
                runner.emit_message(response)
                if should_exit:
                    self.alive = False
            except Exception as exc:  # noqa: BLE001 -- as main()'s loop
                response = runner.make_error_response(request.get("id"), request.get("command", "unknown"), exc)
                failed = self._state.slots.get(runner._resolve_slot_name(self._state, request.get("payload") or {}))
                if failed is not None and failed.kiwari_groups:
                    response["kiwari"] = runner._serialize_kiwari_for_slot(failed, stale=True)
                runner.emit_message(response)
            self.run_jobs()
        return self.alive

    def run_jobs(self):
        """Run the background jobs started so far, in order."""
        while self._pending:
            target, args, kwargs = self._pending.pop(0)
            target(*args, **kwargs)
