"""Start, show and stop the hidden background Windows (RDP) session.

A background session lets the macro run with the physical desktop left free: a second Windows
session, on the same machine and the same user account, reachable only through RDP Wrapper's
loopback trick (127.0.0.2, never 127.0.0.1/localhost - those map to the console session and RDP
fails with error 0x708 even when RDP Wrapper is installed and working). Starting one writes a
throwaway .rdp file, launches mstsc.exe visibly by default, waits for the new session to become
active, then leaves its RDP client connected. A caller can request a hidden client and later
WTSDisconnectSession for a headless run. "Show" reconnects for a look; "Stop" logs the session
off outright.

The sign-in credential is Windows' own: mstsc looks up Credential Manager under the target name
`TERMSRV/<address>` and stores one there itself when the user ticks "Remember me" in its prompt, so
an unattended Start needs no password from this app at all. This module only ever READS whether such
a credential exists (credential_exists, via CredReadW), to say whether the next Start will have to be
answered by hand. It deliberately never writes, prompts for, or holds a password: no password reaches
config.ini, any file this app writes, a command line, or a log. That also rules out cmdkey.exe, whose
only way to accept a password is `/pass:<password>` on its command line, where any same-user process
and any endpoint command-line logging can read it.

Interlock: two engines sharing one user profile would fight over the same config.ini and local
bridge files. The half of that risk this module owns is refusing to START a background session
while an engine is already running on THIS (console) session - see the comment in
start_background_session for why the reverse direction needs no separate check here.
"""

from __future__ import annotations

import csv
import ctypes
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, NamedTuple

from app.engine_process import current_session_id, find_engine_processes
from app.launcher_paths import APP_NAME
from app.window_branding import top_level_windows_for_process


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DEFAULT_SESSION_WAIT_TIMEOUT_SECONDS = 45.0
DISCONNECT_CONFIRM_TIMEOUT_SECONDS = 10.0
# Deliberately longer than the disconnect budget above. Dropping a client is nearly instant, but a
# logoff has to tear down a whole desktop's worth of processes, and a session full of startup
# programs routinely needs more than ten seconds. Measured on the reporting machine: a plain
# Explorer session finished logging off about twelve seconds after the request, which the shorter
# budget reported as a failure even though the logoff was working perfectly.
LOGOFF_CONFIRM_TIMEOUT_SECONDS = 30.0
# A leftover .rdp file is only ever this module's own, holds no secret, and is replaced by a fresh
# one on the next action - so sweeping on a generous age bound is enough to keep the temp directory
# from accumulating them, without racing an mstsc that is still starting up.
STALE_RDP_FILE_AGE_SECONDS = 3600.0
RDP_FILE_PREFIX = "aem-background-session-"
STATE_FILE_NAME = "background_session_state.json"

# Said the same way by every action that refuses on it, because the user's way out is the same one
# in each case and it is not obvious from the situation: two sessions are running a macro engine,
# and only the user can say which of them is the background session.
_AMBIGUOUS_MESSAGE = (
    "More than one Windows session is running a macro engine, so it is not clear which one is the "
    "background session. Sign out of the one you do not want from inside it, then try again."
)

# RDP Wrapper's own convention: a loopback address OTHER than 127.0.0.1/localhost, both of which
# Windows always routes to the console session (session 0/1) regardless of RDP Wrapper, failing
# with error 0x708 ("no session is available") rather than creating a second one.
TARGET_ADDRESS = "127.0.0.2"
DEFAULT_DESKTOP_WIDTH = 1920
DEFAULT_DESKTOP_HEIGHT = 1080
_SM_CXSCREEN = 0
_SM_CYSCREEN = 1


class SessionState(IntEnum):
    """WTS_CONNECTSTATE_CLASS, as returned by WTSEnumerateSessionsW."""

    ACTIVE = 0
    CONNECTED = 1
    CONNECT_QUERY = 2
    SHADOW = 3
    DISCONNECTED = 4
    IDLE = 5
    LISTEN = 6
    RESET = 7
    DOWN = 8
    INIT = 9


class SessionInfo(NamedTuple):
    session_id: int
    state: int


@dataclass(frozen=True)
class BackgroundSessionResult:
    ok: bool
    message: str
    session_id: int | None = None
    client_pid: int | None = None
    # Its ONLY purpose is to keep the launched client's process handle open so the operating
    # system cannot recycle client_pid while branding is still running.
    client_process: Any | None = None
    # The client window this action ended up acting on, so a caller that has to act on it again
    # (Hide minimizes the window it just made sure exists) does not search for it a second time
    # and risk landing on a different one.
    client_window: int | None = None


@dataclass(frozen=True)
class _BackgroundSessionMarker:
    session_id: int
    address: str
    # The owner Windows itself reported for the session when it was created, NOT what the user
    # typed: only that pair can be re-compared exactly later, see _owner_is.
    domain: str
    username: str
    started_at: float


# ---------------------------------------------------------------------------------------------
# Windows Terminal Services bindings (session enumerate/disconnect/logoff)
# ---------------------------------------------------------------------------------------------


class _WTS_SESSION_INFO(ctypes.Structure):
    _fields_ = [
        ("SessionId", wintypes.DWORD),
        ("pWinStationName", wintypes.LPWSTR),
        ("State", ctypes.c_int),
    ]


# ((HANDLE)NULL): WTSEnumerateSessionsW/WTSDisconnectSession/WTSLogoffSession all treat this as
# "the local RD Session Host server", which is exactly what every call in this module wants.
_WTS_CURRENT_SERVER_HANDLE = None


def _wtsapi32() -> Any:
    """Return wtsapi32 with the four functions this module uses typed, or None if unavailable.

    Kept lazy and self-contained, mirroring engine_process._kernel32(): a missing symbol here must
    degrade this module's own features, never anything engine_process.py already relies on.
    """
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.wtsapi32
        library.WTSEnumerateSessionsW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_WTS_SESSION_INFO)),
            ctypes.POINTER(wintypes.DWORD),
        ]
        library.WTSEnumerateSessionsW.restype = wintypes.BOOL
        library.WTSFreeMemory.argtypes = [wintypes.LPVOID]
        library.WTSFreeMemory.restype = None
        library.WTSDisconnectSession.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL]
        library.WTSDisconnectSession.restype = wintypes.BOOL
        library.WTSLogoffSession.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL]
        library.WTSLogoffSession.restype = wintypes.BOOL
        library.WTSQuerySessionInformationW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(wintypes.DWORD),
        ]
        library.WTSQuerySessionInformationW.restype = wintypes.BOOL
        return library
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def _enumerate_sessions_raw() -> list[SessionInfo]:
    """The only function in this module that touches WTSEnumerateSessionsW directly.

    Isolated to a thin wrapper so every caller above it (list_sessions, find_session_by_id, the
    start/show/stop polling and interlock logic) is plain Python, testable by monkeypatching this
    one function instead of faking ctypes structures.
    """
    library = _wtsapi32()
    if library is None:
        return []
    session_pointer = ctypes.POINTER(_WTS_SESSION_INFO)()
    count = wintypes.DWORD()
    try:
        ok = library.WTSEnumerateSessionsW(
            _WTS_CURRENT_SERVER_HANDLE, 0, 1, ctypes.byref(session_pointer), ctypes.byref(count)
        )
    except (AttributeError, OSError, ValueError):
        return []
    if not ok:
        return []
    try:
        return [
            SessionInfo(int(session_pointer[index].SessionId), int(session_pointer[index].State))
            for index in range(count.value)
        ]
    finally:
        try:
            library.WTSFreeMemory(session_pointer)
        except (AttributeError, OSError, ValueError):
            pass


def list_sessions() -> list[SessionInfo]:
    """Return every Windows session on this machine, console and RDP alike."""
    return _enumerate_sessions_raw()


def find_session_by_id(session_id: int) -> SessionInfo | None:
    for session in list_sessions():
        if session.session_id == session_id:
            return session
    return None


# WTS_INFO_CLASS members this module queries.
_WTS_USER_NAME = 5
_WTS_DOMAIN_NAME = 7


def _query_session_string(session_id: int, info_class: int) -> str | None:
    library = _wtsapi32()
    if library is None:
        return None
    buffer = wintypes.LPWSTR()
    length = wintypes.DWORD()
    try:
        ok = library.WTSQuerySessionInformationW(
            _WTS_CURRENT_SERVER_HANDLE, session_id, info_class,
            ctypes.byref(buffer), ctypes.byref(length),
        )
    except (AttributeError, OSError, ValueError):
        return None
    if not ok:
        return None
    try:
        return buffer.value or ""
    finally:
        try:
            library.WTSFreeMemory(buffer)
        except (AttributeError, OSError, ValueError):
            pass


def session_owner(session_id: int) -> tuple[str, str] | None:
    """Return (domain, username) for a session, or None when either cannot be read.

    Both halves must be readable: a partially-known owner cannot be compared safely, and every
    caller of this uses it to decide whether it is allowed to disconnect or log a session off.
    """
    user = _query_session_string(session_id, _WTS_USER_NAME)
    domain = _query_session_string(session_id, _WTS_DOMAIN_NAME)
    if user is None or domain is None or not user:
        return None
    return (domain, user)


def split_account(username: str) -> tuple[str | None, str]:
    """Split what the user typed into (domain or None, account).

    Accepts the three spellings a Windows account is normally written in: bare ("trainer"),
    down-level ("CORP\\trainer", also tolerating a forward slash) and UPN ("trainer@corp.example").
    A bare name yields no domain, which is the common case here (a local account signing in to its
    own machine) and the reason the domain has to be optional at all.
    """
    normalized = username.replace("/", "\\").strip()
    if "\\" in normalized:
        domain, _, account = normalized.rpartition("\\")
        return (domain or None, account)
    if "@" in normalized:
        account, _, domain = normalized.partition("@")
        return (domain or None, account)
    return (None, normalized)


def _owner_matches(session_id: int, username: str) -> bool:
    """Whether `session_id` is signed in as `username`, failing closed when it cannot be told.

    Used only to CLAIM a freshly created session, where all this can compare against is what the
    user typed. A typed domain is compared when present; a bare name necessarily is not, because
    Windows reports the domain half back in a spelling the user never supplied (the machine name
    for a local account). Once claimed, the observed owner is stored in the marker and every later
    check compares that full pair exactly, see ``_owner_is``.
    """
    owner = session_owner(session_id)
    if owner is None:
        return False
    typed_domain, account = split_account(username)
    if not account or owner[1].casefold() != account.casefold():
        return False
    return typed_domain is None or owner[0].casefold() == typed_domain.casefold()


def _owner_is(session_id: int, domain: str, username: str) -> bool:
    """Whether `session_id` is signed in as exactly this domain and account.

    The strict counterpart to ``_owner_matches``: both halves are compared against the owner
    observed when this app created the session, so a reused session id belonging to the same
    account name in a DIFFERENT domain cannot pass as ours.
    """
    owner = session_owner(session_id)
    if owner is None:
        return False
    return owner[0].casefold() == domain.casefold() and owner[1].casefold() == username.casefold()


def disconnect_session(session_id: int) -> bool:
    """Disconnect a session's client without logging it off: it keeps running server-side."""
    library = _wtsapi32()
    if library is None:
        return False
    try:
        return bool(library.WTSDisconnectSession(_WTS_CURRENT_SERVER_HANDLE, session_id, False))
    except (AttributeError, OSError, ValueError):
        return False


def logoff_session(session_id: int) -> bool:
    """End a session outright, the way signing out of Windows does."""
    library = _wtsapi32()
    if library is None:
        return False
    try:
        return bool(library.WTSLogoffSession(_WTS_CURRENT_SERVER_HANDLE, session_id, False))
    except (AttributeError, OSError, ValueError):
        return False


# ---------------------------------------------------------------------------------------------
# Credential Manager (CredReadW, read only) - security relevant, implemented directly
#
# Read only on purpose, and the whole structure below exists for that one read: whether mstsc will
# find a sign-in for this address, or will have to ask the user for it. Nothing here writes or
# deletes a credential, and no password ever enters this process.
# ---------------------------------------------------------------------------------------------


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_CRED_TYPE_GENERIC = 1


def _advapi32() -> Any:
    """Return advapi32 with the two credential functions typed, or None when unavailable."""
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.advapi32
        library.CredReadW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
        ]
        library.CredReadW.restype = wintypes.BOOL
        library.CredFree.argtypes = [ctypes.c_void_p]
        library.CredFree.restype = None
        return library
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def credential_target(address: str) -> str:
    """The generic-credential target name mstsc looks up automatically for a given RDP address."""
    return f"TERMSRV/{address}"


def credential_exists(address: str) -> bool:
    """Whether Windows already holds the sign-in mstsc will use for `address`.

    Never a gate on starting a session, only something to tell the user: without one, mstsc asks for
    the password in its own window and stores it there when "Remember me" is ticked. Any failure to
    read reports False, which at worst produces a note about a prompt that then does not appear.
    """
    library = _advapi32()
    if library is None:
        return False
    credential = ctypes.POINTER(_CREDENTIALW)()
    try:
        ok = library.CredReadW(
            credential_target(address), _CRED_TYPE_GENERIC, 0, ctypes.byref(credential)
        )
    except (AttributeError, OSError, ValueError):
        return False
    if not ok:
        return False
    try:
        return True
    finally:
        try:
            library.CredFree(credential)
        except (AttributeError, OSError, ValueError):
            pass


# ---------------------------------------------------------------------------------------------
# .rdp file generation and mstsc launching
# ---------------------------------------------------------------------------------------------


def _user32() -> Any:
    """Return user32 with the window functions this module uses typed, or None when unavailable."""
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.user32
        library.GetSystemMetrics.argtypes = [ctypes.c_int]
        library.GetSystemMetrics.restype = ctypes.c_int
        library.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        library.ShowWindow.restype = wintypes.BOOL
        library.IsIconic.argtypes = [wintypes.HWND]
        library.IsIconic.restype = wintypes.BOOL
        library.SetForegroundWindow.argtypes = [wintypes.HWND]
        library.SetForegroundWindow.restype = wintypes.BOOL
        library.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        library.GetWindowTextLengthW.restype = ctypes.c_int
        library.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        library.GetWindowTextW.restype = ctypes.c_int
        return library
    except (AttributeError, ImportError, OSError, TypeError, ValueError):
        return None


def primary_display_size() -> tuple[int, int]:
    """Return the primary display dimensions, with a safe full-HD fallback."""
    library = _user32()
    if library is None:
        return (DEFAULT_DESKTOP_WIDTH, DEFAULT_DESKTOP_HEIGHT)
    try:
        width = int(library.GetSystemMetrics(_SM_CXSCREEN))
        height = int(library.GetSystemMetrics(_SM_CYSCREEN))
    except (AttributeError, OSError, TypeError, ValueError):
        return (DEFAULT_DESKTOP_WIDTH, DEFAULT_DESKTOP_HEIGHT)
    if width <= 0 or height <= 0:
        return (DEFAULT_DESKTOP_WIDTH, DEFAULT_DESKTOP_HEIGHT)
    return (width, height)


def _rdp_file_lines(
    address: str,
    username: str,
    *,
    alternate_shell: str | None = None,
    shell_working_directory: str | None = None,
    desktop_width: int | None = None,
    desktop_height: int | None = None,
) -> list[str]:
    """Settings for an unattended, minimal-footprint connection.

    "authentication level:i:0" and "prompt for credentials:i:0" matter specifically because this
    session's mstsc window can be hidden for a headless Start: any dialog it can no longer show (a
    certificate warning, a credentials prompt) would otherwise wait forever for input nobody can
    give it. A connected Start remains visible so the user can read such a failure.
    """
    if desktop_width is None or desktop_height is None:
        resolved_width, resolved_height = primary_display_size()
        if desktop_width is None:
            desktop_width = resolved_width
        if desktop_height is None:
            desktop_height = resolved_height
    lines = [
        f"full address:s:{address}",
        f"username:s:{username}",
        "screen mode id:i:1",
        f"desktopwidth:i:{desktop_width}",
        f"desktopheight:i:{desktop_height}",
        # Smart sizing scales the fixed session picture into the chosen mstsc window. Dynamic
        # resolution must explicitly stay off: its current Windows default overrides smart sizing,
        # and it changes the session's real resolution as the window is dragged. The resolution is
        # decided once at connection time and then stays put. This is not only about window size:
        # every macro coordinate is a percentage of an opening rectangle configured in absolute
        # pixels on the physical desktop. A 1024x768 session cannot contain an opening measured on
        # a 1920x1080 desktop, so matching the desktop is what makes stored coordinates mean the
        # same thing in both places.
        "smart sizing:i:1",
        "dynamic resolution:i:0",
        "session bpp:i:16",
        "compression:i:1",
        "keyboardhook:i:0",
        "audiomode:i:2",
        "redirectprinters:i:0",
        "redirectcomports:i:0",
        "redirectsmartcards:i:0",
        "redirectclipboard:i:0",
        "redirectposdevices:i:0",
        "autoreconnection enabled:i:1",
        "authentication level:i:0",
        "prompt for credentials:i:0",
        "enablecredsspsupport:i:1",
        "disable wallpaper:i:1",
        "disable full window drag:i:1",
        "disable menu anims:i:1",
        "administrative session:i:0",
        "connect to console:i:0",
    ]
    if alternate_shell is not None:
        lines.append(f"alternate shell:s:{alternate_shell}")
    if shell_working_directory is not None:
        lines.append(f"shell working directory:s:{shell_working_directory}")
    return lines


def write_rdp_file(
    path: Path,
    address: str,
    username: str,
    *,
    alternate_shell: str | None = None,
    shell_working_directory: str | None = None,
    desktop_width: int | None = None,
    desktop_height: int | None = None,
) -> None:
    content = "\r\n".join(
        _rdp_file_lines(
            address, username,
            alternate_shell=alternate_shell,
            shell_working_directory=shell_working_directory,
            desktop_width=desktop_width,
            desktop_height=desktop_height,
        )
    )
    path.write_text(content + "\r\n", encoding="utf-8")


def _sweep_stale_rdp_files() -> None:
    """Remove this module's own leftover .rdp files from an earlier run.

    Show's file cannot be deleted right after launching mstsc (that window is meant to stay open,
    and mstsc has not necessarily finished reading the file when Popen returns), so this bounded
    sweep is what keeps those from accumulating. The files hold an address and a username, never a
    secret, so an hour-old one lying around costs nothing beyond the clutter this removes.
    """
    try:
        candidates = list(Path(tempfile.gettempdir()).glob(f"{RDP_FILE_PREFIX}*.rdp"))
    except OSError:
        return
    cutoff = time.time() - STALE_RDP_FILE_AGE_SECONDS
    for candidate in candidates:
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
        except OSError:
            continue


def _new_temp_rdp_path() -> Path:
    _sweep_stale_rdp_files()
    return Path(tempfile.gettempdir()) / f"{RDP_FILE_PREFIX}{uuid.uuid4().hex}.rdp"


def _delete_rdp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _launch_mstsc(rdp_path: Path, *, hidden: bool) -> subprocess.Popen[Any] | None:
    startupinfo = None
    if hidden and sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    try:
        return subprocess.Popen(
            ["mstsc.exe", str(rdp_path)], creationflags=CREATE_NO_WINDOW, startupinfo=startupinfo
        )
    except OSError:
        return None


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=3.0)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        process.kill()
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------
# Persisted "which session did we start" marker
# ---------------------------------------------------------------------------------------------


def _state_path(data_directory: Path) -> Path:
    return data_directory / STATE_FILE_NAME


def _read_state(data_directory: Path) -> _BackgroundSessionMarker | None:
    try:
        raw = json.loads(_state_path(data_directory).read_text(encoding="utf-8"))
        return _BackgroundSessionMarker(
            session_id=int(raw["session_id"]),
            address=str(raw["address"]),
            domain=str(raw["domain"]),
            username=str(raw["username"]),
            started_at=float(raw["started_at"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_state(data_directory: Path, marker: _BackgroundSessionMarker) -> None:
    path = _state_path(data_directory)
    staging = path.with_name(path.name + ".tmp")
    payload = {
        "session_id": marker.session_id,
        "address": marker.address,
        "domain": marker.domain,
        "username": marker.username,
        "started_at": marker.started_at,
    }
    staging.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(staging, path)


def _clear_state(data_directory: Path) -> None:
    try:
        _state_path(data_directory).unlink(missing_ok=True)
    except OSError:
        pass


def _resolve_marker(data_directory: Path) -> tuple[_BackgroundSessionMarker | None, str]:
    """Resolve the recorded background session into one of "none", "ok" or "unverified".

    A Windows session id is reusable, so the recorded id alone is not proof that the session it
    once named is still the same one. Every destructive action (disconnect, logoff) therefore
    re-checks that the session is still signed in as the account this app started it with, and
    refuses when that cannot be confirmed - logging off somebody else's session is the one failure
    mode worth being strict about.

    "none" also clears the marker: a session id that no longer exists at all is unambiguously
    stale (logged off elsewhere, or the machine restarted), and leaving the marker behind would pin
    Start into refusing forever over a session that is gone. An existing-but-unverifiable session
    is NOT cleared, because it may well still be the real one.
    """
    marker = _read_state(data_directory)
    if marker is None:
        return (None, "none")
    if find_session_by_id(marker.session_id) is None:
        _clear_state(data_directory)
        return (None, "none")
    if not _owner_is(marker.session_id, marker.domain, marker.username):
        return (marker, "unverified")
    return (marker, "ok")


def _adopt_session(
    data_directory: Path, username: str | None
) -> tuple[_BackgroundSessionMarker | None, str]:
    """Find the live background session when the marker cannot name it, on evidence alone.

    The marker is written once and never updated, so anything that renumbers or replaces the
    session behind it strands a background session that is plainly running: a reboot (session ids
    are handed out afresh), a session started by hand, a marker lost with the data directory. Every
    action in this module then reports "not running" at a machine where Roblox and the engine are
    visibly working in another session, and the user has no way back to it from the GUI.

    Adoption is deliberately evidence-based rather than a guess at "probably that one", because
    what it resolves feeds Stop, which SIGNS A SESSION OUT. A candidate must clear all of:

    - not this session, and not session 0 (services): never act on ourselves or on the service host;
    - owned by exactly the same (domain, account) pair as the session this process is running in.
      Not "the name the user typed": a bare "trainer" carries no domain and would let DOMAIN-A's
      trainer adopt DOMAIN-B's, and an empty field would drop the comparison altogether, so merely
      opening the tab could claim another user's macro session and a later Stop would log them out.
      The background session is the same account here by construction (see the module docstring),
      so comparing against our own identity is both the strictest rule and the correct one. A typed
      username is checked against that identity as well, so a session started as a DIFFERENT
      account is never adopted; it is still reachable through its own marker, which Start wrote;
    - running an engine process, per find_engine_processes(), which reports session ids already.
      This is the one signal an unrelated session cannot produce by accident.

    Every step fails CLOSED. An unreadable owner on either side, and an unknown own session id, all
    end in "none": not knowing which session this process is in makes "not this one" unprovable,
    and adopting our own session would let Stop sign the user out of the desktop they are sitting at.

    Exactly one candidate is adopted. Several is reported as "ambiguous" rather than resolved: with
    two engines running in two sessions, picking one would mean disconnecting or logging off a
    session on a guess. None leaves "none", the honest answer that there is nothing to act on.

    An adoption WRITES the marker, storing the owner as Windows just reported it, so the recorded
    state stays the single description of the background session for everything downstream.
    """
    engine_sessions = {
        process.session_id
        for process in find_engine_processes()
        if process.session_id is not None and process.session_id != 0
    }
    own_session = current_session_id()
    if own_session is None:
        return (None, "none")
    engine_sessions.discard(own_session)
    if not engine_sessions:
        # Nothing can be adopted without an engine to adopt it by, so stop before enumerating
        # sessions or reading owners. This is the common case (no background session at all), and
        # it keeps the whole resolver free of Windows session calls when there is nothing to find.
        return (None, "none")
    expected_owner = session_owner(own_session)
    if expected_owner is None:
        return (None, "none")
    if username is not None:
        typed_domain, account = split_account(username)
        if not account or account.casefold() != expected_owner[1].casefold():
            return (None, "none")
        if typed_domain is not None and typed_domain.casefold() != expected_owner[0].casefold():
            return (None, "none")
    live = {session.session_id for session in list_sessions()}
    candidates: list[tuple[int, tuple[str, str]]] = []
    for session_id in sorted(engine_sessions & live):
        # Read ONCE and compare that value. Reading the owner again to compare it would mean two
        # reads of a session id Windows is free to recycle in between, so the pair that gets stored
        # could come from a different moment than the pair that was matched on.
        owner = session_owner(session_id)
        if owner is None:
            continue
        if owner[0].casefold() != expected_owner[0].casefold():
            continue
        if owner[1].casefold() != expected_owner[1].casefold():
            continue
        candidates.append((session_id, owner))
    if not candidates:
        return (None, "none")
    if len(candidates) > 1:
        return (None, "ambiguous")
    session_id, owner = candidates[0]
    marker = _BackgroundSessionMarker(session_id, TARGET_ADDRESS, owner[0], owner[1], time.time())
    _write_state(data_directory, marker)
    return (marker, "adopted")


def resolve_background_session(
    data_directory: Path, username: str | None = None
) -> tuple[_BackgroundSessionMarker | None, str]:
    """Return the background session to act on: the recorded one, or a live one adopted on evidence.

    The single entry point for Show, Disconnect, Stop and the status label, so all four agree on
    what "the background session" is. The marker still wins whenever it resolves at all, including
    "unverified": adoption exists to answer the case where the marker names nothing, not to
    second-guess one that does.
    """
    marker, status = _resolve_marker(data_directory)
    if status != "none":
        # A session this process is running in is never the background session, whatever a recorded
        # marker says. Windows reuses session ids, so a marker written before a reboot can end up
        # naming the console session the user is sitting at, and _owner_is would confirm it happily:
        # same account, same domain. Acting on that would disconnect or sign out the desktop the app
        # is running on. Adoption already refuses this by construction; the marker path needs the
        # check spelled out. An unknown own session id cannot rule anything out, so it changes
        # nothing here rather than blocking a session that is probably fine.
        own_session = current_session_id()
        if marker is not None and own_session is not None and marker.session_id == own_session:
            return (None, "none")
        return (marker, status)
    return _adopt_session(data_directory, username)


def is_background_session_active(data_directory: Path, username: str | None = None) -> bool:
    """Whether a background session this app started is still alive.

    An unverifiable or ambiguous session counts as active on purpose: the point of this check is to
    stop Start from creating a second session, and "there is something there that might be ours" is
    reason enough not to. Adoption matters here for the same reason it matters to Show: without it,
    Start after a reboot would see "not running" and create a SECOND session against the engine
    still running in the first one, which is exactly the interlock this check exists to enforce.
    """
    return resolve_background_session(data_directory, username)[1] in {
        "ok",
        "unverified",
        "adopted",
        "ambiguous",
    }


def _wait_until_not_active(
    session_id: int,
    *,
    timeout_seconds: float,
    pump: Callable[[], object] | None,
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> bool:
    """Whether the session left the ACTIVE state within the budget.

    WTSDisconnectSession returning true only means the request was accepted, so every caller that
    disconnects has to confirm the session really let go before reporting success or launching a
    client at it. One helper rather than a copy per caller: the three that existed had already
    started to drift in what they did on timeout.
    """
    deadline = now() + timeout_seconds
    while True:
        session = find_session_by_id(session_id)
        if session is None or session.state != SessionState.ACTIVE:
            return True
        if now() >= deadline:
            return False
        if pump is not None:
            pump()
        sleep(0.5)


# ---------------------------------------------------------------------------------------------
# Start / Show / Stop
# ---------------------------------------------------------------------------------------------


def start_background_session(
    data_directory: Path,
    address: str,
    username: str,
    *,
    alternate_shell: str | None = None,
    shell_working_directory: str | None = None,
    disconnect_after_start: bool = False,
    session_wait_timeout_seconds: float = DEFAULT_SESSION_WAIT_TIMEOUT_SECONDS,
    before_launch: Callable[[], object] | None = None,
    pump: Callable[[], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> BackgroundSessionResult:
    """Create the background session and wait for it to log on.

    ``before_launch`` runs once, immediately before mstsc is started and after every refusal above
    it has already been passed. That exact position is the point of it: the autostart route arms a
    one-shot marker there (see session_autostart.py), and arming any earlier would leave the marker
    live across a refusal that never produced a session at all.

    Interlock, direction 1 of 2: refuses to start while an engine already runs in THIS (console)
    session, since that engine and whatever the background session goes on to run would drive the
    same config.ini and local bridge files. Direction 2 (refusing to start a SECOND engine while a
    background session is active) needs no separate check here: main.py's own startup already
    looks for an engine in ANY session before spawning one (find_engine_processes() is session-
    agnostic by design, see engine_process.py), so it already attaches to a background session's
    engine instead of racing it. Duplicating that check here would just be redundant.
    """
    if is_background_session_active(data_directory, username):
        return BackgroundSessionResult(
            False, "A background session is already running. Use Show or Stop first."
        )

    # Deliberately no credential check. mstsc asks for the sign-in in its own window when Windows
    # holds none, and stores it there on "Remember me", which is the only way one is ever created:
    # this app does not write credentials. Refusing here would strand a first-time user, because Show
    # (the other route to that prompt) can only reconnect to a session that is already running. The
    # caller is expected to SAY that a prompt is coming, see background_session_tab._credential_note.
    # A caller passing disconnect_after_start hides the client, and a prompt in a hidden window
    # cannot be answered: such a Start simply runs out its wait and reports the timeout.
    engines = find_engine_processes()
    if engines:
        own_session = current_session_id()
        # Fails CLOSED: an engine whose session cannot be read, or a GUI that cannot read its own,
        # is treated exactly like a confirmed local engine. Starting a background session in either
        # case risks a second engine driving the same config.ini and bridge files, and the cost of
        # being wrong the other way is only that the user stops an engine before continuing.
        if own_session is None or any(
            process.session_id is None or process.session_id == own_session for process in engines
        ):
            return BackgroundSessionResult(
                False,
                "The macro engine is running on this desktop right now. Stop it first: starting a "
                "background session while it runs would leave two engines sharing one config.",
            )

    rdp_path = _new_temp_rdp_path()
    try:
        write_rdp_file(
            rdp_path, address, username,
            alternate_shell=alternate_shell, shell_working_directory=shell_working_directory,
        )
    except OSError:
        # A failed write can still have left a partial file behind, so clean up before returning.
        _delete_rdp_file(rdp_path)
        return BackgroundSessionResult(False, "Could not write the Remote Desktop connection file.")

    sessions_before = {session.session_id for session in list_sessions()}
    if before_launch is not None:
        # Best-effort by design. Whatever this arms is an optimisation of how the new session comes
        # up; failing it must not cost the user the session itself, which is still perfectly usable
        # with a normal desktop.
        try:
            before_launch()
        except Exception:
            pass
    # A retained client that cannot be seen is strictly worse than a disconnected session: it
    # holds the session and shows nothing. Hide mstsc only when this Start will disconnect it.
    #
    # And only when Windows already holds the sign-in for this address. Without one the client opens
    # a credentials prompt, which nobody can answer in a hidden window: the wait would simply run out
    # and report a timeout that says nothing about the real reason. So a first Start is visible even
    # when the caller asked for a headless one. The read is deliberately behind the short-circuit, so
    # the ordinary visible Start never consults the credential store at all.
    hidden = disconnect_after_start and credential_exists(address)
    process = _launch_mstsc(rdp_path, hidden=hidden)
    if process is None:
        _delete_rdp_file(rdp_path)
        return BackgroundSessionResult(False, "Could not launch the Remote Desktop client (mstsc.exe).")

    deadline = now() + session_wait_timeout_seconds
    new_session_id: int | None = None
    claimed_owner: tuple[str, str] | None = None
    try:
        while True:
            for session in list_sessions():
                # New, active AND signed in as the account this connection was made with. Without
                # that last check, a colleague signing in over RDP, or a fast-user-switch on the
                # console, at exactly this moment would be claimed as "our" session and then
                # disconnected (and later logged off) on its owner's behalf.
                if (
                    session.session_id not in sessions_before
                    and session.state == SessionState.ACTIVE
                    and _owner_matches(session.session_id, username)
                ):
                    new_session_id = session.session_id
                    # Read the owner HERE, in the same moment the session is claimed, rather than
                    # after the disconnect below: a session id freed and reused in between would
                    # otherwise put a different user's account into the marker, and Stop would then
                    # happily log THAT user off, since the pair it re-checks would match.
                    claimed_owner = session_owner(session.session_id)
                    break
            if new_session_id is not None or now() >= deadline:
                break
            if pump is not None:
                pump()
            sleep(0.5)
    finally:
        _delete_rdp_file(rdp_path)

    if new_session_id is None:
        # The owner is read ONCE per candidate and that same value is both matched on and stored.
        # Matching with _owner_matches and then re-reading with session_owner would mean two reads:
        # a transient failure on the second one would store an empty domain, which _owner_is can
        # never match, so Stop would refuse the very session this branch exists to keep stoppable.
        timed_out_candidates = []
        for session in list_sessions():
            if session.session_id in sessions_before:
                continue
            owner = session_owner(session.session_id)
            if owner is None:
                continue
            typed_domain, account = split_account(username)
            if not account or owner[1].casefold() != account.casefold():
                continue
            if typed_domain is not None and owner[0].casefold() != typed_domain.casefold():
                continue
            timed_out_candidates.append((session, owner))
        if len(timed_out_candidates) == 1:
            timed_out_session, observed_owner = timed_out_candidates[0]
            # A marker is the only handle this app has on a session. If a session did come up,
            # recording it before the best-effort disconnect keeps it stoppable; failing to write
            # one would strand it forever after this timeout.
            _write_state(
                data_directory,
                _BackgroundSessionMarker(
                    timed_out_session.session_id,
                    address,
                    observed_owner[0],
                    observed_owner[1],
                    time.time(),
                ),
            )
            disconnect_session(timed_out_session.session_id)
            _terminate_process(process)
            return BackgroundSessionResult(
                False,
                "The background session did come up but could not be confirmed in time. It is now "
                "tracked, and Stop will end it.",
                timed_out_session.session_id,
            )
        # Adopting the wrong session is worse than leaving the candidates alone.
        _terminate_process(process)
        return BackgroundSessionResult(
            False,
            "Timed out waiting for the background session to become active. Confirm RDP Wrapper "
            "is installed and working (see the setup wizard) and that the saved credential is "
            "still correct.",
        )

    # The owner Windows reported at claim time, not the string the user typed: a bare "trainer"
    # carries no domain, and only a full pair can be compared exactly when Stop re-checks ownership
    # later. The fallback keeps the marker writable if that query failed; it simply leaves the
    # session "unverified", which Stop already refuses to act on.
    observed_owner = claimed_owner or ("", split_account(username)[1])
    _write_state(
        data_directory,
        _BackgroundSessionMarker(
            new_session_id, address, observed_owner[0], observed_owner[1], time.time()
        ),
    )
    if not disconnect_after_start:
        # A disconnected RDP session has no rendered desktop, so screen capture and OCR can return
        # nothing. This macro's entire perception layer is screen based, making a connected session
        # the safer default even when nobody needs to watch its startup.
        return BackgroundSessionResult(
            True, "Background session started and remains connected.", new_session_id
        )

    disconnected = disconnect_session(new_session_id)
    if disconnected:
        # A failure here would otherwise be reported as "started and disconnected" while an mstsc
        # window is still holding the session.
        disconnected = _wait_until_not_active(
            new_session_id,
            timeout_seconds=DISCONNECT_CONFIRM_TIMEOUT_SECONDS,
            pump=pump,
            sleep=sleep,
            now=now,
        )

    _terminate_process(process)
    if not disconnected:
        return BackgroundSessionResult(
            False,
            "The background session started but could not be disconnected, so it is still holding "
            "the screen. Use Show to look at it, or Stop to end it.",
            new_session_id,
        )
    return BackgroundSessionResult(True, "Background session started and disconnected.", new_session_id)


def show_background_session(
    data_directory: Path,
    username: str,
    *,
    pump: Callable[[], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> BackgroundSessionResult:
    """Reconnect to the already-running background session for a look.

    An active session first has its existing RDP client disconnected, then this client reconnects
    to the same session. An unverifiable session is still worth offering: only Stop refuses on
    "unverified" because it logs the session off.
    """
    marker, status = resolve_background_session(data_directory, username)
    if status == "ambiguous":
        return BackgroundSessionResult(False, _AMBIGUOUS_MESSAGE)
    if marker is None or status == "none":
        return BackgroundSessionResult(False, "No background session is currently running.")
    session = find_session_by_id(marker.session_id)
    if session is None:
        _clear_state(data_directory)
        return BackgroundSessionResult(False, "No background session is currently running.")
    if session.state == SessionState.ACTIVE:
        disconnected = disconnect_session(marker.session_id)
        if disconnected:
            # Confirm the session actually left ACTIVE before launching a new client.
            disconnected = _wait_until_not_active(
                marker.session_id,
                timeout_seconds=DISCONNECT_CONFIRM_TIMEOUT_SECONDS,
                pump=pump,
                sleep=sleep,
                now=now,
            )
        if not disconnected:
            # With fSingleSessionPerUser=0, launching before the recorded session leaves ACTIVE
            # can create a rival, untracked session instead of reconnecting to this one.
            return BackgroundSessionResult(
                False,
                "The background session could not be released. Try Show again.",
                marker.session_id,
            )

    rdp_path = _new_temp_rdp_path()
    try:
        write_rdp_file(rdp_path, marker.address, username)
    except OSError:
        _delete_rdp_file(rdp_path)
        return BackgroundSessionResult(False, "Could not write the Remote Desktop connection file.")
    # Deliberately not deleted right after launching, unlike the Start path: this window is meant
    # to stay open, and mstsc has not necessarily finished reading the file the instant Popen
    # returns. _sweep_stale_rdp_files() (called from _new_temp_rdp_path) collects it later instead.
    process = _launch_mstsc(rdp_path, hidden=False)
    if process is None:
        _delete_rdp_file(rdp_path)
        return BackgroundSessionResult(False, "Could not launch the Remote Desktop client (mstsc.exe).")
    return BackgroundSessionResult(
        True, "Reconnecting to the background session.", marker.session_id, process.pid, process
    )


# ---------------------------------------------------------------------------------------------
# Bringing the session's own client window to the front
#
# The engine draws its capture overlay on the desktop of the session it runs in, so a capture
# started from a GUI on the physical desktop needs that session's picture in front of the user
# before it can be answered. Everything below exists for that one flow; nothing here acts on the
# session itself beyond reusing Show.
# ---------------------------------------------------------------------------------------------


# The title window_branding puts on the client window this app opens, and therefore the strongest
# signal that a given Remote Desktop window is showing OUR background session rather than an
# unrelated connection the user happens to have open. One constant so the branding side and the
# matching side cannot drift apart.
CLIENT_WINDOW_TITLE = f"{APP_NAME} - Background Session"
CLIENT_EXE_NAME = "mstsc.exe"
_SW_RESTORE = 9
_SW_MINIMIZE = 6
# Long enough for a client to connect and paint on a slow first logon, short enough that a capture
# click does not look frozen when nothing is coming.
CLIENT_WINDOW_WAIT_SECONDS = 20.0


def _client_process_ids() -> list[int]:
    """Return the pids of every Remote Desktop client process on this machine.

    Session filtering is deliberately left out: EnumWindows only ever sees the calling session's
    own desktop, so a client belonging to a different session simply contributes no windows below.
    """
    try:
        completed = subprocess.run(
            ["tasklist.exe", "/FI", f"IMAGENAME eq {CLIENT_EXE_NAME}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=10.0,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    output = completed.stdout or ""
    # tasklist reports "no match" through a localized INFO line that never names the image, which
    # is what keeps this independent of the system language.
    if CLIENT_EXE_NAME.casefold() not in output.casefold():
        return []
    pids: list[int] = []
    for row in csv.reader(io.StringIO(output)):
        if len(row) < 2 or row[0].strip().casefold() != CLIENT_EXE_NAME.casefold():
            continue
        try:
            pids.append(int(row[1]))
        except ValueError:
            continue
    return pids


def _window_title(library: Any, hwnd: int) -> str:
    try:
        length = max(0, int(library.GetWindowTextLengthW(hwnd)))
        buffer = ctypes.create_unicode_buffer(length + 1)
        library.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value or ""
    except (AttributeError, OSError, TypeError, ValueError):
        return ""


def find_client_window(address: str) -> int | None:
    """Return the Remote Desktop window showing this app's background session, or None.

    Picked on evidence rather than on "the first client window found", because the user may well
    have other Remote Desktop connections open and pulling one of those to the front instead would
    send the capture click somewhere it means nothing. Two accepted signals, in order: the title
    this app brands its own client window with, and a title naming the loopback address the
    background session lives on (mstsc puts the address in its title while connecting and once
    connected, so this covers the unbranded client that Start leaves behind).

    Deliberately NO "if there is exactly one client window, use it" fallback. A single unrelated
    connection is exactly the case that would send a capture to somebody else's desktop and report
    success, and the caller has a safe answer for "not found": reconnect the session it can name.
    """
    library = _user32()
    if library is None:
        return None
    windows = [hwnd for pid in _client_process_ids() for hwnd in top_level_windows_for_process(pid)]
    if not windows:
        return None
    titled = [(hwnd, _window_title(library, hwnd)) for hwnd in windows]
    for hwnd, title in titled:
        if title == CLIENT_WINDOW_TITLE:
            return hwnd
    if address:
        for hwnd, title in titled:
            if address in title:
                return hwnd
    return None


def _first_window_for_pid(pid: int | None) -> int | None:
    """The first visible top-level window of a known client pid, or None."""
    if not pid:
        return None
    windows = top_level_windows_for_process(pid)
    return windows[0] if windows else None


def focus_client_window(hwnd: int) -> bool:
    """Restore a minimized client window and pull it to the front.

    Returns whether the window is now ACTIVATED, which is the only part a caller can go on to say
    "it is in front". A restore is still attempted and still worth doing when activation is refused
    (Windows refuses SetForegroundWindow while another process holds the foreground lock, flashing
    the taskbar button instead), but reporting that as success would be exactly the misleading
    answer this return value exists to avoid: the window would be un-minimized somewhere behind the
    rest of the desktop while the caller announced it was in front.
    """
    library = _user32()
    if library is None or not hwnd:
        return False
    try:
        if library.IsIconic(hwnd):
            library.ShowWindow(hwnd, _SW_RESTORE)
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    try:
        return bool(library.SetForegroundWindow(hwnd))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _focus_message(focused: bool) -> str:
    """What to say about an activation attempt Windows may legitimately have refused.

    A refused SetForegroundWindow is reported, not treated as a failure of the whole operation.
    Windows refuses it whenever another process holds the foreground lock and instead flashes the
    window's taskbar button, and the window has still been restored: the user can click it and
    complete the capture, which beats refusing a capture that would have worked. What must not
    happen is claiming the window is in front when nobody checked.
    """
    if focused:
        return "Its window is in front."
    return "Its window could not be pulled to the front; click it on the taskbar, then capture."


def ensure_background_session_visible(
    data_directory: Path,
    username: str | None = None,
    *,
    pump: Callable[[], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    window_wait_seconds: float = CLIENT_WINDOW_WAIT_SECONDS,
    force_reconnect: bool = False,
) -> BackgroundSessionResult:
    """Put the background session's picture in front of the user, reconnecting it if needed.

    Three states, one outcome. A session whose client window is merely minimized or buried is
    restored and activated, which costs nothing and keeps the connection as it was. A session with
    no client window here (started disconnected, or connected from somewhere else) goes through the
    ordinary Show path, and then the window it opens is waited for. A session that cannot be
    resolved at all is a failure with the reason named, since the caller's next move is to tell the
    user why their capture cannot happen.

    ``force_reconnect`` skips the first of those: the existing window is dropped and a new client is
    connected anyway. Only one caller needs it, and it needs it for a reason focusing cannot serve.
    A Remote Desktop client reads the "keep rendering while minimized" setting when it CONNECTS, so
    after that setting has just been written, the window that is already there is still the old one
    and reusing it would mean minimizing a client that still pauses the session's screen.
    """
    marker, status = resolve_background_session(data_directory, username)
    if status == "ambiguous":
        return BackgroundSessionResult(False, _AMBIGUOUS_MESSAGE)
    if marker is None or status == "none":
        return BackgroundSessionResult(False, "No background session is currently running.")

    existing = None if force_reconnect else find_client_window(marker.address)
    if existing is not None:
        return BackgroundSessionResult(
            True,
            _focus_message(focus_client_window(existing)),
            marker.session_id,
            client_window=existing,
        )

    show = show_background_session(
        data_directory, username or split_account(marker.username)[1],
        pump=pump, sleep=sleep, now=now,
    )
    if not show.ok:
        return show

    deadline = now() + window_wait_seconds
    while True:
        # The pid of the client just launched is both cheaper and more precise than searching by
        # title: no process enumeration per poll, and no dependence on what mstsc happens to call
        # its window while it is still connecting.
        hwnd = _first_window_for_pid(show.client_pid) or find_client_window(marker.address)
        if hwnd is not None:
            return BackgroundSessionResult(
                True,
                f"Reconnected to the background session. {_focus_message(focus_client_window(hwnd))}",
                marker.session_id,
                show.client_pid,
                show.client_process,
                client_window=hwnd,
            )
        if now() >= deadline:
            return BackgroundSessionResult(
                False,
                "The background session was reconnected, but its window did not come up in time.",
                marker.session_id,
                show.client_pid,
                show.client_process,
            )
        if pump is not None:
            pump()
        sleep(0.5)


def minimize_client_window(hwnd: int) -> bool:
    """Minimize a client window, best effort."""
    library = _user32()
    if library is None or not hwnd:
        return False
    try:
        library.ShowWindow(hwnd, _SW_MINIMIZE)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    # ShowWindow's own return value reports the window's PREVIOUS visibility, not whether the
    # command was carried out, so it cannot be used as a success test. Ask the window instead.
    try:
        return bool(library.IsIconic(hwnd))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def hide_background_session_window(
    data_directory: Path,
    username: str | None = None,
    *,
    reconnect_first: bool = False,
    screen_keeps_running: bool,
    pump: Callable[[], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    window_wait_seconds: float = CLIENT_WINDOW_WAIT_SECONDS,
) -> BackgroundSessionResult:
    """Put the session's window out of the way, and say honestly what that costs.

    The supported way to free the physical desktop. Disconnect frees it too, but a disconnected
    session has no rendered desktop at all, so the macro's screen detection can go blind with it;
    a minimized client keeps the session drawing as long as the client-side "keep rendering while
    minimized" setting is in place, which is what makes minimizing worth offering as its own action
    rather than leaving it to the window's own minimize button.

    Neither flag is decided here, because neither can be read off a window. ``screen_keeps_running``
    is what the caller CONFIRMED about that setting, and it only picks the wording: a caller that
    hides with the setting deliberately off (the user asked for Windows' default back) gets a result
    that says detection stops, instead of one claiming a screen that keeps running.
    ``reconnect_first`` is the same setting's other half: a client reads it when it CONNECTS, so one
    that was already running when the setting was written is still behaving the old way, and
    minimizing it would pause the session exactly as before. The caller passes True when it has just
    written the setting, and the existing window is then replaced rather than reused.
    """
    if not reconnect_first:
        marker, status = resolve_background_session(data_directory, username)
        if status == "ambiguous":
            return BackgroundSessionResult(False, _AMBIGUOUS_MESSAGE)
        if marker is None or status == "none":
            return BackgroundSessionResult(False, "No background session is currently running.")
        existing = find_client_window(marker.address)
        if existing is not None:
            return _hide_result(
                minimize_client_window(existing), marker.session_id, existing,
                screen_keeps_running=screen_keeps_running,
            )
        # No window to minimize, so there is nothing in the way. Reconnecting one just to minimize
        # it again would be a strange thing to do to a session the user has already freed.
        return BackgroundSessionResult(
            True,
            "The background session has no window on this desktop, so there was nothing to hide.",
            marker.session_id,
        )

    visible = ensure_background_session_visible(
        data_directory, username,
        pump=pump, sleep=sleep, now=now, window_wait_seconds=window_wait_seconds,
        # The whole reason this branch exists: the window that is already there belongs to a client
        # that connected before the setting was written, so focusing it would put the old behavior
        # back in front of the user under a message promising the new one.
        force_reconnect=True,
    )
    if not visible.ok or visible.client_window is None:
        return visible
    return _hide_result(
        minimize_client_window(visible.client_window),
        visible.session_id,
        visible.client_window,
        client_pid=visible.client_pid,
        client_process=visible.client_process,
        screen_keeps_running=screen_keeps_running,
        prefix=(
            "The background session was reconnected so its window picks up the setting that keeps "
            "the screen running. "
        ),
    )


def _hide_result(
    minimized: bool,
    session_id: int | None,
    hwnd: int,
    *,
    screen_keeps_running: bool,
    client_pid: int | None = None,
    client_process: Any | None = None,
    prefix: str = "",
) -> BackgroundSessionResult:
    if not minimized:
        return BackgroundSessionResult(
            False,
            f"{prefix}The background session's window could not be minimized.",
            session_id, client_pid, client_process, client_window=hwnd,
        )
    outcome = (
        "its screen keeps running"
        if screen_keeps_running
        else "its screen is paused while minimized, so detection stops until you show it again"
    )
    return BackgroundSessionResult(
        True,
        f"{prefix}The background session's window is minimized and {outcome}.",
        session_id, client_pid, client_process, client_window=hwnd,
    )


def disconnect_background_session(
    data_directory: Path,
    username: str | None = None,
    *,
    pump: Callable[[], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> BackgroundSessionResult:
    """Drop the background session's RDP client without ending the session.

    The counterpart to Show, and the cheap half of Stop: the session keeps running with everything
    in it, only the client holding it on this desktop goes away. That is what frees this desktop of
    the session's decoded picture, which is the whole reason to have the button.

    Non-destructive, so it accepts an unverifiable session the way Show does; only Stop, which signs
    a session out, insists on a confirmed owner.

    Idempotent on purpose: a session that is already disconnected reports success rather than an
    error. "Disconnect the session" has been achieved either way, and reporting a failure for a
    state the user asked for reads as something having gone wrong.
    """
    marker, status = resolve_background_session(data_directory, username)
    if status == "ambiguous":
        return BackgroundSessionResult(False, _AMBIGUOUS_MESSAGE)
    if marker is None or status == "none":
        return BackgroundSessionResult(False, "No background session is currently running.")
    session = find_session_by_id(marker.session_id)
    if session is None:
        _clear_state(data_directory)
        return BackgroundSessionResult(False, "No background session is currently running.")
    if session.state == SessionState.DISCONNECTED:
        return BackgroundSessionResult(
            True,
            "The background session is already disconnected and keeps running.",
            marker.session_id,
        )
    # Deliberately only DISCONNECTED short-circuits, not "anything that is not ACTIVE". CONNECTED,
    # CONNECT_QUERY and SHADOW all still have a client attached to the session, so reporting them as
    # already disconnected would claim an end state that was never reached.
    if not disconnect_session(marker.session_id):
        return BackgroundSessionResult(
            False, "The background session could not be disconnected.", marker.session_id
        )
    if not _wait_until_not_active(
        marker.session_id,
        timeout_seconds=DISCONNECT_CONFIRM_TIMEOUT_SECONDS,
        pump=pump,
        sleep=sleep,
        now=now,
    ):
        return BackgroundSessionResult(
            False,
            "The background session did not let go of the screen in time, so it may still be "
            "connected. Try Disconnect again.",
            marker.session_id,
        )
    return BackgroundSessionResult(
        True,
        "Background session disconnected. It keeps running with everything in it.",
        marker.session_id,
    )


def stop_background_session(
    data_directory: Path,
    username: str | None = None,
    *,
    pump: Callable[[], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> BackgroundSessionResult:
    """End the background session outright (logs it off, unlike Start's disconnect)."""
    marker, status = resolve_background_session(data_directory, username)
    if status == "ambiguous":
        return BackgroundSessionResult(False, _AMBIGUOUS_MESSAGE)
    if marker is None or status == "none":
        return BackgroundSessionResult(False, "No background session is currently running.")
    if status not in ("ok", "adopted"):
        # Windows reuses session ids, so an id that is no longer signed in as the account this app
        # started it with is not this app's session to log off. Refusing leaves the marker in
        # place: Show still works, and the user can end that session from inside it.
        # "adopted" passes rather than being refused here: it was resolved from a running macro
        # engine in a session that is not this one and whose readable owner matched, which is
        # stronger evidence than the recorded id an "ok" marker rests on, not weaker.
        return BackgroundSessionResult(
            False,
            "The recorded background session is no longer signed in as the account it was started "
            "with, so it was left alone. Use Show to check what is running there.",
            marker.session_id,
        )

    if not logoff_session(marker.session_id):
        # The marker deliberately survives a failed logoff: the session is probably still alive,
        # and dropping the marker here would let Start create a SECOND background session (and so
        # a second engine against the same config) on the next click.
        return BackgroundSessionResult(
            False, "Could not stop the background session cleanly; it may still be running."
        )
    # WTSLogoffSession returning true only means the request was accepted. Confirm the session is
    # really gone before clearing the marker, or a live session would become orphaned: the app
    # could no longer see or stop it after reporting "No background session is currently running."
    confirm_deadline = now() + LOGOFF_CONFIRM_TIMEOUT_SECONDS
    while True:
        if find_session_by_id(marker.session_id) is None:
            _clear_state(data_directory)
            return BackgroundSessionResult(True, "Background session stopped.")
        if now() >= confirm_deadline:
            return BackgroundSessionResult(
                False,
                "The background session could not be confirmed stopped. Try Stop again.",
            )
        if pump is not None:
            pump()
        sleep(0.5)
