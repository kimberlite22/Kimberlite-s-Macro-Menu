"""Hand-rolled reader for the AutoHotkey-owned UTF-16 config.ini file.

``configparser`` is intentionally not used: the application stores ordered
collections as numbered keys, which need reconstruction into structured models.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path


Number = int | float

# AHK writes config.ini through many discrete IniWrite/IniDelete calls per save, and the file's
# mtime already changes on the very first of those - a read landing mid-burst can hit a moment
# where AHK still holds the file open for one of the later writes, surfacing to Python as a
# Windows sharing violation (PermissionError, errno 13). Each individual IniWrite/IniDelete only
# holds the file for a moment, so a short retry almost always succeeds.
_READ_RETRY_ATTEMPTS = 3
_READ_RETRY_DELAY_SECONDS = 0.05


@dataclass
class AdvancedStep:
    type: str = ""
    x: Number = 0
    y: Number = 0
    end_x: Number = 0
    end_y: Number = 0
    drag_ms: int = 0


@dataclass
class GeneralConfig:
    round_wait_seconds: Number = 0
    click_delay_ms: int = 0
    place_tower_delay_ms: int = 0
    after_place_click: bool = False
    after_place_click_x: Number = 0
    after_place_click_y: Number = 0
    max_rounds: int = 0
    marker_size: int = 0
    num_placements: int = 0
    slots: list[str] = field(default_factory=lambda: [""] * 10)
    game_process: str = ""
    hole_x: Number = 0
    hole_y: Number = 0
    hole_w: Number = 0
    hole_h: Number = 0
    fullscreen_opening: bool = False
    disconnect_enabled: bool = False
    disconnect_x1: Number = 0
    disconnect_y1: Number = 0
    disconnect_x2: Number = 0
    disconnect_y2: Number = 0
    disconnect_text: str = ""
    disconnect_reconnect_x: Number = 0
    disconnect_reconnect_y: Number = 0
    disconnect_interval_sec: Number = 0
    remote_bridge_enabled: bool = False
    remote_agent_path: str = ""
    remote_server_url: str = ""
    remote_account_email: str = ""
    private_server_link: str = ""
    coord_format: str = ""
    adv_steps: list[AdvancedStep] = field(default_factory=list)
    adv_steps_migrated: bool = False


@dataclass
class StepConfig:
    type: str = ""
    label: str = ""
    x: Number = 0
    y: Number = 0
    end_x: Number = 0
    end_y: Number = 0
    drag_ms: int = 0
    once_per_cycle: bool = False
    on_true_screen: str = ""
    on_false_screen: str = ""
    seconds: Number = 0
    fallback_enabled: bool = False
    fallback_max_attempts: int = 0
    fallback_screen: str = ""
    advanced: bool = False
    outcomes_raw: str = ""


@dataclass
class ScreenConfig:
    name: str = ""
    steps: list[StepConfig] = field(default_factory=list)


@dataclass
class OptionConfig:
    name: str = ""
    x: Number = 0
    y: Number = 0
    available: bool = False
    priority: int = 0
    max_uses: int = 0
    det_x: Number = 0
    det_y: Number = 0
    det_end_x: Number = 0
    det_end_y: Number = 0
    det_text: str = ""
    det_invert: bool = False
    used_count: int = 0
    used_date: str = ""


@dataclass
class PresetConfig:
    name: str
    screens: list[ScreenConfig] = field(default_factory=list)
    options: list[OptionConfig] = field(default_factory=list)
    default_map: str = ""
    back_x: Number = 0
    back_y: Number = 0
    fallback_screen: str = ""


@dataclass
class PlacementConfig:
    custom_slot: str = ""
    x: Number = 0
    y: Number = 0


@dataclass
class MapProfileConfig:
    name: str
    expected_text: str = ""
    custom_towers: bool = False
    custom_num_placements: int = 0
    placements: list[PlacementConfig] = field(default_factory=list)
    custom_camera: bool = False
    adv_steps: list[AdvancedStep] = field(default_factory=list)


@dataclass
class AppConfig:
    general: GeneralConfig
    games: list[str] = field(default_factory=list)
    active_game: str = ""
    presets: list[PresetConfig] = field(default_factory=list)
    active_preset: str = ""
    map_profiles: list[MapProfileConfig] = field(default_factory=list)
    active_map_profile: str = ""


def read_config(path: str | Path) -> AppConfig:
    """Read an AHK UTF-16LE-with-BOM config.ini into typed, ordered models.

    ``utf-16`` deliberately detects the BOM emitted by AutoHotkey IniWrite.  Do
    not change this to UTF-8: config.ini is a Windows UTF-16 file despite .ini.
    """
    # AHK IniWrite writes a UTF-16LE BOM. Python's utf-16 codec consumes it.
    text = _read_ini_text(Path(path))
    sections = _parse_ini(text)

    games_section = sections.get("Games", {})
    games = _split_list(_value(games_section, "List"))
    active_game = _value(games_section, "Active")
    if active_game not in games:
        active_game = games[0] if games else ""

    general_section = sections.get("General", {})
    game_section = sections.get(f"Game_{active_game}", {}) if active_game else {}
    general = _read_general(general_section, game_section)

    presets_list_section = sections.get(f"Game_{active_game}_Presets", {})
    preset_names = _split_list(_value(presets_list_section, "List"))
    presets = [
        _read_preset(name, sections.get(f"Game_{active_game}_Preset_{name}", {}))
        for name in preset_names
    ]

    profiles_list_section = sections.get(f"Game_{active_game}_MapProfiles", {})
    profile_names = _split_list(_value(profiles_list_section, "List"))
    profiles = [
        _read_map_profile(name, sections.get(f"Game_{active_game}_MapProfile_{name}", {}))
        for name in profile_names
    ]
    return AppConfig(
        general=general,
        games=games,
        active_game=active_game,
        presets=presets,
        active_preset=_value(presets_list_section, "Active"),
        map_profiles=profiles,
        active_map_profile=_value(profiles_list_section, "Active"),
    )


def _read_ini_text(path: Path) -> str:
    """Read config.ini's raw text, retrying past a transient sharing violation.

    A FileNotFoundError (the config genuinely does not exist) is not retried - only an OSError
    raised while the path exists is a candidate for the mid-save race this guards against.
    """
    last_error: OSError | None = None
    for attempt in range(_READ_RETRY_ATTEMPTS):
        try:
            return path.read_text(encoding="utf-16")
        except FileNotFoundError:
            raise
        except OSError as error:
            last_error = error
            if attempt + 1 < _READ_RETRY_ATTEMPTS:
                time.sleep(_READ_RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


def _parse_ini(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
            continue
        if current is not None and "=" in raw_line:
            key, value = raw_line.split("=", 1)
            current[key.strip()] = value
    return sections


def _read_general(section: dict[str, str], game_section: dict[str, str]) -> GeneralConfig:
    """Merge the shared [General] section with the active game's own [Game_<name>] section.

    `section` is shared across every game (Game Window, Disconnect, Remote Agent, CoordFormat).
    `game_section` holds the active game's own Timing, Tower Loadout, and shared Advanced Steps.
    Mirrors GeneralKeysMovedIntoGame() in tower_defense_macro_gui.ahk - keep the two in step.
    Reading both into one GeneralConfig keeps every existing caller (main_window.py's widget
    population code) working against the same flat shape unchanged.
    """
    return GeneralConfig(
        round_wait_seconds=_number(_value(game_section, "RoundWaitSeconds")),
        click_delay_ms=_integer(_value(game_section, "ClickDelayMs")),
        place_tower_delay_ms=_integer(_value(game_section, "PlaceTowerDelayMs")),
        after_place_click=_boolean(_value(game_section, "AfterPlaceClick")),
        after_place_click_x=_number(_value(game_section, "AfterPlaceClickX")),
        after_place_click_y=_number(_value(game_section, "AfterPlaceClickY")),
        max_rounds=_integer(_value(game_section, "MaxRounds")),
        marker_size=_integer(_value(game_section, "MarkerSize")),
        num_placements=_integer(_value(game_section, "NumPlacements")),
        slots=[_value(game_section, f"Slot{i}") for i in range(1, 11)],
        game_process=_value(section, "GameProcess"),
        hole_x=_number(_value(section, "HoleX")), hole_y=_number(_value(section, "HoleY")),
        hole_w=_number(_value(section, "HoleW")), hole_h=_number(_value(section, "HoleH")),
        fullscreen_opening=_boolean(_value(section, "FullscreenOpening")),
        disconnect_enabled=_boolean(_value(section, "DisconnectEnabled")),
        disconnect_x1=_number(_value(section, "DisconnectX1")),
        disconnect_y1=_number(_value(section, "DisconnectY1")),
        disconnect_x2=_number(_value(section, "DisconnectX2")),
        disconnect_y2=_number(_value(section, "DisconnectY2")),
        disconnect_text=_value(section, "DisconnectText"),
        disconnect_reconnect_x=_number(_value(section, "DisconnectReconnectX")),
        disconnect_reconnect_y=_number(_value(section, "DisconnectReconnectY")),
        disconnect_interval_sec=_number(_value(section, "DisconnectIntervalSec")),
        remote_bridge_enabled=_boolean(_value(section, "RemoteBridgeEnabled")),
        remote_agent_path=_value(section, "RemoteAgentPath"),
        remote_server_url=_value(section, "RemoteServerUrl"),
        remote_account_email=_value(section, "RemoteAccountEmail"),
        private_server_link=_value(section, "PrivateServerLink"),
        coord_format=_value(section, "CoordFormat"),
        adv_steps=_read_adv_steps(game_section),
        adv_steps_migrated=_adv_steps_migrated(game_section),
    )


def _read_preset(name: str, section: dict[str, str]) -> PresetConfig:
    screens: list[ScreenConfig] = []
    for index in range(1, _integer(_value(section, "ScreenCount")) + 1):
        prefix = f"Screen{index}"
        steps: list[StepConfig] = []
        for step_index in range(1, _integer(_value(section, prefix + "StepCount")) + 1):
            steps.append(_read_step(section, f"{prefix}Step{step_index}"))
        screens.append(ScreenConfig(name=_value(section, prefix + "Name"), steps=steps))
    options = [_read_option(section, index) for index in range(1, 4)]
    return PresetConfig(
        name=name, screens=screens, options=options,
        default_map=_value(section, "DefaultMap"), back_x=_number(_value(section, "BackX")),
        back_y=_number(_value(section, "BackY")), fallback_screen=_value(section, "FallbackScreen"),
    )


def _read_step(section: dict[str, str], prefix: str) -> StepConfig:
    return StepConfig(
        type=_value(section, prefix + "Type"), label=_value(section, prefix + "Label"),
        x=_number(_value(section, prefix + "X")), y=_number(_value(section, prefix + "Y")),
        end_x=_number(_value(section, prefix + "EndX")), end_y=_number(_value(section, prefix + "EndY")),
        drag_ms=_integer(_value(section, prefix + "DragMs")),
        once_per_cycle=_boolean(_value(section, prefix + "OncePerCycle")),
        on_true_screen=_value(section, prefix + "OnTrueScreen"),
        on_false_screen=_value(section, prefix + "OnFalseScreen"),
        seconds=_number(_value(section, prefix + "Seconds")),
        fallback_enabled=_boolean(_value(section, prefix + "FallbackEnabled")),
        fallback_max_attempts=_integer(_value(section, prefix + "FallbackMaxAttempts")),
        fallback_screen=_value(section, prefix + "FallbackScreen"),
        advanced=_boolean(_value(section, prefix + "Advanced")),
        outcomes_raw=_value(section, prefix + "Outcomes"),
    )


def _read_option(section: dict[str, str], index: int) -> OptionConfig:
    prefix = f"Option{index}"
    return OptionConfig(
        name=_value(section, prefix + "Name"), x=_number(_value(section, prefix + "X")),
        y=_number(_value(section, prefix + "Y")), available=_boolean(_value(section, prefix + "Available")),
        priority=_integer(_value(section, prefix + "Priority")), max_uses=_integer(_value(section, prefix + "MaxUses")),
        det_x=_number(_value(section, prefix + "DetX")), det_y=_number(_value(section, prefix + "DetY")),
        det_end_x=_number(_value(section, prefix + "DetEndX")), det_end_y=_number(_value(section, prefix + "DetEndY")),
        det_text=_value(section, prefix + "DetText"), det_invert=_boolean(_value(section, prefix + "DetInvert")),
        used_count=_integer(_value(section, prefix + "UsedCount")), used_date=_value(section, prefix + "UsedDate"),
    )


def _read_map_profile(name: str, section: dict[str, str]) -> MapProfileConfig:
    custom_camera = _boolean(_value(section, "CustomCamera"))
    return MapProfileConfig(
        name=name, expected_text=_value(section, "ExpectedText"),
        custom_towers=_boolean(_value(section, "CustomTowers")),
        custom_num_placements=_integer(_value(section, "CustomNumPlacements")),
        placements=[PlacementConfig(_value(section, f"CustomSlot{i}"), _number(_value(section, f"Placement{i}X")), _number(_value(section, f"Placement{i}Y"))) for i in range(1, 11)],
        custom_camera=custom_camera,
        # Always read these, even while custom_camera is false: AHK does not delete a profile's own
        # AdvStep* keys just because CustomCamera was unchecked - they sit dormant, ready to resume
        # if it's checked again. A caller that needs to edit them (gui/app/map_advanced_window.py)
        # must see that dormant data, or re-enabling custom camera would show an empty list and its
        # next Save would permanently overwrite the real dormant steps with nothing.
        adv_steps=_read_adv_steps(section),
    )


def _read_adv_steps(section: dict[str, str]) -> list[AdvancedStep]:
    """Read a section's camera/zoom actions the same way GetMapAdvSteps() does.

    That includes the legacy fallback, and it has to. A section whose ``AdvStepsMigrated`` marker is
    not set does not hold an ``AdvStep*`` list yet: it still holds the old single
    ``CenterCamera`` drag plus ``ZoomOut`` ticks pair, and the engine derives the list from those on
    its first read. Reading only the numbered keys here showed an EMPTY list for such a section, and
    since the Map Advanced window saves back whatever it was showing, the user's first save silently
    dropped a camera drag they never touched.
    """
    if not _adv_steps_migrated(section):
        return _legacy_adv_steps(section)
    result: list[AdvancedStep] = []
    for index in range(1, _integer(_value(section, "AdvStepsCount")) + 1):
        prefix = f"AdvStep{index}"
        result.append(AdvancedStep(
            type=_value(section, prefix + "Type"), x=_number(_value(section, prefix + "X")),
            y=_number(_value(section, prefix + "Y")), end_x=_number(_value(section, prefix + "EndX")),
            end_y=_number(_value(section, prefix + "EndY")), drag_ms=_integer(_value(section, prefix + "DragMs")),
        ))
    return result


def _adv_steps_migrated(section: dict[str, str]) -> bool:
    """Exactly GetMapAdvSteps()'s own test, which is a string compare, NOT a boolean parse.

    The engine asks ``Cfg(section, "AdvStepsMigrated", "0") != "1"``, so only the literal "1" counts
    as migrated - "true"/"yes"/"on" do not. Using the lenient _boolean() here would put the two sides
    into exactly the disagreement this whole pairing exists to remove: the GUI would read the
    numbered list while the engine still considered the section legacy and overwrote it. IniRead
    trims the value it returns, which is why this compares the stripped text.
    """
    return _value(section, "AdvStepsMigrated").strip() == "1"


def _legacy_adv_steps(section: dict[str, str]) -> list[AdvancedStep]:
    """The pre-list camera format, converted exactly as GetMapAdvSteps()'s migration branch does.

    Keep the defaults (DragMs 500, ZoomTicks 5) identical to that branch: whichever side reads the
    section first decides what gets written back as the migrated list, so a different default here
    would mean the steps depend on whether the GUI or the engine looked at the section first.
    """
    steps: list[AdvancedStep] = []
    if _boolean(_value(section, "CenterCamera")):
        steps.append(AdvancedStep(
            type="Drag",
            x=_number(_value(section, "CamStartX")), y=_number(_value(section, "CamStartY")),
            end_x=_number(_value(section, "CamEndX")), end_y=_number(_value(section, "CamEndY")),
            drag_ms=_integer(_value(section, "CamDragMs") or "500"),
        ))
    if _boolean(_value(section, "ZoomOut")):
        steps.append(AdvancedStep(type="Zoom Out", x=_number(_value(section, "ZoomTicks") or "5"), drag_ms=500))
    return steps


def _value(section: dict[str, str], key: str) -> str:
    return section.get(key, "")


def _split_list(value: str) -> list[str]:
    # JoinList() in tower_defense_macro_gui.ahk writes a plain comma-separated list.
    return [item for item in value.split(",") if item]


def _boolean(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_float(value: str) -> float | None:
    """Parse one config value the way SafeNum() does, or None when it is not a number.

    The comma handling is not cosmetic: these files are written on German-locale machines, where a
    decimal comma is what the user types, and SafeInt()/SafeNum() in tower_defense_macro_gui.ahk
    both normalize it before parsing. A reader that did not would silently read "0,5" as zero.
    """
    text = value.strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _integer(value: str) -> int:
    """The Python counterpart of SafeInt(): comma-tolerant, and ROUNDS rather than truncating.

    Both halves matter for agreeing with the engine. SafeInt() ends in ``Integer(Round(Number(s)))``,
    so it reads "1.6" as 2 and "1,5" as 2; this used to be ``int(float(...))``, which truncated 1.6
    to 1 and rejected "1,5" outright as 0. Any field the GUI shows and then saves back (delays,
    marker size, placement counts) was silently rewritten to that different value.

    Round-half-AWAY-FROM-ZERO, not Python's default round(), which is round-half-to-EVEN and would
    put 0.5 -> 0 and 2.5 -> 2 where AHK gives 1 and 3.
    """
    number = _parse_float(value)
    if number is None:
        return 0
    return math.floor(number + 0.5) if number >= 0 else math.ceil(number - 0.5)


def _number(value: str) -> Number:
    number = _parse_float(value)
    if number is None:
        return 0
    return int(number) if number.is_integer() else number
