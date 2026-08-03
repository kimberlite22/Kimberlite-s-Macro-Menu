"""Discovery and lifecycle helpers for the hidden AutoHotkey engine process."""

from __future__ import annotations

import csv
import ctypes
import io
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.launcher_paths import ENGINE_EXE_NAME, is_frozen, source_repo_root


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
READY_FILE_NAME = "engine_ready.txt"
COMMAND_FILE_NAME = "local_cmd.txt"
# The whole engine shutdown runs synchronously on the Qt main thread inside aboutToQuit, so every
# step of it is bounded. Each of the two waits below used to be five seconds, with a third after
# Popen.kill(), which is what made closing the app visibly slow.
ENGINE_SHUTDOWN_TIMEOUT_SECONDS = 1.0
# Separate, deliberately more generous bound for the tasklist.exe process queries: they also run
# at STARTUP, where timing out means concluding "no engine is running" and starting a second one.
# It exists so a wedged tasklist.exe cannot hang shutdown either, not to make those queries quick.
PROCESS_QUERY_TIMEOUT_SECONDS = 5.0


def find_engine_executable(install_directory: Path | None) -> list[str] | None:
    """Return the command needed to run the bundled or development engine.

    A frozen onefile bundle extracts its engine to a temporary directory, so copy that
    payload to a stable location next to the installed GUI on every launch.
    """
    if is_frozen():
        try:
            bundle_directory = Path(getattr(sys, "_MEIPASS"))
            bundled_engine = bundle_directory / "engine" / ENGINE_EXE_NAME
            if not bundled_engine.is_file() or install_directory is None:
                return None
            # Directly in install_directory, not a further "engine" subfolder: this path lives
            # under the user's own profile (LOCALAPPDATA), whose length is out of this app's
            # control - a long username or a redirected/OneDrive profile can push a deeply nested
            # path past Windows' 260-character MAX_PATH, which fails process creation with an
            # opaque error rather than a clear one. Every extra path segment/character here is
            # pure risk with no benefit, which is also why ENGINE_EXE_NAME itself is short.
            stable_engine = install_directory / ENGINE_EXE_NAME
            stable_engine.parent.mkdir(parents=True, exist_ok=True)
            staging_engine = stable_engine.with_suffix(f"{stable_engine.suffix}.staging")
            try:
                shutil.copy2(bundled_engine, staging_engine)
                os.replace(staging_engine, stable_engine)
            except Exception:
                try:
                    staging_engine.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            return [str(stable_engine)]
        except (AttributeError, OSError, TypeError):
            return None

    macro_directory = source_repo_root() / "macro"
    autohotkey_executable = shutil.which("AutoHotkey64.exe")
    source_script = macro_directory / "tower_defense_macro_gui.ahk"
    if autohotkey_executable and source_script.is_file():
        return [autohotkey_executable, str(source_script), "--headless"]
    return None


def is_engine_running() -> bool:
    """Check tasklist output for the exact engine image name, independent of locale."""
    try:
        completed = subprocess.run(
            [
                "tasklist.exe",
                "/FI",
                f"IMAGENAME eq {ENGINE_EXE_NAME}",
                "/FO",
                "CSV",
                "/NH",
            ],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=PROCESS_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return ENGINE_EXE_NAME in (completed.stdout or "")


def get_engine_pid() -> int | None:
    """Return the PID of the running engine process, or None if it is not running.

    Used to take shutdown ownership of an engine this launch merely found already running
    (attached to, not spawned), so no ``subprocess.Popen`` handle exists for it.
    """
    try:
        completed = subprocess.run(
            [
                "tasklist.exe",
                "/FI",
                f"IMAGENAME eq {ENGINE_EXE_NAME}",
                "/FO",
                "CSV",
                "/NH",
            ],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=PROCESS_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = completed.stdout or ""
    if ENGINE_EXE_NAME not in output:
        return None
    try:
        row = next(csv.reader(io.StringIO(output.splitlines()[0])))
        return int(row[1])
    except (StopIteration, IndexError, ValueError):
        return None


def launch_engine_hidden(argv: Sequence[str], data_directory: Path) -> subprocess.Popen[Any] | None:
    """Start the engine without a visible console and return its process handle."""
    command = [str(argument) for argument in argv]
    if not command:
        return None
    if Path(command[0]).name.casefold() == ENGINE_EXE_NAME.casefold() and "--headless" not in command:
        command.append("--headless")

    # The engine deletes this itself while it initializes.  Removing it before process creation
    # also closes the tiny race where a stale marker from a crashed prior engine is observed first.
    try:
        (data_directory / READY_FILE_NAME).unlink(missing_ok=True)
    except OSError:
        pass

    try:
        return subprocess.Popen(command, creationflags=CREATE_NO_WINDOW)
    except OSError:
        return None


def wait_for_engine_ready(
    data_directory: Path,
    timeout_seconds: float = 15.0,
    *,
    pump: Callable[[], object] | None = None,
) -> bool:
    """Poll the engine readiness marker while optionally keeping Qt responsive."""
    marker_path = data_directory / READY_FILE_NAME
    deadline = time.monotonic() + timeout_seconds
    while True:
        if marker_path.exists():
            return True
        if time.monotonic() >= deadline:
            return False
        if pump is not None:
            pump()
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))


def wait_for_local_command_slot(
    data_directory: Path,
    timeout_seconds: float = 15.0,
    *,
    pump: Callable[[], object] | None = None,
) -> bool:
    """Wait until the bridge's command file and its atomic-write staging file are absent.

    This deliberately observes only: a command left by an earlier GUI can have an unknown
    outcome, so this launcher must neither remove it nor republish it.  The caller may then safely
    issue the window's automatic initial command without overwriting that pending work.
    """
    command_path = data_directory / COMMAND_FILE_NAME
    staging_path = command_path.with_name(command_path.name + ".tmp")
    deadline = time.monotonic() + timeout_seconds
    while command_path.exists() or staging_path.exists():
        if time.monotonic() >= deadline:
            return False
        if pump is not None:
            pump()
        # A Qt event may have let the engine consume the command. Recheck before sleeping so the
        # UI can proceed immediately rather than always adding one polling interval at startup.
        if not command_path.exists() and not staging_path.exists():
            return True
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
    return True


def stop_engine(
    process: subprocess.Popen[Any] | None,
    timeout_seconds: float = ENGINE_SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    """Stop only an engine process that this GUI launch owns, gracefully when possible."""
    if process is None or process.poll() is not None:
        return

    _run_taskkill(["taskkill.exe", "/PID", str(process.pid)], timeout_seconds)
    try:
        process.wait(timeout=timeout_seconds)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    # /T is required because the engine starts ocr_server.exe, which PyInstaller's onefile build
    # runs as a bootloader process plus a child. Killing only the engine PID orphans both: this
    # machine currently holds three such orphaned ocr_server.exe pairs from three different days,
    # and StopOcrServer() in tower_defense_macro_gui.ahk is defined but never called from anywhere,
    # so nothing on the engine side stops them either. Popen.terminate()/kill() are exactly that
    # same single-process kill, which is why the escalation goes through taskkill /T instead.
    _run_taskkill(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], timeout_seconds)
    try:
        process.wait(timeout=timeout_seconds)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Last resort, and only reachable when taskkill.exe itself could not be launched or did not
    # take: this launch still owns a real process handle, so use it rather than exiting with the
    # engine left running. It cannot reach the engine's children, which is why it stays last.
    for finish in (process.terminate, process.kill):
        try:
            finish()
            process.wait(timeout=timeout_seconds)
            return
        except (OSError, subprocess.TimeoutExpired):
            continue


def _run_taskkill(command: list[str], timeout_seconds: float) -> None:
    """Run one taskkill request without letting it block the shutdown path.

    Every failure mode is swallowed on purpose (the caller escalates on its own): a taskkill.exe
    that cannot be launched at all, a non-zero result, and taskkill.exe itself hanging, which the
    explicit timeout is there to bound. Without it the "bounded shutdown" this module promises
    would still depend on an external process returning.
    """
    try:
        subprocess.run(
            command,
            check=False,
            creationflags=CREATE_NO_WINDOW,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _kernel32() -> Any:
    """Return kernel32 with the three process functions typed, or None when unavailable.

    ``ctypes.wintypes`` only imports on Windows, so this stays lazy: importing it at module scope
    would make the whole module unimportable anywhere else.
    """
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes

        library = ctypes.windll.kernel32
        library.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        library.OpenProcess.restype = wintypes.HANDLE
        library.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        library.WaitForSingleObject.restype = wintypes.DWORD
        library.CloseHandle.argtypes = [wintypes.HANDLE]
        library.CloseHandle.restype = wintypes.BOOL
        return library
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def _open_process_handle(pid: int) -> Any:
    """Open a SYNCHRONIZE handle to `pid`, or return None when it cannot be opened."""
    library = _kernel32()
    if library is None:
        return None
    try:
        # PROCESS_SYNCHRONIZE: enough to wait on the process, and nothing more.
        return library.OpenProcess(0x00100000, False, pid) or None
    except (AttributeError, OSError, ValueError):
        return None


def _close_process_handle(handle: Any) -> None:
    """Release a handle from `_open_process_handle`, ignoring a failure to do so."""
    library = _kernel32()
    if library is None or not handle:
        return
    try:
        library.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        pass


def _wait_for_process_exit(handle: Any, timeout_seconds: float) -> bool | None:
    """Wait on an open process handle: True exited, False still running, None not observable."""
    library = _kernel32()
    if library is None or not handle:
        return None
    try:
        result = library.WaitForSingleObject(handle, max(0, int(timeout_seconds * 1000)))
    except (AttributeError, OSError, ValueError):
        return None
    if result == 0:  # WAIT_OBJECT_0
        return True
    if result == 0x102:  # WAIT_TIMEOUT
        return False
    return None


def stop_engine_by_pid(
    pid: int,
    timeout_seconds: float = ENGINE_SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    """Stop an engine process this launch merely attached to (found already running).

    No ``subprocess.Popen`` handle exists for it, so ownership is exercised through a real Windows
    process handle instead. If that handle cannot be opened, the image-name polling fallback keeps
    its replacement-process safety check.
    """
    # Opened BEFORE the graceful request and held until the escalation is done, not just around the
    # wait: Windows will not reuse a PID while a handle to it is open, so the graceful request, the
    # wait and the force-kill all address one and the same process. Opening it only for the wait
    # would leave two windows (before the wait, and between the wait and the force-kill) in which
    # that process could exit and its PID be handed to an unrelated one.
    handle = _open_process_handle(pid)
    try:
        _run_taskkill(["taskkill.exe", "/PID", str(pid)], timeout_seconds)

        exited = _wait_for_process_exit(handle, timeout_seconds)
        if exited is True:
            return
        if exited is None:
            # Fallback for a handle that could not be opened at all. This is the old behavior: it
            # infers liveness by scraping tasklist.exe output, one process spawn per poll, each
            # typically costing more than the 200 ms sleep between polls.
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if get_engine_pid() != pid:
                    return
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))

        # The handle pins this PID only from the moment it was opened, which is here, at shutdown.
        # The PID itself was captured back when this launch attached to an already-running engine,
        # so between those two moments that engine could have exited and Windows could have handed
        # its PID to something else entirely. Confirm the engine image still holds it before
        # force-killing anything. One tasklist.exe spawn, and only on the escalation path: the
        # common case returned above without it.
        if get_engine_pid() != pid:
            return
        _run_taskkill(["taskkill.exe", "/PID", str(pid), "/T", "/F"], timeout_seconds)
    finally:
        _close_process_handle(handle)
