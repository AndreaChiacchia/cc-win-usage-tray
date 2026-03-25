"""PTY-based Claude Code CLI runner to capture /usage output."""

import os
import re
import shutil
import time
import tempfile
import threading
import queue

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


def _resolve_claude_path() -> str:
    """Resolve full path to the claude executable."""
    import shutil as _shutil
    found = _shutil.which(CLAUDE_CMD)
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


class ClaudePtySession:
    """Persistent PTY session that stays alive across refresh cycles.

    Focus steal (from CreateProcessW) happens only once at spawn time.
    Subsequent query_usage() calls reuse the same PTY — no new console window.
    """

    def __init__(self):
        self._proc = None
        self._tmpdir: str | None = None
        self._data_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()
        self._ready = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _spawn(self):
        """Spawn PTY and wait for banner. Called once, or on recovery."""
        try:
            import winpty
        except ImportError:
            raise RuntimeError("pywinpty is not installed. Run: pip install pywinpty")

        self._cleanup_proc()

        claude_path = _resolve_claude_path()
        self._tmpdir = tempfile.mkdtemp(prefix="claude_usage_")
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"

        try:
            self._proc = winpty.PtyProcess.spawn(
                claude_path,
                dimensions=(PTY_ROWS, PTY_COLS),
                cwd=self._tmpdir,
                env=env,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to spawn Claude Code ({claude_path}): {e}")

        # Fresh stop event + reader thread
        self._stop_event = threading.Event()
        self._drain_queue()
        self._reader = threading.Thread(
            target=_reader_thread,
            args=(self._proc, self._data_queue, self._stop_event),
            daemon=True,
        )
        self._reader.start()

        self._wait_for_banner()
        self._ready = True

    def _wait_for_banner(self):
        """Wait for the Claude banner (or trust dialog + banner)."""
        buffer = ""
        deadline = time.monotonic() + PTY_TIMEOUT_S
        first_output_at = None
        trust_confirmed = False

        while time.monotonic() < deadline:
            while True:
                try:
                    chunk = self._data_queue.get_nowait()
                    if chunk is None:
                        raise RuntimeError("PTY EOF before banner appeared")
                    buffer += chunk
                    if first_output_at is None:
                        first_output_at = time.monotonic()
                except queue.Empty:
                    break

            clean = strip_ansi(buffer)

            if not trust_confirmed and _TRUST_PROMPT_RE.search(clean):
                time.sleep(0.3)
                self._proc.write("\r")
                trust_confirmed = True
                buffer = ""
                continue

            if _BANNER_RE.search(clean):
                time.sleep(0.5)  # let prompt settle
                self._drain_queue()
                return

            if (
                first_output_at is not None
                and (time.monotonic() - first_output_at) > _BANNER_FALLBACK_S
            ):
                time.sleep(0.1)
                self._drain_queue()
                return

            time.sleep(0.05)

        raise RuntimeError("Timeout waiting for Claude banner")

    def _drain_queue(self):
        """Discard all pending data in the queue."""
        while True:
            try:
                self._data_queue.get_nowait()
            except queue.Empty:
                break

    def _drain_to_str(self) -> str:
        """Drain all pending queue data and return as a string."""
        result = ""
        while True:
            try:
                chunk = self._data_queue.get_nowait()
                if chunk is None:
                    break
                result += chunk
            except queue.Empty:
                break
        return result

    def _ensure_alive(self):
        """Re-spawn if the PTY process has died."""
        if self._proc is None or not self._ready:
            self._spawn()
            return
        try:
            if not self._proc.isalive():
                self._cleanup_proc()
                self._spawn()
        except Exception:
            self._cleanup_proc()
            self._spawn()

    def _cleanup_proc(self):
        """Terminate the current process and clean up resources."""
        self._ready = False
        self._stop_event.set()
        if self._proc is not None:
            try:
                self._proc.write("/exit\r")
                time.sleep(0.2)
            except Exception:
                pass
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
        if self._tmpdir:
            try:
                shutil.rmtree(self._tmpdir, ignore_errors=True)
            except Exception:
                pass
            self._tmpdir = None

    def _capture_status(self) -> str:
        """Read /status output until email seen, silence, or timeout."""
        buf = ""
        deadline = time.monotonic() + PTY_TIMEOUT_S
        state_start = time.monotonic()
        last_data_at = time.monotonic()

        while time.monotonic() < deadline:
            while True:
                try:
                    chunk = self._data_queue.get_nowait()
                    if chunk is None:
                        return buf
                    buf += chunk
                    last_data_at = time.monotonic()
                except queue.Empty:
                    break

            clean = strip_ansi(buf)
            silence = time.monotonic() - last_data_at
            elapsed = time.monotonic() - state_start

            if (
                ("@" in clean or "logged" in clean.lower())
                or (silence > 0.5 and len(clean.strip()) > 0)
                or elapsed > 2.0
            ):
                return buf

            time.sleep(0.05)

        return buf

    def _capture_usage(self) -> str:
        """Read /usage output until header found or timeout."""
        buf = ""
        deadline = time.monotonic() + PTY_TIMEOUT_S
        state_start = time.monotonic()
        last_data_at = time.monotonic()

        while time.monotonic() < deadline:
            while True:
                try:
                    chunk = self._data_queue.get_nowait()
                    if chunk is None:
                        return buf
                    buf += chunk
                    last_data_at = time.monotonic()
                except queue.Empty:
                    break

            clean = strip_ansi(buf)
            silence = time.monotonic() - last_data_at

            if _USAGE_HEADER_RE.search(clean):
                # Wait a bit more for the full output, then drain
                time.sleep(0.4)
                buf += self._drain_to_str()
                return buf

            if silence > 3.0 and len(clean.strip()) > 10:
                return buf

            time.sleep(0.05)

        return buf

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query_usage(self) -> tuple[str, str]:
        """Send /status + /usage over the persistent PTY.

        Returns (status_text, usage_text) with ANSI stripped.
        Serializes concurrent calls via self._lock.
        """
        with self._lock:
            self._ensure_alive()
            self._drain_queue()

            # 1. /status
            self._proc.write("/status\r")
            status_raw = self._capture_status()
            self._proc.write("\x1b")   # dismiss status overlay
            time.sleep(0.1)
            self._drain_queue()

            # 2. Resize trick + /usage
            try:
                self._proc.setwinsize(PTY_ROWS, PTY_COLS - 1)
                time.sleep(0.05)
                self._proc.setwinsize(PTY_ROWS, PTY_COLS)
            except Exception:
                pass
            time.sleep(0.05)

            self._proc.write("/usage\r")
            usage_raw = self._capture_usage()
            self._proc.write("\x1b")   # dismiss usage overlay, return to prompt
            time.sleep(0.1)
            self._drain_queue()

            return strip_ansi(status_raw), strip_ansi(usage_raw)

    def close(self):
        """Clean shutdown — send /exit and terminate the PTY."""
        with self._lock:
            self._cleanup_proc()


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_session: ClaudePtySession | None = None
_session_lock = threading.Lock()


def _get_session() -> ClaudePtySession:
    global _session
    with _session_lock:
        if _session is None:
            _session = ClaudePtySession()
        return _session


def close_session():
    """Terminate the persistent PTY session. Call on app quit."""
    global _session
    with _session_lock:
        if _session is not None:
            _session.close()
            _session = None


def force_restart_session():
    """Kill the singleton PTY so the next query spawns a fresh session."""
    global _session
    with _session_lock:
        if _session is not None:
            _session.close()
            _session = None


# ------------------------------------------------------------------
# Public threaded runner — same API as before, transparent to main.py
# ------------------------------------------------------------------

def run_usage_threaded(callback, error_callback=None):
    """
    Run capture in a daemon thread.
    Calls callback(status_text, usage_text) on success, error_callback(msg) on failure.
    """
    def _worker():
        try:
            session = _get_session()
            status, usage = session.query_usage()
            callback(status, usage)
        except Exception as e:
            if error_callback:
                error_callback(str(e))
            else:
                callback(None, None)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t
