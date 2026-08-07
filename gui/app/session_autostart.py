"""Boot the background session into the macro without administrator rights.

Windows' own mechanism for this, the .rdp "alternate shell", is validated against the RemoteApp
published-application allow list before it is ever launched. On a machine where that list is
enforced but empty (Windows' default) the lookup misses, the RPC that serves the initial program
fails, and NOTHING starts: not the requested program, and not Explorer either. See
``rdp_wrapper.initial_program_allow_list_disabled`` for the switch that turns that off, and the
"fixes/rdp-initial-program-does-nothing" task file for the disassembly that established it.

That switch needs administrator rights. This module is the route that does not: an ordinary HKCU
``Run`` value, which Windows starts after the shell at logon. Three properties make that work here,
and all three are load-bearing:

- A ``Run`` value is a COMMAND LINE, not a bare application name. It can therefore carry
  ``--session-autostart``, which is why this route needs none of the separate-executable trickery
  the alternate shell needs to express "start in session-shell mode".
- Both sessions share ONE Windows profile, so this entry also fires for the console logon on the
  physical desktop. Booting the user's real desktop into a macro shell would be a serious misfire,
  so the launched process gates itself on genuinely being in a background session and exits before
  a QApplication (and therefore any window) is ever constructed.
- An RDP logon the user performs for their own reasons is not a request to run the macro. A
  one-shot arm marker, written immediately before mstsc is launched and consumed on read, is what
  separates "this app asked for this session" from "somebody signed in over RDP".

The entry is installed on demand and removed again as soon as it has been claimed, so it exists
only during the short window in which a background session is actually being started. That also
means it can never go stale: every start rewrites it with the currently installed path.

KNOWN LIMITATION, stated because it cannot be closed rather than because it is acceptable in the
abstract. The marker authorises "the next background-session logon", not one specific session,
because the session does not exist yet at the moment it has to be armed: its id is assigned by
Windows during the logon the marker is what permits. So a REMOTE logon that somebody makes by hand
into this same account, inside the ARM_WINDOW_SECONDS after a Start, can consume the authorisation
meant for the session the app just asked for. Two things bound it. The console is not affected at
all (in_background_session refuses there, which is the case that would actually matter, since that
is the user's own physical desktop). And the consequence in the remote case is a misfire rather
than a breach: the macro starts in a session its owner is sitting in front of, with the control
window visible and closable. What is NOT a mitigation, and was considered and rejected: recording
the session ids that existed at arm time and requiring the claimant's own id to be absent from that
set. A hand-made logon in the window gets a brand new id too, so it would pass that test just as
the intended session does.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

from app.engine_process import current_session_id
from app.self_install import installed_gui_path


SESSION_AUTOSTART_FLAG = "--session-autostart"
# Under HKEY_CURRENT_USER. Deliberately the per-user Run key and not its HKLM twin: the whole point
# of this route is that it needs no administrator rights.
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
# Stable across releases. Renaming it would orphan an entry a previous version installed.
RUN_VALUE_NAME = "KimberliteMacroSession"
ARM_FILE_NAME = "session_autostart_arm.json"
# Roughly three times the worst logon this has to cover (the tab warns a first logon can take up to
# a minute, and the Run entry only fires after the shell has started), and no more. The window is
# the ONLY thing bounding the limitation described in the module docstring, so it buys nothing to
# make it generous: every second of it is a second in which a hand-made RDP logon could take the
# authorisation instead.
ARM_WINDOW_SECONDS = 180.0

# GetSystemMetrics(SM_REMOTESESSION): non-zero when the calling process runs in a remote session.
_SM_REMOTESESSION = 0x1000
# WTSGetActiveConsoleSessionId's documented failure value.
_INVALID_SESSION_ID = 0xFFFFFFFF


# ---------------------------------------------------------------------------------------------
# The HKCU Run entry
# ---------------------------------------------------------------------------------------------


def autostart_command(directory: Path | None = None) -> str:
    """Return the command line Windows should run at the background session's logon.

    Quoted because the installed path contains both spaces and an apostrophe, and because a Run
    value is parsed as a command line: an unquoted path would be split into an executable plus
    stray arguments.
    """
    return f'"{installed_gui_path(directory)}" {SESSION_AUTOSTART_FLAG}'


def autostart_available(directory: Path | None = None) -> bool:
    """Whether there is an installed executable for the Run entry to point at.

    A source checkout, and any launch that never self-installed, has none. Unlike the alternate
    shell an absent target here is harmless (Windows simply skips the entry), but offering an
    option that cannot do anything is worse than not offering it.
    """
    try:
        return installed_gui_path(directory).is_file()
    except (KeyError, OSError, ValueError):
        return False


def _winreg() -> object | None:
    """Return the winreg module, or None on a platform that has no registry."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        return winreg
    except ImportError:
        return None


def install_autostart_entry(directory: Path | None = None) -> bool:
    """Write the Run value, replacing whatever it held before.

    Overwriting rather than preserving is deliberate: the value is this application's own, and the
    installed path it points at can move between releases, so the current path always wins.
    """
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        command = autostart_command(directory)
    except (KeyError, OSError, ValueError):
        return False
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command)
        return True
    except (AttributeError, OSError, ValueError):
        return False


def read_autostart_entry() -> str | None:
    """Return the installed Run command line, or None when there is none."""
    winreg = _winreg()
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, value_type = winreg.QueryValueEx(key, RUN_VALUE_NAME)
    except (AttributeError, OSError, ValueError):
        return None
    if value_type != winreg.REG_SZ or not isinstance(value, str):
        return None
    return value


def remove_autostart_entry() -> bool:
    """Delete the Run value. An entry that is already absent counts as removed."""
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
        return True
    except FileNotFoundError:
        return True
    except (AttributeError, OSError, ValueError):
        return False


# ---------------------------------------------------------------------------------------------
# The one-shot arm marker
# ---------------------------------------------------------------------------------------------


def _arm_path(data_directory: Path) -> Path:
    return Path(data_directory) / ARM_FILE_NAME


def _sweep_claim_files(data_directory: Path) -> None:
    """Remove claim copies a previous take could not delete.

    consume_arm's own unlink is best-effort, because refusing to authorise a logon over a file it
    could not tidy up would trade a real feature for housekeeping. This is where that debt is
    settled instead: at the start of the next arm, when nothing is in flight. A leftover claim file
    is litter and never an authorisation, since only ARM_FILE_NAME is ever looked for.
    """
    try:
        for leftover in Path(data_directory).glob(f"{ARM_FILE_NAME}.claim-*"):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError:
        pass


def arm(data_directory: Path, *, now: float | None = None) -> bool:
    """Record that the NEXT background-session logon was asked for by this application.

    Called immediately before mstsc is launched, so the window in which the marker is live is as
    short as the logon itself. Written atomically for the same reason every other file shared
    between the two sessions is: the reader must never see a half-written marker.
    """
    path = _arm_path(data_directory)
    payload = {"armed_at": time.time() if now is None else now}
    _sweep_claim_files(data_directory)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.with_name(path.name + ".tmp")
        staging.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(staging, path)
        return True
    except (OSError, ValueError):
        return False


def disarm(data_directory: Path) -> None:
    """Drop the marker without consuming it, for a start that never reached a logon."""
    try:
        _arm_path(data_directory).unlink(missing_ok=True)
    except OSError:
        pass


def consume_arm(data_directory: Path, *, now: float | None = None) -> bool:
    """Take the marker and report whether it was present and still fresh.

    The marker authorises ONE logon, and the taking is done by RENAMING it rather than by reading
    and then deleting it. That ordering is the whole point: a read-then-delete lets two logons both
    read the same valid payload before either removes it, so both would be authorised. A rename
    either succeeds or finds nothing, so exactly one caller can ever win, and a caller that could
    not remove the marker is never authorised by it.

    The claimed copy is then deleted whatever it turns out to contain, because a marker left on disk
    is a marker that could arm some later, unrelated RDP logon. That delete is best-effort and the
    next arm sweeps whatever it missed (_sweep_claim_files): a claim copy is inert litter under a
    name nothing ever looks for, so failing to remove one must not cost the user the logon.
    """
    path = _arm_path(data_directory)
    # The pid keeps two racing claimants from colliding on the temporary name itself; a process
    # cannot race against itself, so this is unique for as long as it needs to be.
    claimed = path.with_name(f"{path.name}.claim-{os.getpid()}")
    try:
        os.replace(path, claimed)
    except OSError:
        # Includes "there was no marker" and "another logon already took it". Both mean the same
        # thing here: this launch has no authorisation.
        return False
    try:
        raw = claimed.read_text(encoding="utf-8")
    except (OSError, ValueError):
        raw = None
    try:
        claimed.unlink(missing_ok=True)
    except OSError:
        pass
    if raw is None:
        return False
    try:
        armed_at = float(json.loads(raw)["armed_at"])
    except (KeyError, TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    # Both bounds matter. A marker from the future is as untrustworthy as an expired one, and the
    # clock can genuinely move between the two sessions' reads (a resume from sleep, an NTP step).
    return -ARM_WINDOW_SECONDS <= current - armed_at <= ARM_WINDOW_SECONDS


# ---------------------------------------------------------------------------------------------
# Self-gating: am I the background session?
# ---------------------------------------------------------------------------------------------


def is_remote_session() -> bool | None:
    """Whether this process runs in a remote session, or None when Windows will not say.

    ``SM_REMOTESESSION`` is the documented answer to exactly this question, which is why it is the
    primary gate rather than an inference from session ids.
    """
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.user32
        library.GetSystemMetrics.argtypes = [ctypes.c_int]
        library.GetSystemMetrics.restype = ctypes.c_int
        return bool(library.GetSystemMetrics(_SM_REMOTESESSION))
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def console_session_id() -> int | None:
    """Return the session id currently attached to the physical console, or None."""
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.kernel32
        library.WTSGetActiveConsoleSessionId.argtypes = []
        library.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
        value = int(library.WTSGetActiveConsoleSessionId())
    except (AttributeError, ImportError, OSError, ValueError):
        return None
    return None if value == _INVALID_SESSION_ID else value


def in_background_session() -> bool:
    """Whether this process may act as the background session's macro shell.

    Fails closed, and composes its two signals deliberately rather than requiring both outright.
    ``SM_REMOTESESSION`` must be a confirmed yes: anything else (the console, or an answer Windows
    would not give) is refused, because starting the macro shell on the user's physical desktop is
    the failure this gate exists to prevent. The console-session comparison is then only allowed to
    VETO that yes, never to supply one, so an unreadable console id degrades the check to its
    primary signal instead of disabling the feature outright.
    """
    if is_remote_session() is not True:
        return False
    console = console_session_id()
    own = current_session_id()
    if console is not None and own is not None and console == own:
        # A remote session whose id is the console's is a contradiction; refuse rather than guess.
        return False
    return True


def claim_session_autostart(data_directory: Path) -> bool:
    """Decide whether this ``--session-autostart`` launch should become the macro shell.

    Order matters and is the reason this is one function rather than two calls at the call site.
    The session gate runs FIRST and returns without touching the marker, so the console logon (which
    fires this same Run entry, off the same shared profile) cannot eat the authorisation that the
    background session about to log on is waiting for.

    A refusal also removes nothing: the Run entry survives so the real background session still
    finds it. Only a successful claim retires the entry, which is what keeps this application's
    footprint on the user's machine limited to the moments it is actually starting a session.
    """
    if not in_background_session():
        return False
    if not consume_arm(data_directory):
        return False
    remove_autostart_entry()
    return True
