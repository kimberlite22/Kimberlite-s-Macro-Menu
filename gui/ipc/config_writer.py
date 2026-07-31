"""Key-preserving writer for the config.ini the AHK engine reads.

This is the write half of :mod:`config_reader`, and the reason the GUI no longer asks the engine
to persist anything: the engine wrote config.ini one key at a time through ``IniWrite``, and every
single one of those calls rewrites the WHOLE file under an exclusive lock.  One Save click fired
hundreds of them while this process re-read the same file every 250ms, which is where the sharing
violations, the ack timeouts and the half-saved configs came from.  Here a save is one document, one
temp file and one atomic replace, so a reader only ever sees the old file or the new one.

Two rules this module exists to enforce:

* **Never serialize from the typed model alone.**  config.ini holds keys no dataclass in
  config_reader models (``RegionX1``, ``StartX``, ``ScreenWidth``, ``CenterCamera``,
  ``AdvStepsMigrated``, ``CoordFormat``, ``ScreenDetectionSchema``, whatever a future engine version
  adds).  Writing only the modelled keys would delete the rest.  :class:`IniDocument` therefore
  edits the file that is on disk as an ordered list of lines and touches nothing it was not asked
  to touch.
* **Match AutoHotkey's own INI semantics.**  Section and key names are compared case-insensitively
  (``IniRead`` does), the file stays UTF-16LE with a BOM and CRLF line endings, because that is what
  ``IniRead`` parses.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


# Mirrors config_reader's read retry: another process (the engine's one-time coordinate migration,
# or an editor) can still hold the file for a moment. Writing is worth retrying for the same reason.
_WRITE_RETRY_ATTEMPTS = 5
_WRITE_RETRY_DELAY_SECONDS = 0.1

# BackupConfig() in tower_defense_macro_gui.ahk keeps this many timestamped snapshots.
BACKUP_KEEP = 10
_BACKUP_DIR_NAME = "config_backups"
_BACKUP_PATTERN = re.compile(r"^config_\d{8}_\d{6}\.ini$", re.IGNORECASE)

_SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]*)\]\s*$")


class IniDocument:
    """An ordered, case-insensitive, key-preserving view of one INI file.

    Backed by the raw lines rather than a dict of dicts, so comments, blank lines, key order and
    every key this application does not model survive a load/modify/save round trip untouched.
    """

    def __init__(self, lines: Sequence[str] | None = None) -> None:
        self._lines: list[str] = list(lines or [])

    # ---- construction -------------------------------------------------------------------

    @classmethod
    def from_text(cls, text: str) -> "IniDocument":
        text = text.lstrip("\ufeff")
        # Splitting on the universal newlines and re-joining with CRLF on write normalizes a file
        # that was hand-edited in an editor that used LF.
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        return cls([line.rstrip("\r") for line in lines])

    @classmethod
    def load(cls, path: str | Path) -> "IniDocument":
        """Read an existing config.ini, or return an empty document when there is none yet."""
        try:
            raw = Path(path).read_bytes()
        except FileNotFoundError:
            return cls()
        return cls.from_text(_decode(raw))

    # ---- reading ------------------------------------------------------------------------

    def sections(self) -> list[str]:
        return [match.group("name") for line in self._lines if (match := _SECTION_RE.match(line))]

    def has_section(self, section: str) -> bool:
        return _fold(section) in {_fold(name) for name in self.sections()}

    def get(self, section: str, key: str, default: str = "") -> str:
        index = self._find_key(section, key)
        if index is None:
            return default
        return self._lines[index].split("=", 1)[1]

    def keys(self, section: str) -> list[str]:
        """Every key name in `section`, in file order."""
        result: list[str] = []
        for index in self._section_body(section):
            name = _key_of(self._lines[index])
            if name is not None:
                result.append(name)
        return result

    # ---- writing ------------------------------------------------------------------------

    def set(self, section: str, key: str, value: Any) -> None:
        """Set one key, updating it in place when it exists so key order never churns."""
        text = _format_value(value)
        index = self._find_key(section, key)
        if index is not None:
            # Keep the key's own spelling from the file: AHK compares case-insensitively, and
            # rewriting the case for no reason would show up as noise in every diff and backup.
            self._lines[index] = f"{_key_of(self._lines[index])}={text}"
            return
        self._lines.insert(self._insert_position(section), f"{key}={text}")

    def set_many(self, section: str, values: Mapping[str, Any]) -> None:
        for key, value in values.items():
            self.set(section, key, value)

    def delete(self, section: str, key: str) -> None:
        index = self._find_key(section, key)
        if index is not None:
            del self._lines[index]

    def delete_keys(self, section: str, predicate: Callable[[str], bool]) -> None:
        """Delete every key in `section` whose name satisfies `predicate`."""
        for index in sorted(self._section_body(section), reverse=True):
            name = _key_of(self._lines[index])
            if name is not None and predicate(name):
                del self._lines[index]

    def delete_section(self, section: str) -> None:
        body = self._section_body(section)
        header = self._find_section(section)
        if header is None:
            return
        for index in sorted(body + [header], reverse=True):
            del self._lines[index]

    def rename_section(self, old: str, new: str) -> None:
        index = self._find_section(old)
        if index is not None:
            self._lines[index] = f"[{new}]"

    # ---- serialization ------------------------------------------------------------------

    def to_text(self) -> str:
        return "".join(f"{line}\r\n" for line in self._lines)

    def to_bytes(self) -> bytes:
        # UTF-16LE with a BOM is what AHK's IniWrite produces and what IniRead expects. The BOM is
        # not optional: without it Windows reads the file as ANSI and every value comes back garbled.
        return ("\ufeff" + self.to_text()).encode("utf-16-le")

    def write_atomic(self, path: str | Path) -> None:
        """Write the document so a concurrent reader sees either the old file or the new one.

        os.replace is atomic within a volume, which is the whole point: the engine's ``Cfg()`` does
        a fresh ``IniRead`` on every single call, so a reader that opened the old file keeps a
        consistent view and the next call gets the complete new one. There is no window in which
        config.ini is truncated or half written.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".tmp")
        payload = self.to_bytes()

        last_error: OSError | None = None
        for attempt in range(_WRITE_RETRY_ATTEMPTS):
            try:
                temp.write_bytes(payload)
                os.replace(temp, target)
                return
            except OSError as error:
                last_error = error
                if attempt + 1 < _WRITE_RETRY_ATTEMPTS:
                    time.sleep(_WRITE_RETRY_DELAY_SECONDS)
        try:
            temp.unlink()
        except OSError:
            pass
        assert last_error is not None
        raise last_error

    # ---- internals ----------------------------------------------------------------------

    def _find_section(self, section: str) -> int | None:
        wanted = _fold(section)
        for index, line in enumerate(self._lines):
            match = _SECTION_RE.match(line)
            if match is not None and _fold(match.group("name")) == wanted:
                return index
        return None

    def _section_body(self, section: str) -> list[int]:
        """Line indexes belonging to `section`, excluding its own header."""
        start = self._find_section(section)
        if start is None:
            return []
        body: list[int] = []
        for index in range(start + 1, len(self._lines)):
            if _SECTION_RE.match(self._lines[index]):
                break
            body.append(index)
        return body

    def _find_key(self, section: str, key: str) -> int | None:
        wanted = _fold(key)
        for index in self._section_body(section):
            name = _key_of(self._lines[index])
            if name is not None and _fold(name) == wanted:
                return index
        return None

    def _insert_position(self, section: str) -> int:
        """Where a new key of `section` goes, creating the section itself when it is missing."""
        body = self._section_body(section)
        if not body:
            if self._find_section(section) is None:
                self._lines.append(f"[{section}]")
                return len(self._lines)
            return self._find_section(section) + 1  # type: ignore[operator]
        # After the section's last non-blank line, so a blank separator before the next section
        # stays a separator instead of collecting appended keys behind it.
        last = body[0]
        for index in body:
            if self._lines[index].strip():
                last = index
        return last + 1


def _decode(raw: bytes) -> str:
    """Decode config.ini, preferring the UTF-16LE the engine writes but tolerating UTF-8."""
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-16")
    except UnicodeError:
        return raw.decode("utf-8", errors="replace")


def _fold(name: str) -> str:
    return name.strip().casefold()


def _key_of(line: str) -> str | None:
    """The key name of a `Key=Value` line, or None for anything else (blank, comment, junk)."""
    if not line or line.lstrip().startswith((";", "#")):
        return None
    key, separator, _ = line.partition("=")
    return key if separator else None


def _format_value(value: Any) -> str:
    """Render one value the way the engine's SafeInt/SafeNum will read it back.

    Floats go through ``%.10g`` so a value that only exists because of binary float representation
    (``32.051000000000002``, which is what a JSON round trip of 32.051 produced) is written as the
    number the user actually entered, without inventing precision the value never had.
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.10g}"
    if value is None:
        return ""
    # A newline would silently split one value into a second, bogus line on the next read.
    return str(value).replace("\r", " ").replace("\n", " ")


def backup_config(path: str | Path, keep: int = BACKUP_KEEP) -> None:
    """Snapshot config.ini into config_backups/ and prune to the newest `keep` snapshots.

    A port of BackupConfig() (tower_defense_macro_gui.ahk): config.ini is a single file holding
    EVERY preset, map profile and setting, so a cheap copy before overwriting it is the insurance.
    Best-effort exactly like the original - a failure here must never block the save itself.
    """
    try:
        source = Path(path)
        if not source.exists():
            return
        backup_dir = source.parent / _BACKUP_DIR_NAME
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        (backup_dir / f"config_{stamp}.ini").write_bytes(source.read_bytes())

        # The yyyyMMdd_HHmmss stamp makes plain name order match chronological order (oldest first).
        existing = sorted(
            entry for entry in backup_dir.iterdir() if _BACKUP_PATTERN.match(entry.name)
        )
        for stale in existing[: max(0, len(existing) - keep)]:
            try:
                stale.unlink()
            except OSError:
                pass
    except OSError:
        pass


# --------------------------------------------------------------------------------------------
# Payload -> INI key mapping
# --------------------------------------------------------------------------------------------
# These take the SAME payload dicts that used to travel over the bridge as the SAVE_* verbs, so the
# widget-reading code in main_window and the secondary windows is unchanged and its tests still
# apply. Each function is the direct counterpart of the AHK writer named in its docstring; keep them
# in step if either side gains a field.


def apply_general(document: IniDocument, payload: Mapping[str, Any]) -> None:
    """Counterpart of SaveGeneralFromData() (tower_defense_macro_gui.ahk)."""
    scalar_keys = {
        "RoundWaitSeconds": "roundWaitSeconds", "ClickDelayMs": "clickDelayMs",
        "PlaceTowerDelayMs": "placeTowerDelayMs", "AfterPlaceClick": "afterPlaceClick",
        "AfterPlaceClickX": "afterPlaceClickX", "AfterPlaceClickY": "afterPlaceClickY",
        "MaxRounds": "maxRounds", "MarkerSize": "markerSize", "NumPlacements": "numPlacements",
        "GameProcess": "gameProcess", "HoleX": "holeX", "HoleY": "holeY", "HoleW": "holeW",
        "HoleH": "holeH", "DisconnectEnabled": "disconnectEnabled",
        "DisconnectX1": "disconnectX1", "DisconnectY1": "disconnectY1",
        "DisconnectX2": "disconnectX2", "DisconnectY2": "disconnectY2",
        "DisconnectText": "disconnectText", "DisconnectReconnectX": "disconnectReconnectX",
        "DisconnectReconnectY": "disconnectReconnectY",
        "DisconnectIntervalSec": "disconnectIntervalSec",
        "RemoteBridgeEnabled": "remoteBridgeEnabled",
    }
    for ini_key, payload_key in scalar_keys.items():
        if payload_key in payload:
            document.set("General", ini_key, payload[payload_key])

    slots = payload.get("slots")
    if slots is not None:
        for index, slot in enumerate(slots, start=1):
            document.set("General", f"Slot{index}", slot)


def apply_preset(document: IniDocument, payload: Mapping[str, Any]) -> None:
    """Counterpart of LocalBridgeReplacePresetScreens() + SavePresetToIni()."""
    name = payload["name"]
    section = f"Preset_{name}"

    # Same rule the bridge used: drop every key whose name contains "Screen" before rebuilding, or
    # removing a screen would leave its steps behind as stale keys. The preset-level FallbackScreen
    # also matches, and is rewritten below, exactly as before.
    document.delete_keys(section, lambda key: "screen" in key.casefold())

    screens = list(payload.get("screens", ()))
    document.set(section, "ScreenCount", len(screens))
    for index, screen in enumerate(screens, start=1):
        _apply_screen(document, section, index, screen)

    options = list(payload.get("options", ()))
    if len(options) != 3:
        raise ValueError("a preset save requires exactly three options")
    option_keys = {
        "Name": "name", "X": "x", "Y": "y", "Available": "available", "Priority": "priority",
        "MaxUses": "maxUses", "DetX": "detX", "DetY": "detY", "DetEndX": "detEndX",
        "DetEndY": "detEndY", "DetText": "detText", "DetInvert": "detInvert",
    }
    for index, option in enumerate(options, start=1):
        for ini_suffix, payload_key in option_keys.items():
            document.set(section, f"Option{index}{ini_suffix}", option.get(payload_key, ""))

    document.set(section, "DefaultMap", payload.get("defaultMap", ""))
    document.set(section, "BackX", payload.get("backX", 0))
    document.set(section, "BackY", payload.get("backY", 0))
    document.set(section, "FallbackScreen", payload.get("fallbackScreen", ""))


def _apply_screen(document: IniDocument, section: str, index: int, screen: Mapping[str, Any]) -> None:
    """Counterpart of WriteScreenSteps()."""
    steps = list(screen.get("steps", ()))
    document.set(section, f"Screen{index}Name", screen.get("name", ""))
    document.set(section, f"Screen{index}StepCount", len(steps))
    step_keys = {
        "Type": "type", "Label": "label", "X": "x", "Y": "y", "EndX": "endX", "EndY": "endY",
        "DragMs": "dragMs", "OncePerCycle": "oncePerCycle", "OnTrueScreen": "onTrueScreen",
        "OnFalseScreen": "onFalseScreen", "Seconds": "seconds",
        "FallbackEnabled": "fallbackEnabled", "FallbackMaxAttempts": "fallbackMaxAttempts",
        "FallbackScreen": "fallbackScreen", "Advanced": "advanced", "Outcomes": "outcomesRaw",
    }
    for step_index, step in enumerate(steps, start=1):
        prefix = f"Screen{index}Step{step_index}"
        for ini_suffix, payload_key in step_keys.items():
            document.set(section, f"{prefix}{ini_suffix}", step.get(payload_key, ""))


def apply_map_profile(document: IniDocument, payload: Mapping[str, Any]) -> None:
    """Counterpart of SaveMapProfileToIni()."""
    section = f"MapProfile_{payload['name']}"
    placements = list(payload.get("placements", ()))
    if len(placements) > 10:
        raise ValueError("a map profile save accepts at most ten placements")
    document.set(section, "ExpectedText", payload.get("expectedText", ""))
    document.set(section, "CustomTowers", payload.get("customTowers", False))
    document.set(section, "CustomNumPlacements", payload.get("customNumPlacements", 0))
    for index, placement in enumerate(placements, start=1):
        document.set(section, f"CustomSlot{index}", placement.get("customSlot", ""))
        document.set(section, f"Placement{index}X", placement.get("x", 0))
        document.set(section, f"Placement{index}Y", placement.get("y", 0))
    document.set(section, "CustomCamera", payload.get("customCamera", False))


def adv_steps_section(document: IniDocument, map_profile_name: str) -> str:
    """Which section a map profile's camera steps live in.

    Ported from LocalBridgeSaveAdvMapSteps: a profile only owns its own AdvStep* keys while its
    CustomCamera flag is set, otherwise the shared [General] steps are the ones being edited.
    """
    if map_profile_name == "General":
        return "General"
    section = f"MapProfile_{map_profile_name}"
    custom = document.get(section, "CustomCamera", "0").strip().lower()
    return section if custom in {"1", "true", "yes", "on"} else "General"


def apply_adv_steps(document: IniDocument, section: str, steps: Iterable[Mapping[str, Any]]) -> None:
    """Counterpart of SaveMapAdvStepsArr()."""
    step_list = list(steps)
    document.set(section, "AdvStepsCount", len(step_list))
    keys = {"Type": "type", "X": "x", "Y": "y", "EndX": "endX", "EndY": "endY", "DragMs": "dragMs"}
    for index, step in enumerate(step_list, start=1):
        for ini_suffix, payload_key in keys.items():
            document.set(section, f"AdvStep{index}{ini_suffix}", step.get(payload_key, ""))


def save_config(
    path: str | Path, *,
    general: Mapping[str, Any] | None = None,
    preset: Mapping[str, Any] | None = None,
    map_profile: Mapping[str, Any] | None = None,
    adv_steps: Mapping[str, Any] | None = None,
) -> str:
    """Apply every given payload to config.ini in ONE load, ONE backup and ONE atomic write.

    This is the whole point of the module. The same edit used to be three separate bridge commands,
    each with its own token, ack and 5s timeout, and each expanding into dozens or hundreds of
    whole-file rewrites on the engine side. A partial failure left config.ini half saved with
    nothing but a joined status-bar string to say so. Here either everything lands or nothing does.

    Returns a short human-readable summary for the status bar.
    """
    if general is not None:
        # Before touching the file: a zero-size opening is unrecoverable once written.
        validate_general(general)

    document = IniDocument.load(path)
    saved: list[str] = []
    if general is not None:
        apply_general(document, general)
        saved.append("general settings")
    if map_profile is not None:
        apply_map_profile(document, map_profile)
        saved.append(f"map profile {map_profile['name']}")
    if preset is not None:
        apply_preset(document, preset)
        saved.append(f"preset {preset['name']}")
    if adv_steps is not None:
        name = adv_steps["mapProfileName"]
        section = adv_steps_section(document, name)
        apply_adv_steps(document, section, adv_steps.get("steps", ()))
        saved.append(f"camera steps ({section})")

    if not saved:
        return "Nothing to save."

    backup_config(path)
    document.write_atomic(path)
    return "Saved: " + ", ".join(saved) + "."


class ConfigValidationError(ValueError):
    """A save was refused because it would store a config the engine cannot act on."""


def validate_general(payload: Mapping[str, Any]) -> None:
    """Refuse the one General state that silently breaks every coordinate in the file.

    Every click, drag and detection region is stored as a percentage of the game window opening.
    With a zero-size opening AbsXY() falls back to treating that percentage as a raw screen pixel
    (tower_defense_macro_gui.ahk), so the macro clicks in the top-left corner of the screen instead
    of in the game. It is worth refusing at the point of saving rather than letting the file reach
    that state, because nothing downstream can tell the difference afterwards.
    """
    width = payload.get("holeW", 0) or 0
    height = payload.get("holeH", 0) or 0
    if width <= 0 or height <= 0:
        raise ConfigValidationError(
            "Not saved: the game window opening has no size (width and height must both be "
            "greater than 0). Every stored coordinate is a percentage of that opening, so saving "
            "a zero-size opening would make every click land in the corner of the screen."
        )
