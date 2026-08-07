"""Join a configured private server without leaving a browser window behind.

Opening a private server link with the shell "open" verb starts the default browser, which loads a
Roblox page whose only job is to hand off to the ``roblox://`` protocol handler. The browser then
sits in the session for the rest of the run, doing nothing.

This module removes it in the order that costs the user least:

1. Build the ``roblox://`` link ourselves and start THAT, so no browser is involved at all. Free and
   offline for a ``?privateServerLinkCode=`` link, because it already carries both halves the
   protocol needs (the place id sits in the path, the link code in the query).
2. For a ``/share?code=...&type=Server`` link, ask Roblox' own share-link endpoint what those two
   halves are. This is the only network request this application makes on the macro side, so it is
   strictly bounded: one pinned https URL, a short timeout, a capped response body, and any failure
   at all falls through to step 3 rather than being reported as a problem.
3. Open the original link in the browser, exactly like before, and close the browser again once
   Roblox is up. The process that gets closed is the one Windows started FOR THIS LINK, taken from
   ShellExecuteExW's own process handle, so a window the user opened themselves is never a
   candidate: when the shell hands the link to a browser that was already running, it starts no
   process at all, this module gets no handle, and nothing is closed.

Everything after the validation runs on a worker thread. Both callers start Roblox from a path that
must not block: the session shell has not built its control window yet, and the button press is on
the Qt GUI thread.
"""

from __future__ import annotations

import csv
import ctypes
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from typing import Callable, NamedTuple
from urllib.parse import parse_qs, urlparse

from app.private_server_link import validation_error


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Both images count as "Roblox came up". The launcher is what the protocol handler starts first and
# it hands off to the player, so seeing either one proves the handoff worked, which is the question
# both the fallback decision and the browser close are actually asking.
ROBLOX_IMAGES = ("RobloxPlayerBeta.exe", "RobloxPlayerLauncher.exe")

SHARE_LINK_RESOLVE_URL = "https://apis.roblox.com/sharelinks/v1/resolve-link"
SHARE_LINK_TIMEOUT_SECONDS = 8.0
# A resolve response is a few hundred bytes. The cap exists so a wrong or hostile answer cannot make
# this read grow without bound; it is not a tuning value.
SHARE_LINK_MAX_BYTES = 64 * 1024

PROCESS_QUERY_TIMEOUT_SECONDS = 20.0
# How long Roblox gets to appear. The deep link either works within seconds or is not supported by
# the installed client, so waiting longer only delays the fallback the user is waiting for. The
# browser path gets more, because it also pays for the browser's own cold start.
DEEP_LINK_WAIT_SECONDS = 20.0
BROWSER_WAIT_SECONDS = 60.0
PROCESS_POLL_SECONDS = 1.0

_PLACE_ID_PATTERN = re.compile(r"^[0-9]{1,19}$")
# Roblox link codes are hex-ish tokens. Deliberately strict: this value is interpolated into a URL
# that is handed to the shell, so anything outside this set is treated as "cannot build a deep link"
# rather than escaped and hoped for.
_LINK_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_GAMES_PATH_PATTERN = re.compile(r"^/games/([0-9]{1,19})(?:/|$)")


class PrivateServer(NamedTuple):
    """The two values the Roblox protocol handler needs to join a private server."""

    place_id: str
    link_code: str

    def deep_link(self) -> str:
        return (
            f"roblox://experiences/start?placeId={self.place_id}&linkCode={self.link_code}"
        )


def private_server_from_link(link: str) -> PrivateServer | None:
    """Read place id and link code straight out of a link, without any network access.

    Only the ``/games/<placeId>/...?privateServerLinkCode=<code>`` form carries both, which is why
    a ``/share`` link returns None here and has to be resolved instead.
    """
    if validation_error(link) is not None:
        return None
    try:
        parsed = urlparse(link.strip())
    except ValueError:
        return None
    path_match = _GAMES_PATH_PATTERN.match(parsed.path or "")
    if path_match is None:
        return None
    code = parse_qs(parsed.query).get("privateServerLinkCode", [""])[0]
    if not _LINK_CODE_PATTERN.match(code):
        return None
    return PrivateServer(path_match.group(1), code)


def share_link_code(link: str) -> str | None:
    """Return the share code of a ``/share?code=...&type=Server`` link, or None."""
    if validation_error(link) is not None:
        return None
    try:
        parsed = urlparse(link.strip())
    except ValueError:
        return None
    if (parsed.path or "") != "/share":
        return None
    query = parse_qs(parsed.query)
    if query.get("type", [""])[0] != "Server":
        return None
    code = query.get("code", [""])[0]
    return code if _LINK_CODE_PATTERN.match(code) else None


def resolve_share_link(code: str, *, opener: Callable[..., object] | None = None) -> PrivateServer | None:
    """Ask Roblox what place and link code a share code stands for, or None on any failure.

    Every failure mode is the same answer on purpose. The endpoint may require a signed-in session,
    may rate limit, may change shape, and may simply be unreachable from a machine that is offline;
    none of those is worth reporting to the user, because the caller has a working fallback that
    needs no network at all.
    """
    if not _LINK_CODE_PATTERN.match(code or ""):
        return None
    if opener is None:
        opener = urllib.request.urlopen
    body = json.dumps({"linkId": code, "linkType": "Server"}).encode("utf-8")
    request = urllib.request.Request(
        SHARE_LINK_RESOLVE_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with opener(request, timeout=SHARE_LINK_TIMEOUT_SECONDS) as response:  # type: ignore[operator]
            payload = json.loads(response.read(SHARE_LINK_MAX_BYTES).decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError):
        return None
    if not isinstance(payload, dict):
        return None
    invite = payload.get("privateServerInviteData")
    if not isinstance(invite, dict):
        return None
    place_id = invite.get("placeId")
    link_code = invite.get("linkCode")
    if isinstance(place_id, bool) or not isinstance(place_id, (int, str)):
        return None
    place_id = str(place_id)
    if not isinstance(link_code, str):
        return None
    if not _PLACE_ID_PATTERN.match(place_id) or not _LINK_CODE_PATTERN.match(link_code):
        return None
    return PrivateServer(place_id, link_code)


def deep_link_for(link: str, *, opener: Callable[..., object] | None = None) -> str | None:
    """Return the ``roblox://`` link for a private server link, resolving a share code if needed."""
    server = private_server_from_link(link)
    if server is not None:
        return server.deep_link()
    code = share_link_code(link)
    if code is None:
        return None
    resolved = resolve_share_link(code, opener=opener)
    return None if resolved is None else resolved.deep_link()


def _query_pids(image: str) -> set[int] | None:
    """Return the pids running ``image``, or None when tasklist.exe could not be asked.

    Same mechanism engine_process.py uses, and for the same reason: it needs no third-party module
    and no elevated rights. None and the empty set are kept apart because "could not look" must not
    be read as "nothing is running", which on the browser path is the difference between leaving a
    user's own window alone and closing it.
    """
    try:
        completed = subprocess.run(
            ["tasklist.exe", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=PROCESS_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if getattr(completed, "returncode", 0) != 0:
        return None
    output = completed.stdout or ""
    # tasklist.exe reports "no match" through a localized INFO line that never holds the image name,
    # which keeps this independent of the system language.
    if image.casefold() not in output.casefold():
        return set()
    pids: set[int] = set()
    for row in csv.reader(io.StringIO(output)):
        if len(row) < 2 or row[0].strip().casefold() != image.casefold():
            continue
        try:
            pids.add(int(row[1]))
        except ValueError:
            continue
    return pids


def roblox_pids() -> set[int]:
    """Every Roblox process id currently running, as far as tasklist.exe can tell."""
    pids: set[int] = set()
    for image in ROBLOX_IMAGES:
        found = _query_pids(image)
        if found:
            pids |= found
    return pids


def wait_for_new_roblox(
    before: set[int],
    timeout_seconds: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    """Poll until a Roblox process that is NOT in ``before`` exists, or the timeout passes.

    A NEW process, not merely "a Roblox process": the user may well have Roblox open already, and
    treating that as proof of a successful handoff would report every launch as an instant success.
    The browser fallback would then close the browser before it had done anything, and the private
    server would never be joined.
    """
    deadline = monotonic() + timeout_seconds
    while True:
        if roblox_pids() - before:
            return True
        if monotonic() >= deadline:
            return False
        sleep(PROCESS_POLL_SECONDS)


def _close_pid(pid: int) -> None:
    """Ask a process to close its windows. Deliberately not a forced kill.

    A browser that is asked politely writes its session out and comes back clean next time; one that
    is killed shows a "restore pages?" prompt. A browser that refuses to go is left alone: an extra
    window is a far smaller problem than data loss in one the user cared about.
    """
    try:
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T"],
            check=False,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=PROCESS_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


class _ShellExecuteInfoW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SEE_MASK_NOASYNC = 0x00000100
_SW_SHOWNORMAL = 1


class ShellLaunch(NamedTuple):
    """What one shell "open" produced: whether it ran, and what this launch may close afterwards.

    ``handle`` is kept OPEN for as long as ``pid`` is going to be used. An open process handle keeps
    the process object alive, and Windows only recycles a pid once the last handle to it is gone, so
    holding it is what stops a browser that exits during the wait from handing its number to an
    unrelated process that then gets closed in its place.
    """

    ok: bool
    pid: int | None
    handle: int | None


def _shell_execute_ex(target: str) -> tuple[bool, int]:
    """Run one shell "open" and return (it ran, the process handle or 0). The only Win32 part."""
    info = _ShellExecuteInfoW()
    info.cbSize = ctypes.sizeof(info)
    # NOASYNC: the call must not return before the shell has finished acting on it, or hProcess
    # could still be unset by the time it is read.
    info.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NOASYNC
    info.lpVerb = "open"
    info.lpFile = target
    info.nShow = _SW_SHOWNORMAL
    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfoW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        return (False, 0)
    return (True, int(info.hProcess or 0))


def _process_id(handle: int) -> int:
    kernel32 = ctypes.windll.kernel32
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD
    return int(kernel32.GetProcessId(wintypes.HANDLE(handle)))


def close_process_handle(handle: int | None) -> None:
    """Release a handle taken by start_and_own. After this the pid may be recycled."""
    if not handle:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(wintypes.HANDLE(handle))
    except (AttributeError, ImportError, OSError, ValueError):
        return


def start_and_own(
    target: str,
    *,
    execute: Callable[[str], tuple[bool, int]] | None = None,
    process_id: Callable[[int], int] | None = None,
) -> ShellLaunch:
    """Open ``target`` with the shell, and report which process it started for it.

    That process is what makes closing the browser safe later. ShellExecuteExW hands back a handle
    to the process it STARTED, so anything named here can only exist because of this call. When the
    shell instead routes the link into a browser that was already running, it starts nothing, there
    is no handle, and the answer is "nothing to close": the correct one, since that window may be
    the one the user was reading and nothing can tell it apart from the one showing the link.

    Whenever the handle route cannot be taken at all, it falls back to the plain shell open this
    module replaced, so the worst case is exactly the old behaviour (a browser window that stays
    open) and never a launch that did not happen. That fallback is reachable ONLY from a shell call
    that did not run: once one has, launching a second time would open the link twice.
    """
    if execute is None:
        if sys.platform != "win32":
            return ShellLaunch(_start_plain(target), None, None)
        execute = _shell_execute_ex
    if process_id is None:
        process_id = _process_id
    try:
        ran, handle = execute(target)
    except (AttributeError, ImportError, OSError, ValueError):
        return ShellLaunch(_start_plain(target), None, None)
    if not ran:
        return ShellLaunch(_start_plain(target), None, None)
    if not handle:
        return ShellLaunch(True, None, None)
    try:
        pid = process_id(handle)
    except (AttributeError, ImportError, OSError, ValueError):
        pid = 0
    if not pid:
        # Launched, but not owned. Releasing the handle here is safe precisely because nothing will
        # be closed: there is no pid to protect from being recycled.
        close_process_handle(handle)
        return ShellLaunch(True, None, None)
    return ShellLaunch(True, pid, handle)


def _start_plain(target: str) -> bool:
    """The shell "open" verb with no handle back: what this module did before, kept as a floor."""
    try:
        os.startfile(target)  # noqa: S606 - the shell open verb is exactly what launches Roblox
        return True
    except (AttributeError, OSError, ValueError):
        return False


def _start(target: str) -> bool:
    """Hand a target to the shell's open verb, which is what performs the protocol handoff.

    Used for the ``roblox://`` link, where nothing is ever closed afterwards, so the handle is
    released straight away rather than held for a pid nobody is going to use.
    """
    launch = start_and_own(target)
    close_process_handle(launch.handle)
    return launch.ok


def run_launch(target: str, *, log: Callable[[str], None]) -> bool:
    """Start Roblox for ``target``, preferring the browserless route. Blocks; see launch_game.

    Returns whether Roblox was seen running afterwards. The deep link is tried first and verified
    rather than trusted: an installed client that does not understand it would otherwise leave the
    session with nothing running and no browser either, which is worse than the browser this whole
    module exists to remove.
    """
    # Taken once, before anything is started, and used by both attempts: it is what makes "Roblox
    # came up" mean a new process rather than one the user already had open.
    before_roblox = roblox_pids()

    deep_link = deep_link_for(target)
    if deep_link is not None:
        log("Starting Roblox through the roblox:// protocol, so no browser is opened.")
        if _start(deep_link):
            if wait_for_new_roblox(before_roblox, DEEP_LINK_WAIT_SECONDS):
                log("Roblox started without a browser.")
                return True
            log("Roblox did not come up from the protocol link; falling back to the browser.")
        else:
            log("The protocol link could not be started; falling back to the browser.")
    else:
        log("The link could not be turned into a protocol link; opening it in the browser.")

    browser = start_and_own(target)
    try:
        if not browser.ok:
            log("The private server link could not be opened.")
            return False
        if not wait_for_new_roblox(before_roblox, BROWSER_WAIT_SECONDS):
            # The browser is deliberately left open here. Roblox never came up, so the page it is
            # showing is the only thing left that says why.
            log("Roblox did not come up, so the browser window was left open.")
            return False
        if browser.pid is None:
            log("The link went to a browser that was already running, so no window was closed.")
            return True
        _close_pid(browser.pid)
        log("Closed the browser this launch opened, now that Roblox is up.")
        return True
    finally:
        # Only now, and on every path: until this runs, the open handle is what guarantees the pid
        # above still means the process this launch started.
        close_process_handle(browser.handle)


def launch_game(
    target: str,
    *,
    log: Callable[[str], None] | None = None,
    spawn: Callable[..., object] = threading.Thread,
) -> bool:
    """Start a configured private server link. Returns whether a launch was started.

    Only the validation is synchronous. Everything else (a resolve request, waiting for Roblox, and
    closing a browser) happens on a daemon thread, because both callers reach this from a path that
    must not block: the session shell has not built its control window yet, and the button press
    runs on the Qt GUI thread.
    """
    target = target.strip()
    if not target:
        # Checked separately from the validator below, which treats an empty link as VALID because
        # there it means "no private server configured, keep today's behavior". Here that same
        # value would reach the shell as "" instead, so it has to be its own refusal.
        return False
    if validation_error(target) is not None:
        # config.ini can be hand-edited, so only a validated target may reach the shell.
        return False
    sink: Callable[[str], None] = log if log is not None else (lambda _message: None)
    worker = spawn(target=run_launch, args=(target,), kwargs={"log": sink}, daemon=True)
    start = getattr(worker, "start", None)
    if callable(start):
        start()
    return True
