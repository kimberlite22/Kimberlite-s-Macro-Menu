"""Hand-rolled reader for the AutoHotkey-owned UTF-16 config.ini file.

``configparser`` is intentionally not used: the application stores ordered
collections as numbered keys, which need reconstruction into structured models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


Number = int | float


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
    text = Path(path).read_text(encoding="utf-16")
    sections = _parse_ini(text)
    general_section = sections.get("General", {})
    general = _read_general(general_section)

    presets_section = sections.get("Presets", {})
    preset_names = _split_list(_value(presets_section, "List"))
    presets = [_read_preset(name, sections.get("Preset_" + name, {})) for name in preset_names]

    profiles_section = sections.get("MapProfiles", {})
    profile_names = _split_list(_value(profiles_section, "List"))
    profiles = [_read_map_profile(name, sections.get("MapProfile_" + name, {})) for name in profile_names]
    return AppConfig(
        general=general,
        presets=presets,
        active_preset=_value(presets_section, "Active"),
        map_profiles=profiles,
        active_map_profile=_value(profiles_section, "Active"),
    )


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


def _read_general(section: dict[str, str]) -> GeneralConfig:
    return GeneralConfig(
        round_wait_seconds=_number(_value(section, "RoundWaitSeconds")),
        click_delay_ms=_integer(_value(section, "ClickDelayMs")),
        place_tower_delay_ms=_integer(_value(section, "PlaceTowerDelayMs")),
        after_place_click=_boolean(_value(section, "AfterPlaceClick")),
        after_place_click_x=_number(_value(section, "AfterPlaceClickX")),
        after_place_click_y=_number(_value(section, "AfterPlaceClickY")),
        max_rounds=_integer(_value(section, "MaxRounds")),
        marker_size=_integer(_value(section, "MarkerSize")),
        num_placements=_integer(_value(section, "NumPlacements")),
        slots=[_value(section, f"Slot{i}") for i in range(1, 11)],
        game_process=_value(section, "GameProcess"),
        hole_x=_number(_value(section, "HoleX")), hole_y=_number(_value(section, "HoleY")),
        hole_w=_number(_value(section, "HoleW")), hole_h=_number(_value(section, "HoleH")),
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
        coord_format=_value(section, "CoordFormat"),
        adv_steps=_read_adv_steps(section),
        adv_steps_migrated=_boolean(_value(section, "AdvStepsMigrated")),
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
    result: list[AdvancedStep] = []
    for index in range(1, _integer(_value(section, "AdvStepsCount")) + 1):
        prefix = f"AdvStep{index}"
        result.append(AdvancedStep(
            type=_value(section, prefix + "Type"), x=_number(_value(section, prefix + "X")),
            y=_number(_value(section, prefix + "Y")), end_x=_number(_value(section, prefix + "EndX")),
            end_y=_number(_value(section, prefix + "EndY")), drag_ms=_integer(_value(section, prefix + "DragMs")),
        ))
    return result


def _value(section: dict[str, str], key: str) -> str:
    return section.get(key, "")


def _split_list(value: str) -> list[str]:
    # JoinList() in tower_defense_macro_gui.ahk writes a plain comma-separated list.
    return [item for item in value.split(",") if item]


def _boolean(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _integer(value: str) -> int:
    try:
        return int(float(value.strip()))
    except (TypeError, ValueError):
        return 0


def _number(value: str) -> Number:
    text = value.strip().replace(",", ".")
    if not text:
        return 0
    try:
        number = float(text)
    except ValueError:
        return 0
    return int(number) if number.is_integer() else number
