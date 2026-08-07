"""Start, show and stop the hidden background Windows (RDP) session.

A background session lets the macro run with the physical desktop left free: a second Windows
session, on the same machine and the same user account, reachable only through RDP Wrapper's
loopback trick (127.0.0.2, never 127.0.0.1/localhost - those map to the console session and RDP
fails with error 0x708 even when RDP Wrapper is installed and working). Starting one writes a
throwaway .rdp file, launches mstsc.exe with its window hidden, waits for the new session to become
active, then immediately disconnects it (WTSDisconnectSession) so it keeps running with no client
attached. "Show" reconnects for a look; "Stop" logs the session off outright.

Sign-in credentials go into Windows Credential Manager via the CredWriteW API (DPAPI-protected
under this user account), never into config.ini or any file this application writes itself: this is
the security-relevant half of the module and is implemented directly here rather than delegated,
per CLAUDE.md's Codex-delegation rule. Deliberately NOT cmdkey.exe, whose only way to accept a
password is `/pass:<password>` on its command line, where any same-user process and any endpoint
command-line logging can read it.

Interlock: two engines sharing one user profile would fight over the same config.ini and local
bridge files. The half of that risk this module owns is refusing to START a background session
while an engine is already running on THIS (console) session - see the comment in
start_background_session for why the reverse direction needs no separate check here.
"""

from __future__ import annotations

import ctypes
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


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DEFAULT_SESSION_WAIT_TIMEOUT_SECONDS = 45.0
DISCONNECT_CONFIRM_TIMEOUT_SECONDS = 10.0
# A leftover .rdp file is only ever this module's own, holds no secret, and is replaced by a fresh
# one on the next action - so sweeping on a generous age bound is enough to keep the temp directory
# from accumulating them, without racing an mstsc that is still starting up.
STALE_RDP_FILE_AGE_SECONDS = 3600.0
RDP_FILE_PREFIX = "aem-background-session-"
STATE_FILE_NAME = "background_session_state.json"

# RDP Wrapper's own convention: a loopback address OTHER than 127.0.0.1/localhost, both of which
# Windows always routes to the console session (session 0/1) regardless of RDP Wrapper, failing
# with error 0x708 ("no session is available") rather than creating a second one.
TARGET_ADDRESS = "127.0.0.2"


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
# Credential Manager (CredWriteW) - security relevant, implemented directly
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
_CRED_PERSIST_LOCAL_MACHINE = 2


def _advapi32() -> Any:
    """Return advapi32 with the three credential functions typed, or None when unavailable."""
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.advapi32
        library.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        library.CredWriteW.restype = wintypes.BOOL
        library.CredReadW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
        ]
        library.CredReadW.restype = wintypes.BOOL
        library.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        library.CredDeleteW.restype = wintypes.BOOL
        library.CredFree.argtypes = [ctypes.c_void_p]
        library.CredFree.restype = None
        return library
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def credential_target(address: str) -> str:
    """The generic-credential target name mstsc looks up automatically for a given RDP address."""
    return f"TERMSRV/{address}"


def store_credential(address: str, username: str, password: str) -> bool:
    """Save an RDP auto-logon credential into Windows Credential Manager (DPAPI-protected).

    The password reaches Windows only as an in-process buffer handed to CredWriteW: it is never a
    process argument, never written to a file, never logged, and never included in a returned
    message. That buffer is zeroed before this returns, so it does not sit in this process's heap
    any longer than the call itself. Once stored, mstsc connects to `address` without prompting,
    which is what lets Start and Show run unattended.
    """
    library = _advapi32()
    if library is None:
        return False
    blob = ctypes.create_string_buffer(password.encode("utf-16-le"))
    # create_string_buffer appends a NUL terminator that is not part of the password itself.
    blob_size = max(0, len(blob) - 1)
    try:
        credential = _CREDENTIALW(
            Flags=0,
            Type=_CRED_TYPE_GENERIC,
            TargetName=credential_target(address),
            Comment=None,
            CredentialBlobSize=blob_size,
            CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte)),
            Persist=_CRED_PERSIST_LOCAL_MACHINE,
            AttributeCount=0,
            Attributes=None,
            TargetAlias=None,
            UserName=username,
        )
        try:
            return bool(library.CredWriteW(ctypes.byref(credential), 0))
        except (AttributeError, OSError, ValueError):
            return False
    finally:
        ctypes.memset(blob, 0, len(blob))


def credential_exists(address: str) -> bool:
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


def delete_credential(address: str) -> bool:
    library = _advapi32()
    if library is None:
        return False
    try:
        return bool(library.CredDeleteW(credential_target(address), _CRED_TYPE_GENERIC, 0))
    except (AttributeError, OSError, ValueError):
        return False


# ---------------------------------------------------------------------------------------------
# .rdp file generation and mstsc launching
# ---------------------------------------------------------------------------------------------


def _rdp_file_lines(
    address: str,
    username: str,
    *,
    alternate_shell: str | None = None,
    shell_working_directory: str | None = None,
) -> list[str]:
    """Settings for an unattended, minimal-footprint connection.

    "authentication level:i:0" and "prompt for credentials:i:0" matter specifically because this
    session's mstsc window is launched hidden for Start: any dialog it can no longer show (a
    certificate warning, a credentials prompt) would otherwise wait forever for input nobody can
    give it.
    """
    lines = [
        f"full address:s:{address}",
        f"username:s:{username}",
        "screen mode id:i:1",
        "desktopwidth:i:1024",
        "desktopheight:i:768",
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
) -> None:
    content = "\r\n".join(
        _rdp_file_lines(
            address, username,
            alternate_shell=alternate_shell, shell_working_directory=shell_working_directory,
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


def is_background_session_active(data_directory: Path) -> bool:
    """Whether a background session this app started is still alive.

    An unverifiable session counts as active on purpose: the point of this check is to stop Start
    from creating a second session, and "there is something there that might be ours" is reason
    enough not to.
    """
    return _resolve_marker(data_directory)[1] in {"ok", "unverified"}


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
    session_wait_timeout_seconds: float = DEFAULT_SESSION_WAIT_TIMEOUT_SECONDS,
    pump: Callable[[], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> BackgroundSessionResult:
    """Create the background session, wait for it to log on, then disconnect it.

    Interlock, direction 1 of 2: refuses to start while an engine already runs in THIS (console)
    session, since that engine and whatever the background session goes on to run would drive the
    same config.ini and local bridge files. Direction 2 (refusing to start a SECOND engine while a
    background session is active) needs no separate check here: main.py's own startup already
    looks for an engine in ANY session before spawning one (find_engine_processes() is session-
    agnostic by design, see engine_process.py), so it already attaches to a background session's
    engine instead of racing it. Duplicating that check here would just be redundant.
    """
    if is_background_session_active(data_directory):
        return BackgroundSessionResult(
            False, "A background session is already running. Use Show or Stop first."
        )

    # Both checks below are side-effect-free refusals, but report a missing credential first. That
    # way the user is never told to stop a running macro for a Start that would fail anyway.
    if not credential_exists(address):
        return BackgroundSessionResult(
            False,
            "No saved sign-in credential for the background session. Enter the password and "
            "click Save Credential first.",
        )

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
    process = _launch_mstsc(rdp_path, hidden=True)
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
        _terminate_process(process)
        return BackgroundSessionResult(
            False,
            "Timed out waiting for the background session to become active. Confirm RDP Wrapper "
            "is installed and working (see the setup wizard) and that the saved credential is "
            "still correct.",
        )

    disconnected = disconnect_session(new_session_id)
    if disconnected:
        # WTSDisconnectSession returning true only means the request was accepted. Confirm the
        # session actually left the ACTIVE state before reporting success, or a failure here would
        # be reported as "started and disconnected" while an mstsc window is still holding it.
        confirm_deadline = now() + DISCONNECT_CONFIRM_TIMEOUT_SECONDS
        while True:
            session = find_session_by_id(new_session_id)
            if session is None or session.state != SessionState.ACTIVE:
                break
            if now() >= confirm_deadline:
                disconnected = False
                break
            if pump is not None:
                pump()
            sleep(0.5)

    _terminate_process(process)
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
    if not disconnected:
        return BackgroundSessionResult(
            False,
            "The background session started but could not be disconnected, so it is still holding "
            "the screen. Use Show to look at it, or Stop to end it.",
            new_session_id,
        )
    return BackgroundSessionResult(True, "Background session started and disconnected.", new_session_id)


def show_background_session(data_directory: Path, username: str) -> BackgroundSessionResult:
    """Reconnect to the already-running background session for a look.

    Reconnecting is not destructive, so an unverifiable session is still worth offering: the worst
    case is an mstsc window that asks for credentials. Only Stop refuses on "unverified".
    """
    marker, status = _resolve_marker(data_directory)
    if marker is None or status == "none":
        return BackgroundSessionResult(False, "No background session is currently running.")

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


def stop_background_session(data_directory: Path) -> BackgroundSessionResult:
    """End the background session outright (logs it off, unlike Start's disconnect)."""
    marker, status = _resolve_marker(data_directory)
    if marker is None or status == "none":
        return BackgroundSessionResult(False, "No background session is currently running.")
    if status != "ok":
        # Windows reuses session ids, so an id that is no longer signed in as the account this app
        # started it with is not this app's session to log off. Refusing leaves the marker in
        # place: Show still works, and the user can end that session from inside it.
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
    _clear_state(data_directory)
    return BackgroundSessionResult(True, "Background session stopped.")


def forget_credential(address: str) -> BackgroundSessionResult:
    ok = delete_credential(address)
    return BackgroundSessionResult(
        ok, "Saved credential removed." if ok else "Could not remove the saved credential."
    )
