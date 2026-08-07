"""Ask Roblox itself to come up full screen, instead of resizing its window afterwards.

Roblox remembers its own window state per Windows USER, in
``%LOCALAPPDATA%\\Roblox\\GlobalBasicSettings_13.xml`` (``Fullscreen``, next to ``StartScreenSize``
and ``StartScreenPosition``). A background session runs as that same user, so it inherits whatever
the physical desktop last left there. That is also why the setting cannot simply be ticked once by
hand and then trusted: Roblox rewrites the whole file when it exits, so one ordinary windowed round
on the physical desktop puts it straight back.

Writing the value ourselves just before the session launches Roblox is what makes the window full
screen FROM THE MOMENT IT APPEARS, with nothing moving or resizing it afterwards. That matters
because the engine deliberately stops asserting the window's geometry in a background session (see
LeaveGameWindowGeometryAlone() in macro/tower_defense_macro_gui.ahk): with the window lock gone,
there is no longer anything that would put a badly sized window where it belongs after the fact, so
the size has to be right at launch rather than corrected later.

Deliberately the narrowest possible edit. This file belongs to Roblox and holds every graphics,
audio and input preference the user has, so exactly one boolean element is matched and rewritten,
only when it is currently false, and the bytes around it (including the file's own line endings) are
carried through untouched. A file that does not look the way this expects is left completely alone
rather than repaired, regenerated or rewritten from a parsed model: not being able to set the
preference costs a session that starts windowed, while getting the rewrite wrong costs the user
every setting in it.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import NamedTuple


SETTINGS_FILE_NAME = "GlobalBasicSettings_13.xml"

# Matched rather than parsed, so everything this does not understand survives byte for byte. The
# element is written by Roblox itself and has been stable for many client versions; the tolerant
# whitespace and the case-insensitive value keep a cosmetic reformat from turning into a refusal,
# while the anchored name attribute keeps it from ever matching a different setting.
_FULLSCREEN_ELEMENT = re.compile(
    r'(<bool\s+name="Fullscreen"\s*>)\s*(true|false)\s*(</bool>)',
    re.IGNORECASE,
)


class FullscreenOutcome(NamedTuple):
    """What one attempt did, and a line saying so for the session log.

    ``ready`` answers the only question a caller has: will the next Roblox launch come up full
    screen? It is true both when this call changed the setting and when it was already set, because
    a caller that treated "nothing to do" as a failure would log a problem that does not exist.
    """

    ready: bool
    changed: bool
    message: str


def settings_path(local_app_data: Path | None = None) -> Path:
    """Where Roblox keeps the settings file, for this Windows user.

    ``local_app_data`` exists so the tests can point this somewhere harmless. In production the
    environment variable is the only source: the path is per user, and a background session is the
    same user, which is the entire reason this module works from inside one.
    """
    if local_app_data is None:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    return Path(local_app_data) / "Roblox" / SETTINGS_FILE_NAME


def enable_fullscreen(path: Path | None = None) -> FullscreenOutcome:
    """Turn Roblox' own ``Fullscreen`` setting on, so its next launch fills the screen by itself.

    Every failure is reported rather than raised. The caller is a background session's start-up path
    where nothing may throw, and none of these outcomes is worth failing a session over: the worst
    case is a Roblox window that is not full screen, which the user can still fix with F11.
    """
    if path is None:
        path = settings_path()
    path = Path(path)
    try:
        # newline="" so the file's own line endings are read as they are and written back unchanged.
        # Without it the round trip silently rewrites every line in the file, which is a much larger
        # edit than this module is willing to make to somebody else's data.
        with path.open("r", encoding="utf-8", newline="") as settings_file:
            text = settings_file.read()
    except FileNotFoundError:
        return FullscreenOutcome(
            False,
            False,
            "Roblox has no settings file yet, so its fullscreen setting was left alone.",
        )
    except (OSError, UnicodeDecodeError):
        return FullscreenOutcome(
            False,
            False,
            "Roblox' settings file could not be read, so its fullscreen setting was left alone.",
        )

    matches = _FULLSCREEN_ELEMENT.findall(text)
    if len(matches) != 1:
        # Zero means a client that names the setting differently; more than one means a file this
        # module does not understand well enough to edit. Both are "leave it alone".
        return FullscreenOutcome(
            False,
            False,
            "Roblox' settings file does not hold exactly one fullscreen setting, "
            "so it was left alone.",
        )
    if matches[0][1].lower() == "true":
        return FullscreenOutcome(
            True, False, "Roblox was already set to start full screen."
        )

    updated = _FULLSCREEN_ELEMENT.sub(r"\1true\3", text, count=1)
    if not _write_atomically(path, updated):
        return FullscreenOutcome(
            False,
            False,
            "Roblox' fullscreen setting could not be written, so Roblox starts the way it did.",
        )
    return FullscreenOutcome(True, True, "Roblox was set to start full screen.")


def _write_atomically(path: Path, text: str) -> bool:
    """Replace ``path`` in one step, so a failure leaves the user's settings as they were.

    The temporary file is a sibling, because os.replace is only atomic within one filesystem, and it
    is removed again on every failure: a stray file in Roblox' own directory is exactly the kind of
    litter this module has no right to leave behind.

    mkstemp rather than a fixed ".tmp" name, so the name is both unique and created exclusively. Two
    calls overlapping (the session's start-up and its control window's button, or a second session on
    the same profile) would otherwise share one temporary file and could publish each other's
    half-written snapshot, and a fixed name would additionally adopt, and then delete, a file
    somebody else happened to leave there.
    """
    directory = path.parent
    try:
        handle, temporary_name = tempfile.mkstemp(
            dir=directory, prefix=path.name + ".", suffix=".tmp"
        )
    except OSError:
        return False
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as settings_file:
            settings_file.write(text)
        os.replace(temporary, path)
        return True
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        return False
