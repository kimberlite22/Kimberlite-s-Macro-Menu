"""Wire types and payload builders for the local AHK GUI bridge.

The bridge owns the exact file format.  This module keeps Python call sites from
hand-assembling loosely structured dictionaries as the protocol grows.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


VERB_SET_ACTIVE_PRESET = "SET_ACTIVE_PRESET"
VERB_START = "START"
VERB_PAUSE = "PAUSE"
VERB_RESUME = "RESUME"
VERB_STOP = "STOP"
VERB_START_CAPTURE = "START_CAPTURE"
VERB_START_CAPTURE_REGION = "START_CAPTURE_REGION"
VERB_CANCEL_CAPTURE = "CANCEL_CAPTURE"
VERB_LIST_GAME_PROCESSES = "LIST_GAME_PROCESSES"
VERB_FORCE_GAME_WINDOW = "FORCE_GAME_WINDOW"
VERB_SHOW_REGION_PREVIEW = "SHOW_REGION_PREVIEW"
VERB_SHOW_POINT_PREVIEW = "SHOW_POINT_PREVIEW"
VERB_TEST_OCR = "TEST_OCR"
VERB_PAIR_REMOTE_AGENT = "PAIR_REMOTE_AGENT"
VERB_START_REMOTE_AGENT = "START_REMOTE_AGENT"
VERB_STOP_REMOTE_AGENT = "STOP_REMOTE_AGENT"


@dataclass(frozen=True)
class LocalStatus:
    schema: int = 1
    timestamp: str = ""
    running: bool = False
    paused: bool = False
    dry_run: bool = False
    active_preset: str = ""
    running_preset: str = ""
    queued_preset: str = ""
    current_map: str = ""
    current_screen: str = ""
    current_step: str = ""
    cycle_count: int = 0
    step_repeat_count: int = 0
    start_repeat_count: int = 0
    victory_count: int = 0
    defeat_count: int = 0
    session_id: str = ""
    session_time_ms: int = 0
    current_step_time_ms: int = -1
    # screenTimeMs/stepTimeMs are the only non-scalar status fields.
    screen_time_ms: Mapping[str, int] = field(default_factory=dict)
    step_time_ms: Mapping[str, int] = field(default_factory=dict)
    config_version: int = 0
    capture_active: bool = False
    capture_field_id: str = ""

    @classmethod
    def from_json_dict(cls, value: Mapping[str, Any]) -> "LocalStatus":
        """Build a status snapshot, accepting missing or future fields."""
        return cls(
            schema=_as_int(value.get("schema"), 1),
            timestamp=_as_str(value.get("timestamp")),
            running=_as_bool(value.get("running")),
            paused=_as_bool(value.get("paused")),
            dry_run=_as_bool(value.get("dryRun")),
            active_preset=_as_str(value.get("activePreset")),
            running_preset=_as_str(value.get("runningPreset")),
            queued_preset=_as_str(value.get("queuedPreset")),
            current_map=_as_str(value.get("currentMap")),
            current_screen=_as_str(value.get("currentScreen")),
            current_step=_as_str(value.get("currentStep")),
            cycle_count=_as_int(value.get("cycleCount")),
            step_repeat_count=_as_int(value.get("stepRepeatCount")),
            start_repeat_count=_as_int(value.get("startRepeatCount")),
            victory_count=_as_int(value.get("victoryCount")),
            defeat_count=_as_int(value.get("defeatCount")),
            session_id=_as_str(value.get("sessionId")),
            session_time_ms=_as_int(value.get("sessionTimeMs")),
            current_step_time_ms=_as_int(value.get("currentStepTimeMs"), -1),
            screen_time_ms=_as_int_map(value.get("screenTimeMs")),
            step_time_ms=_as_int_map(value.get("stepTimeMs")),
            config_version=_as_int(value.get("configVersion")),
            capture_active=_as_bool(value.get("captureActive")),
            capture_field_id=_as_str(value.get("captureFieldId")),
        )


@dataclass(frozen=True)
class CaptureResult:
    """A point or region result published by the AHK capture overlay."""

    mode: str = ""
    field_id: str | None = None
    field_ids: tuple[str, ...] | None = None
    cancelled: bool = False
    x: float | None = None
    y: float | None = None
    x1: float | None = None
    y1: float | None = None
    x2: float | None = None
    y2: float | None = None

    @classmethod
    def from_json_dict(cls, value: Mapping[str, Any]) -> "CaptureResult":
        """Build a tolerant result model from the one-line capture JSON object."""
        if not isinstance(value, Mapping):
            return cls()
        raw_field_ids = value.get("fieldIds")
        field_ids = (
            tuple(raw_field_ids)
            if isinstance(raw_field_ids, (list, tuple)) and all(isinstance(item, str) for item in raw_field_ids)
            else None
        )
        field_id = value.get("fieldId")
        return cls(
            mode=_as_str(value.get("mode")),
            field_id=field_id if isinstance(field_id, str) else None,
            field_ids=field_ids,
            cancelled=_as_bool(value.get("cancelled")),
            x=_as_float_or_none(value.get("x")),
            y=_as_float_or_none(value.get("y")),
            x1=_as_float_or_none(value.get("x1")),
            y1=_as_float_or_none(value.get("y1")),
            x2=_as_float_or_none(value.get("x2")),
            y2=_as_float_or_none(value.get("y2")),
        )


@dataclass(frozen=True)
class GameProcessCandidate:
    """A game window candidate published by the AHK process scan."""

    title: str = ""
    process: str = ""

    @classmethod
    def from_json_dict(cls, value: Mapping[str, Any]) -> "GameProcessCandidate":
        """Build a tolerant process candidate from one JSON object."""
        if not isinstance(value, Mapping):
            return cls()
        return cls(title=_as_str(value.get("title")), process=_as_str(value.get("process")))


@dataclass(frozen=True)
class StepPayload:
    type: str
    label: str = ""
    x: float = 0
    y: float = 0
    end_x: float = 0
    end_y: float = 0
    drag_ms: int = 0
    once_per_cycle: bool = False
    seconds: float = 0
    on_true_screen: str = ""
    on_false_screen: str = ""
    fallback_enabled: bool = False
    fallback_max_attempts: int = 0
    fallback_screen: str = ""
    advanced: bool = False
    outcomes_raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type, "label": self.label, "x": self.x, "y": self.y,
            "endX": self.end_x, "endY": self.end_y, "dragMs": self.drag_ms,
            "oncePerCycle": self.once_per_cycle, "seconds": self.seconds,
            "onTrueScreen": self.on_true_screen, "onFalseScreen": self.on_false_screen,
            "fallbackEnabled": self.fallback_enabled,
            "fallbackMaxAttempts": self.fallback_max_attempts,
            "fallbackScreen": self.fallback_screen, "advanced": self.advanced,
            "outcomesRaw": self.outcomes_raw,
        }


@dataclass(frozen=True)
class GeneralPayload:
    round_wait_seconds: float = 0
    click_delay_ms: int = 0
    place_tower_delay_ms: int = 0
    after_place_click: bool = False
    after_place_click_x: float = 0
    after_place_click_y: float = 0
    max_rounds: int = 0
    marker_size: int = 0
    num_placements: int = 0
    slots: tuple[str, ...] = ("", "", "", "", "", "", "", "", "", "")
    game_process: str = ""
    hole_x: float = 0
    hole_y: float = 0
    hole_w: float = 0
    hole_h: float = 0
    fullscreen_opening: bool = False
    disconnect_enabled: bool = False
    disconnect_x1: float = 0
    disconnect_y1: float = 0
    disconnect_x2: float = 0
    disconnect_y2: float = 0
    disconnect_text: str = ""
    disconnect_reconnect_x: float = 0
    disconnect_reconnect_y: float = 0
    disconnect_interval_sec: float = 0
    private_server_link: str = ""
    remote_bridge_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        if len(self.slots) != 10:
            raise ValueError("slots must contain exactly 10 strings")
        return {
            "roundWaitSeconds": self.round_wait_seconds, "clickDelayMs": self.click_delay_ms,
            "placeTowerDelayMs": self.place_tower_delay_ms,
            "afterPlaceClick": self.after_place_click,
            "afterPlaceClickX": self.after_place_click_x,
            "afterPlaceClickY": self.after_place_click_y, "maxRounds": self.max_rounds,
            "markerSize": self.marker_size, "numPlacements": self.num_placements,
            "slots": list(self.slots), "gameProcess": self.game_process, "holeX": self.hole_x,
            "holeY": self.hole_y, "holeW": self.hole_w, "holeH": self.hole_h,
            "fullscreenOpening": self.fullscreen_opening,
            "disconnectEnabled": self.disconnect_enabled, "disconnectX1": self.disconnect_x1,
            "disconnectY1": self.disconnect_y1, "disconnectX2": self.disconnect_x2,
            "disconnectY2": self.disconnect_y2, "disconnectText": self.disconnect_text,
            "disconnectReconnectX": self.disconnect_reconnect_x,
            "disconnectReconnectY": self.disconnect_reconnect_y,
            "disconnectIntervalSec": self.disconnect_interval_sec,
            "privateServerLink": self.private_server_link,
            "remoteBridgeEnabled": self.remote_bridge_enabled,
        }


@dataclass(frozen=True)
class ScreenPayload:
    name: str
    steps: tuple[StepPayload, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "steps": [step.to_dict() for step in self.steps]}


@dataclass(frozen=True)
class OptionPayload:
    name: str = ""
    x: float = 0
    y: float = 0
    available: bool = False
    priority: int = 0
    max_uses: int = 0
    det_x: float = 0
    det_y: float = 0
    det_end_x: float = 0
    det_end_y: float = 0
    det_text: str = ""
    det_invert: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "x": self.x, "y": self.y, "available": self.available,
            "priority": self.priority, "maxUses": self.max_uses, "detX": self.det_x,
            "detY": self.det_y, "detEndX": self.det_end_x, "detEndY": self.det_end_y,
            "detText": self.det_text, "detInvert": self.det_invert,
        }


def save_general_payload(**values: Any) -> dict[str, Any]:
    """Build the complete, typed "general settings" JSON object from snake-case values."""
    return GeneralPayload(**values).to_dict()


def save_preset_payload(
    *, name: str, screens: Iterable[ScreenPayload | Mapping[str, Any]],
    options: Iterable[OptionPayload | Mapping[str, Any]], default_map: str = "",
    back_x: float = 0, back_y: float = 0, fallback_screen: str = "",
) -> dict[str, Any]:
    option_values = [_payload_dict(item) for item in options]
    if len(option_values) != 3:
        raise ValueError("a preset save requires exactly three options")
    return {
        "name": name,
        "screens": [_payload_dict(item) for item in screens],
        "options": option_values,
        "defaultMap": default_map, "backX": back_x, "backY": back_y,
        "fallbackScreen": fallback_screen,
    }


def save_map_profile_payload(
    *, name: str, expected_text: str = "", custom_towers: bool = False,
    custom_num_placements: int = 0, placements: Iterable[Mapping[str, Any]] = (),
    custom_camera: bool = False,
) -> dict[str, Any]:
    placement_values = [dict(item) for item in placements]
    if len(placement_values) > 10:
        raise ValueError("a map profile save accepts at most ten placements")
    return {"name": name, "expectedText": expected_text, "customTowers": custom_towers,
            "customNumPlacements": custom_num_placements,
            "placements": placement_values, "customCamera": custom_camera}


def save_adv_map_steps_payload(
    *, map_profile_name: str, steps: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    return {"mapProfileName": map_profile_name, "steps": [dict(item) for item in steps]}


def name_payload(name: str) -> dict[str, Any]:
    return {"name": name}


def set_active_preset_payload(name: str) -> dict[str, Any]:
    return name_payload(name)


def start_payload(start_screen: str = "", start_step: int = 0, use_active: bool = True) -> dict[str, Any]:
    return {"startScreen": start_screen, "startStep": start_step, "useActive": use_active}


def start_capture_payload(field_id: str) -> dict[str, Any]:
    return {"fieldId": field_id}


def start_capture_region_payload(field_ids: list[str]) -> dict[str, Any]:
    if len(field_ids) != 4 or not all(isinstance(field_id, str) for field_id in field_ids):
        raise ValueError("START_CAPTURE_REGION requires exactly four strings")
    return {"fieldIds": field_ids}


def cancel_capture_payload() -> dict[str, Any]:
    return {}


def pause_payload() -> dict[str, Any]:
    return {}


def resume_payload() -> dict[str, Any]:
    return {}


def stop_payload() -> dict[str, Any]:
    return {}


def list_game_processes_payload() -> dict[str, Any]:
    return {}


def force_game_window_payload() -> dict[str, Any]:
    return {}


def show_region_preview_payload(x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]:
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def show_point_preview_payload(x: float, y: float) -> dict[str, Any]:
    return {"x": x, "y": y}


def ocr_test_payload(
    x1: float, y1: float, x2: float, y2: float, expected: str = "",
) -> dict[str, Any]:
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "expected": expected}


@dataclass(frozen=True)
class OcrTestResult:
    """What TEST_OCR's escalation ladder did, as reported by macro/local_bridge.ahk.

    The ladder re-scans the same screen pixels with a progressively larger border drawn around
    them, because Windows OCR often reads nothing at all from a rectangle cropped tight against
    its own glyphs.  ``detected`` is the ladder's own verdict, never re-derived from whether some
    other field happens to be non-empty; ``pad_pct`` and ``pad_color`` describe the rung that
    produced the match, i.e. how much border it took.  On a match ``stages_tried`` is that rung's
    own 1-based position, since the ladder stops at the rung that matched.
    """

    detected: bool = False
    text: str = ""
    pad_pct: int = 0
    pad_color: str = ""
    stages_tried: int = 0
    stages_total: int = 0
    capped: bool = False
    max_side: int = 0

    @classmethod
    def from_ack_data(cls, value: Mapping[str, Any]) -> "OcrTestResult":
        """Read an acknowledgement payload, accepting missing or future fields.

        AHK has no boolean type, so ``detected``/``capped`` arrive as the numbers 1 and 0 (see
        LocalBridgeAckValueJson in macro/local_bridge.ahk); ``_as_bool`` covers both those and a
        real JSON boolean from a test double.
        """
        return cls(
            detected=_as_bool(value.get("detected")),
            text=_as_str(value.get("text")),
            pad_pct=_as_int(value.get("padPct")),
            pad_color=_as_str(value.get("padColor")),
            stages_tried=_as_int(value.get("stagesTried")),
            stages_total=_as_int(value.get("stagesTotal")),
            capped=_as_bool(value.get("capped")),
            max_side=_as_int(value.get("maxSide")),
        )


def _ocr_framing_phrase(result: "OcrTestResult") -> str:
    """Name the framing that matched, in the user's terms rather than the engine's rung label.

    The rung's own position is part of the answer to "how far up the ladder did this go", so it is
    spelled out even for the raw capture, where the useful news is that no border was needed.
    """
    if result.pad_pct <= 0 or not result.pad_color:
        framing = "the raw capture, with no border added"
    else:
        framing = f"a {result.pad_color} border of {result.pad_pct}% per side"
    if result.stages_tried <= 0 or result.stages_total <= 0:
        return framing
    return f"{framing} (framing {result.stages_tried} of {result.stages_total})"


def _ocr_coverage_phrase(result: OcrTestResult) -> str:
    """Say how much of the ladder actually ran, so a failure is not mistaken for a full sweep."""
    if result.stages_total <= 0:
        return ""
    if result.capped:
        return (
            f" Only {result.stages_tried} of {result.stages_total} framings were tried: the wider "
            f"borders would push this region past the {result.max_side} px scan limit."
        )
    return f" All {result.stages_total} framings were tried."


def format_ocr_test_result(result: OcrTestResult, expected: str) -> str:
    """Render the one sentence both "Test OCR" buttons show.

    Lives here rather than in either window so the two cannot drift apart, and next to the wire
    type it reads, since every branch below depends on which fields the bridge actually sends.
    """
    if not expected:
        # No expected text to match, so the question is only whether the region reads at all.
        if result.detected:
            return (
                f'No expected text set. The region reads "{result.text}" from '
                f"{_ocr_framing_phrase(result)}."
            )
        return f"No expected text set, and the region read nothing.{_ocr_coverage_phrase(result)}"
    if result.detected:
        return (
            f'DETECTED: "{expected}" matched from '
            f'{_ocr_framing_phrase(result)}. Read: "{result.text}"'
        )
    if result.text:
        return (
            f'NOT DETECTED: "{expected}" was not found in any framing. '
            f'Best read: "{result.text}".{_ocr_coverage_phrase(result)}'
        )
    return f"NOT DETECTED: the region read nothing at all.{_ocr_coverage_phrase(result)}"


def pair_remote_agent_payload(
    agent_path: str, server_url: str, mode: str, email: str, credentials_file: str,
) -> dict[str, Any]:
    """Build the credential-file-only PAIR_REMOTE_AGENT bridge payload."""
    if mode not in {"login", "register"}:
        raise ValueError("mode must be 'login' or 'register'")
    return {
        "agentPath": agent_path,
        "serverUrl": server_url,
        "mode": mode,
        "email": email,
        "credentialsFile": credentials_file,
    }


def start_remote_agent_payload(agent_path: str) -> dict[str, Any]:
    return {"agentPath": agent_path}


def stop_remote_agent_payload(agent_path: str) -> dict[str, Any]:
    return {"agentPath": agent_path}


def dumps_payload(payload: Mapping[str, Any]) -> str:
    """Compact, one-line JSON used in local_cmd.txt."""
    return json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def parse_ack_line(line: str) -> tuple[str, dict[str, Any]]:
    """Parse ``<token>|<json>``, splitting once because JSON strings may contain ``|``."""
    token, separator, json_text = line.rstrip("\r\n").partition("|")
    if not separator or not token:
        raise ValueError("ack line must be '<token>|<json>'")
    value = json.loads(json_text)
    if not isinstance(value, dict):
        raise ValueError("ack JSON must be an object")
    return token, value


def parse_game_process_candidates(value: Any) -> list[GameProcessCandidate]:
    if not isinstance(value, Mapping):
        return []
    processes = value.get("processes")
    if not isinstance(processes, list):
        return []
    return [
        GameProcessCandidate.from_json_dict(candidate)
        for candidate in processes
        if isinstance(candidate, Mapping)
    ]


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return asdict(value)


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        try:
            result[str(key)] = int(item)
        except (TypeError, ValueError):
            continue
    return result


def _as_float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
