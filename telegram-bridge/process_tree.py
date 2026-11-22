"""Run a command with a deadline that really ends the whole process tree.

22.11: the developer call had ``subprocess.run(timeout=30 min)``. On timeout Python kills
only the direct child and then waits for the output pipes — which grandchildren (sandbox,
code host, the test gate) keep open. The bot waited 4 h 50 min; the task queue stood still.
"""
import os
import signal
import subprocess


def run(command, *, timeout, input=None, grace=5, **kwargs):
    """Like ``subprocess.run(..., capture_output=True, text=True)``; raises TimeoutExpired
    only after the whole process group is gone."""
    process = subprocess.Popen(command, start_new_session=True, stdin=subprocess.PIPE if input is not None else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=grace)
        except subprocess.TimeoutExpired:
            _kill_group(process.pid, signal.SIGKILL)
            try:
                process.communicate(timeout=grace)
            except subprocess.TimeoutExpired:
                pass  # pipes held by a process outside the group: do not wait for them
        raise subprocess.TimeoutExpired(command, timeout)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _kill_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass
