"""PTY-based Claude Code CLI runner to capture /usage output."""

import os
import re
import shutil
import time
import tempfile
import threading
import queue
from enum import Enum, auto

from config import CLAUDE_CMD, PTY_TIMEOUT_S, PTY_COLS, PTY_ROWS

# Strip ANSI escape sequences
_ANSI_RE = re.compile(r'\x1b\[[^@-~]*[@-~]|\x1b[^[]|\x1b\].*?\x07|\r')

# Patterns for state machine
# Trust dialog uses cursor-positioning — spaces are stripped, words run together
_TRUST_PROMPT_RE = re.compile(r'trust.{0,10}folder|trustthisfolder|Entertoconfirm', re.IGNORECASE)
_BANNER_RE = re.compile(r'Claude Code|╭|Welcome', re.IGNORECASE)
_USAGE_HEADER_RE = re.compile(r'Current session|Current week|Extra usage', re.IGNORECASE)

# After this many seconds with any output, stop waiting for banner and proceed
_BANNER_FALLBACK_S = 8.0


class _State(Enum):
    WAITING_FOR_BANNER = auto()
    CONFIRMING_TRUST = auto()   # auto-press Enter on the trust dialog
    SENDING_STATUS = auto()
    CAPTURING_STATUS = auto()
    SENDING_USAGE = auto()
    CAPTURING_USAGE = auto()
    DONE = auto()


def _resolve_claude_path() -> str:
    """Resolve full path to the claude executable."""
    found = shutil.which(CLAUDE_CMD)
    if found:
        return found

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".local", "bin", "claude.exe"),
        os.path.join(home, ".local", "bin", "claude"),
        os.path.join(home, "AppData", "Local", "Programs", "claude", "claude.exe"),
    ]
    npm_prefix = os.environ.get("APPDATA")
    if npm_prefix:
        candidates.append(os.path.join(npm_prefix, "npm", "claude.cmd"))

    for path in candidates:
        if os.path.isfile(path):
            return path

    raise RuntimeError(
        f"Claude Code not found on PATH or in common locations.\n"
        f"Searched: PATH, ~/.local/bin/claude.exe"
    )


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences and carriage returns."""
    return _ANSI_RE.sub('', text)


def _reader_thread(proc, data_queue: queue.Queue, stop_event: threading.Event):
    """Background thread that reads from PTY and puts chunks into a queue."""
    while not stop_event.is_set():
        try:
            chunk = proc.read(4096)
            if chunk:
                data_queue.put(chunk)
        except EOFError:
            data_queue.put(None)  # signal EOF
            break
        except Exception:
            time.sleep(0.05)


def run_usage() -> tuple[str, str]:
    """
    Spawn Claude Code CLI in a PTY, send /status, then /usage,
    and return both outputs (status, usage).
    Raises RuntimeError on failure.
    """
    try:
        import winpty
    except ImportError:
        raise RuntimeError("pywinpty is not installed. Run: pip install pywinpty")

    claude_path = _resolve_claude_path()
    tmpdir = tempfile.mkdtemp(prefix="claude_usage_")
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"

    try:
        proc = winpty.PtyProcess.spawn(
            claude_path,
            dimensions=(PTY_ROWS, PTY_COLS),
            cwd=tmpdir,
            env=env,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to spawn Claude Code ({claude_path}): {e}")

    # Start a reader thread so we don't block on proc.read()
    data_queue = queue.Queue()
    stop_event = threading.Event()
    reader = threading.Thread(
        target=_reader_thread, args=(proc, data_queue, stop_event), daemon=True
    )
    reader.start()

    state = _State.WAITING_FOR_BANNER
    buffer = ""
    deadline = time.monotonic() + PTY_TIMEOUT_S
    first_output_at = None
    send_cmd_at = None
    status_buffer = ""
    usage_buffer = ""
    last_data_at = time.monotonic()
    state_start_at = time.monotonic()

    try:
        eof_reached = False
        while time.monotonic() < deadline:
            # Drain the queue (non-blocking)
            got_data = False
            while True:
                try:
                    chunk = data_queue.get_nowait()
                    if chunk is None:
                        # EOF
                        eof_reached = True
                        break
                    buffer += chunk
                    got_data = True
                    last_data_at = time.monotonic()
                    if first_output_at is None:
                        first_output_at = time.monotonic()
                except queue.Empty:
                    break

            if state == _State.WAITING_FOR_BANNER:
                clean = strip_ansi(buffer)
                if _TRUST_PROMPT_RE.search(clean):
                    # Auto-confirm the folder trust dialog
                    time.sleep(0.3)
                    proc.write("\r")
                    state = _State.CONFIRMING_TRUST
                    state_start_at = time.monotonic()
                    buffer = ""
                elif _BANNER_RE.search(clean):
                    state = _State.SENDING_STATUS
                    state_start_at = time.monotonic()
                    send_cmd_at = time.monotonic() + 0.5
                elif (
                    first_output_at is not None
                    and (time.monotonic() - first_output_at) > _BANNER_FALLBACK_S
                ):
                    # Fallback: just try sending /status anyway
                    state = _State.SENDING_STATUS
                    state_start_at = time.monotonic()
                    send_cmd_at = time.monotonic() + 0.1

            elif state == _State.CONFIRMING_TRUST:
                clean = strip_ansi(buffer)
                # Wait for the real prompt to appear after trust confirmation
                if _BANNER_RE.search(clean):
                    state = _State.SENDING_STATUS
                    state_start_at = time.monotonic()
                    send_cmd_at = time.monotonic() + 1.0
                elif (
                    first_output_at is not None
                    and (time.monotonic() - first_output_at) > _BANNER_FALLBACK_S + 5
                ):
                    state = _State.SENDING_STATUS
                    state_start_at = time.monotonic()
                    send_cmd_at = time.monotonic() + 0.5

            elif state == _State.SENDING_STATUS:
                if time.monotonic() >= send_cmd_at:
                    proc.write("/status\r")
                    state = _State.CAPTURING_STATUS
                    state_start_at = time.monotonic()
                    buffer = ""

            elif state == _State.CAPTURING_STATUS:
                if got_data:
                    status_buffer += buffer
                    buffer = ""
                clean = strip_ansi(status_buffer)
                
                # Robust transition: if we see an email OR if it's been silent for 2s after some data
                # OR if it's been 5s since we started capturing status
                time_in_state = time.monotonic() - state_start_at
                silence_time = time.monotonic() - last_data_at
                
                if (
                    ("@" in clean or "logged" in clean.lower())
                    or (silence_time > 0.8 and len(clean.strip()) > 0)
                    or (time_in_state > 3.0)
                ):
                    # User Hint: Status UI must be dismissed with Esc before sending next command
                    proc.write("\x1b")
                    time.sleep(0.2)
                    state = _State.SENDING_USAGE
                    state_start_at = time.monotonic()
                    send_cmd_at = time.monotonic() + 0.1

            elif state == _State.SENDING_USAGE:
                if time.monotonic() >= send_cmd_at:
                    # Resize trick to force full re-render
                    try:
                        proc.setwinsize(PTY_ROWS, PTY_COLS - 1)
                        time.sleep(0.05)
                        proc.setwinsize(PTY_ROWS, PTY_COLS)
                    except Exception:
                        pass
                    time.sleep(0.1)
                    proc.write("/usage\r")
                    state = _State.CAPTURING_USAGE
                    state_start_at = time.monotonic()
                    usage_buffer = ""
                    buffer = ""  # reset to capture fresh

            elif state == _State.CAPTURING_USAGE:
                if got_data:
                    usage_buffer += buffer
                    buffer = ""
                clean = strip_ansi(usage_buffer)
                
                # Check for usage headers OR a reasonable silence timeout
                time_in_state = time.monotonic() - state_start_at
                silence_time = time.monotonic() - last_data_at
                
                if _USAGE_HEADER_RE.search(clean):
                    # We found usage data — wait a bit more for the full output
                    time.sleep(1.0)
                    # Drain any remaining data
                    while True:
                        try:
                            chunk = data_queue.get_nowait()
                            if chunk is None:
                                break
                            usage_buffer += chunk
                        except queue.Empty:
                            break
                    state = _State.DONE
                    break
                elif silence_time > 5.0 and len(clean.strip()) > 10:
                    # Fallback if we have some data but headers never matched
                    state = _State.DONE
                    break

            if eof_reached:
                break
            
            time.sleep(0.1)

        if state == _State.DONE:
            return strip_ansi(status_buffer), strip_ansi(usage_buffer)

        # Error cases
        all_text = strip_ansi(buffer + status_buffer + usage_buffer)
        preview = all_text[:300].strip() or "(no output)"
        raise RuntimeError(f"Failed to capture data in state {state}.\nReceived: {preview}")

    finally:
        stop_event.set()
        try:
            proc.write("/exit\r")
            time.sleep(0.2)
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def run_usage_threaded(callback, error_callback=None):
    """
    Run capture in a daemon thread.
    Calls callback(status_text, usage_text) on success, error_callback(msg) on failure.
    """
    def _worker():
        try:
            status, usage = run_usage()
            callback(status, usage)
        except Exception as e:
            if error_callback:
                error_callback(str(e))
            else:
                callback(None, None)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t
