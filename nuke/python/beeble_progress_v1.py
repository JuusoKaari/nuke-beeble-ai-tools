# Purpose:
# - Global Beeble progress dialog for Nuke runner scripts (Python 2.7 / 3.x).
# - Wraps helper subprocess execution with nuke.ProgressTask and streams stdout to the Script Editor.

from __future__ import print_function

import json
import re
import subprocess
import threading

try:
    import Queue as _queue_mod
except ImportError:
    import queue as _queue_mod

_POLL_TIMEOUT_SEC = 0.1

_UPLOAD_RE = re.compile(r"Uploading", re.I)
_START_RE = re.compile(r"Starting SwitchX", re.I)
# Legacy SwitchX uses completed/failed; Product API uses success/cancelled/credit_required.
_POLL_RE = re.compile(
    r"status=(in_queue|processing|completed|failed|success|cancelled|credit_required)",
    re.I,
)
_PROGRESS_RE = re.compile(r"progress=(\d+)", re.I)
_DOWNLOAD_RE = re.compile(r"Downloading output", re.I)
_RETRY_RE = re.compile(r"WARNING:\s*Beeble request failed", re.I)
_ERROR_RE = re.compile(r"^ERROR:", re.I)


class BeebleProgressCancelled(Exception):
    """Raised when the user cancels the Beeble progress dialog."""


def decode_subprocess_line(line):
    if line is None:
        return ""
    if isinstance(line, bytes):
        try:
            return line.decode("utf-8", "replace")
        except Exception:
            try:
                return str(line)
            except Exception:
                return ""
    try:
        return str(line)
    except Exception:
        return ""


def progress_update_from_line(text, state):
    text = (text or "").strip()
    if not text:
        return False

    if _ERROR_RE.match(text):
        state["message"] = text[:160]
        return True

    if _RETRY_RE.search(text):
        state["message"] = "Retrying Beeble request..."
        return True

    if _DOWNLOAD_RE.search(text):
        state["message"] = text[:160]
        state["phase"] = "download"
        return True

    if _UPLOAD_RE.search(text):
        state["message"] = text[:160]
        state["phase"] = "upload"
        return True

    if _START_RE.search(text):
        state["message"] = text[:160]
        state["phase"] = "waiting"
        return True

    if _POLL_RE.search(text) or _PROGRESS_RE.search(text):
        state["message"] = text[:160]
        state["phase"] = "waiting"
        return True

    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and obj.get("ok"):
                state["message"] = "Done"
                state["phase"] = "done"
                return True
        except Exception:
            pass

    return False


def _terminate_process(process):
    if process is None:
        return
    try:
        process.terminate()
    except Exception:
        pass
    try:
        process.kill()
    except Exception:
        pass


def _refresh_progress_task(task, state, nuke_module):
    try:
        task.setMessage(str(state.get("message", "Running Beeble SwitchX...")))
    except Exception:
        pass
    try:
        nuke_module.updateUI()
    except Exception:
        pass


def _start_stdout_reader(process, line_queue):
    def _reader():
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line_queue.put(line)
        finally:
            line_queue.put(None)

    thread = threading.Thread(target=_reader)
    thread.daemon = True
    thread.start()
    return thread


def run_helper_subprocess(args, env=None, title="Beeble SwitchX", initial_message="Running Beeble SwitchX..."):
    import nuke

    state = {
        "message": initial_message,
        "phase": "start",
    }

    task = nuke.ProgressTask(title or "Beeble SwitchX")
    _refresh_progress_task(task, state, nuke)

    stdout_lines = []
    process = None
    returncode = 1

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            env=env,
        )

        line_queue = _queue_mod.Queue()
        reader_thread = _start_stdout_reader(process, line_queue)

        while True:
            if task.isCancelled():
                _terminate_process(process)
                raise BeebleProgressCancelled()

            try:
                line = line_queue.get(timeout=_POLL_TIMEOUT_SEC)
            except _queue_mod.Empty:
                if process.poll() is not None and line_queue.empty():
                    break
                _refresh_progress_task(task, state, nuke)
                continue

            if line is None:
                break

            text = decode_subprocess_line(line).rstrip("\r\n")
            stdout_lines.append(text)
            try:
                print(text)
            except Exception:
                pass

            if progress_update_from_line(text, state):
                _refresh_progress_task(task, state, nuke)

        try:
            reader_thread.join(timeout=1.0)
        except Exception:
            pass

        returncode = int(process.wait())
        if returncode == 0:
            state["message"] = "Done"
            _refresh_progress_task(task, state, nuke)
        return returncode, stdout_lines
    finally:
        try:
            del task
        except Exception:
            pass
