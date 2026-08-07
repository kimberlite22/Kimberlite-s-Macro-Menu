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
from typing import Any, NamedTuple

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


class EngineProcess(NamedTuple):
    """One running engine process, and the Windows session it belongs to."""

    pid: int
    session_id: int | None


def current_session_id() -> int | None:
    """Return the Windows session id of this process, or None when it cannot be determined.

    Deliberately self-contained instead of folded into ``_kernel32()``: that helper types the
    three process functions the shutdown path relies on, and one missing symbol there makes it
    return None for all of them at once. Session detection is an optional refinement on top, so
    it must not be able to degrade the shutdown path by failing.
    """
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes

        library = ctypes.windll.kernel32
        library.GetCurrentProcessId.argtypes = []
        library.GetCurrentProcessId.restype = wintypes.DWORD
        library.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        library.ProcessIdToSessionId.restype = wintypes.BOOL
        session = wintypes.DWORD()
        if not library.ProcessIdToSessionId(library.GetCurrentProcessId(), ctypes.byref(session)):
            return None
        return int(session.value)
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def _query_engine_processes() -> list[EngineProcess] | None:
    """Return engine processes, or None when tasklist.exe could not be queried.

    One tasklist.exe spawn now answers "is an engine running", "which PID" and "which session"
    together; those were two separate scrapes with identical arguments before, both of which ran
    back to back on the startup path.

    The IMAGENAME filter is not session scoped, so this deliberately also sees engines in OTHER
    sessions. That is what makes a background RDP session workable at all, because such a session
    shares one user profile, and therefore one set of local bridge files, with the GUI on the
    physical desktop. It is equally the reason the session id has to be carried along: shutdown
    ownership must never be taken over an engine belonging to a different session.
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
    return_code = getattr(completed, "returncode", 0)
    if isinstance(return_code, int) and return_code != 0:
        return None
    output = completed.stdout or ""
    # tasklist.exe reports "no match" through a localized INFO line that never contains the image
    # name, which is what keeps this check independent of the system language.
    if ENGINE_EXE_NAME not in output:
        return []

    processes: list[EngineProcess] = []
    for row in csv.reader(io.StringIO(output)):
        if len(row) < 2 or row[0].strip().casefold() != ENGINE_EXE_NAME.casefold():
            continue
        try:
            pid = int(row[1])
        except ValueError:
            continue
        # Column index 3 is Session#. A row can be shorter (or hold something unparsable), in
        # which case this process simply has an unknown session rather than no entry at all.
        session_id: int | None = None
        if len(row) > 3:
            try:
                session_id = int(row[3])
            except ValueError:
                session_id = None
        processes.append(EngineProcess(pid, session_id))
    return processes


def find_engine_processes() -> list[EngineProcess]:
    """Return every running engine process with the Windows session each one runs in."""
    return _query_engine_processes() or []


def _engine_pid_has_engine_image(pid: int) -> bool | None:
    """Report whether `pid` has the engine image, or None when it cannot be verified."""
    processes = _query_engine_processes()
    if processes is None:
        return None
    return any(process.pid == pid for process in processes)


def engine_pid_is_running(pid: int) -> bool:
    """Report whether `pid` is still held by an engine process.

    Deliberately a membership test rather than "is this the FIRST engine tasklist reports". With
    a background session in play there can legitimately be two engines at once, and comparing
    against only the first row would read the OTHER engine's PID as proof that this one is gone.
    In ``stop_engine_by_pid`` that misreading skips the force-kill and orphans exactly the process
    the call set out to stop.
    """
    return _engine_pid_has_engine_image(pid) is True


def shutdown_owned_engine_pid(processes: Sequence[EngineProcess]) -> int | None:
    """Pick the engine a GUI launch may shut down, or None to leave every engine running.

    Closing the GUI must not kill an engine that belongs to a background session: keeping the
    macro running while the physical desktop is used for something else is that session's entire
    purpose, and ``find_engine_processes`` sees straight across the session boundary.

    When no session id can be determined at all, this falls back to the previous behavior and
    owns the first engine found, so a system without working session detection still cannot be
    left with an orphaned engine.
    """
    if not processes:
        return None
    own_session = current_session_id()
    if own_session is None:
        return processes[0].pid
    for process in processes:
        if process.session_id == own_session:
            return process.pid
    # An engine whose own session could not be read counts as possibly-ours here: orphaning it is
    # the worse of the two failure modes, because nothing else would ever stop it.
    for process in processes:
        if process.session_id is None:
            return process.pid
    return None


def engine_is_in_current_session() -> bool | None:
    """Whether a running engine shares this process's session, or None when undeterminable.

    Callers must read None as "cannot tell" and carry on rather than as a negative answer: it
    also covers the ordinary case of no engine running at all.
    """
    own_session = current_session_id()
    if own_session is None:
        return None
    known = [
        process.session_id
        for process in find_engine_processes()
        if process.session_id is not None
    ]
    if not known:
        return None
    # ALL of them, not "any of them": several engines share one set of bridge files, so a capture
    # command is answered by whichever one consumes it first. With one engine here and another in
    # a background session, the overlay can still open on the desktop the user cannot reach, so
    # that mixed state has to count as not capturable rather than as success.
    return all(session == own_session for session in known)


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
    # runs as a bootloader process plus a child. Killing only the engine PID orphans both, and
    # Popen.terminate()/kill() are exactly that same single-process kill, which is why the
    # escalation goes through taskkill /T instead. The graceful request above deliberately stays
    # without /T: the engine reaps its own helpers from its OnExit handler (ReapHelperProcesses in
    # tower_defense_macro_gui.ahk), and anything that outlives even this escalation is caught by the
    # kill-on-close job object the engine puts every helper into (EnsureHelperJob there).
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
    """Return kernel32 with the process functions typed, or None when unavailable.

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
        library.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        library.QueryFullProcessImageNameW.restype = wintypes.BOOL
        library.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        library.WaitForSingleObject.restype = wintypes.DWORD
        library.CloseHandle.argtypes = [wintypes.HANDLE]
        library.CloseHandle.restype = wintypes.BOOL
        return library
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def _open_process_handle(pid: int) -> Any:
    """Open a queryable, synchronizable handle to `pid`, or return None when unavailable."""
    library = _kernel32()
    if library is None:
        return None
    try:
        # PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE lets this handle identify and wait on
        # the same process without asking tasklist.exe to look the PID up again.
        return library.OpenProcess(0x00101000, False, pid) or None
    except (AttributeError, OSError, ValueError):
        return None


def _process_handle_image_name(handle: Any) -> str | None:
    """Return the full image path for an open process handle, or None on any failure."""
    try:
        library = _kernel32()
        if library is None or not handle:
            return None
        from ctypes import wintypes

        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not library.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value or None
    except Exception:
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
    # Open the handle first precisely so this check and the shutdown that follows address one and
    # the same process. Windows will not reuse a PID while a handle to it is open. The check is
    # about whether that process is our engine, not about whether the PID drifted. The graceful
    # request, wait and force-kill all stay pinned. Opening it only for the wait would leave two
    # windows (before the wait, and between the wait and the force-kill) in which that process
    # could exit and its PID be handed to an unrelated one.
    handle = _open_process_handle(pid)
    try:
        # Read the image from the pinned handle, not by looking the PID up through tasklist.exe.
        # Windows cannot recycle this PID while the handle is open, so its image is authoritative.
        if handle is not None:
            image_name = _process_handle_image_name(handle)
            if image_name is not None and Path(image_name).name.casefold() != ENGINE_EXE_NAME.casefold():
                return
            # A failed read cannot mean a recycled PID because the handle is pinned. In that rare
            # case, leaking a running engine is worse than proceeding with the shutdown request.
        _run_taskkill(["taskkill.exe", "/PID", str(pid)], timeout_seconds)

        exited = _wait_for_process_exit(handle, timeout_seconds)
        if exited is True:
            return
        if handle is None and exited is None:
            # Fallback for a handle that could not be opened at all. This is the old behavior: it
            # infers liveness by scraping tasklist.exe output, one process spawn per poll, each
            # typically costing more than the 200 ms sleep between polls.
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if not engine_pid_is_running(pid):
                    return
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))

        if handle is None and not engine_pid_is_running(pid):
            return
        _run_taskkill(["taskkill.exe", "/PID", str(pid), "/T", "/F"], timeout_seconds)
    finally:
        _close_process_handle(handle)
