"""Wire types and payload builders for the local AHK GUI bridge.

The bridge owns the exact file format.  This module keeps Python call sites from
hand-assembling loosely structured dictionaries as the protocol grows.
"""

from __future__ import annotations

import json
import math
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
VERB_RUN_CAMERA_ACTION = "RUN_CAMERA_ACTION"
VERB_SHOW_REGION_PREVIEW = "SHOW_REGION_PREVIEW"
VERB_SHOW_POINT_PREVIEW = "SHOW_POINT_PREVIEW"
VERB_TEST_OCR = "TEST_OCR"
VERB_SAVE_OCR_SAMPLE = "SAVE_OCR_SAMPLE"
VERB_SET_OCR_SAMPLE = "SET_OCR_SAMPLE"
VERB_GET_OCR_SAMPLE = "GET_OCR_SAMPLE"
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
    ocr_match_threshold: float = 0.75
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
            "ocrMatchThreshold": self.ocr_match_threshold,
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


def run_camera_action_payload(map_profile: str) -> dict[str, Any]:
    return {"mapProfile": map_profile}


def show_region_preview_payload(x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]:
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def show_point_preview_payload(x: float, y: float) -> dict[str, Any]:
    return {"x": x, "y": y}


# What a Test OCR press compares the region against. The engine resolves "maps" itself from the
# live map profile list, so the two cannot disagree about which profiles exist; "outcomes" travels
# in `candidates` because those names are being edited in the GUI and may not be saved yet.
OCR_TEST_SOURCE_TEXT = "text"
OCR_TEST_SOURCE_MAPS = "maps"
OCR_TEST_SOURCE_OUTCOMES = "outcomes"


def ocr_test_payload(
    x1: float, y1: float, x2: float, y2: float, expected: str = "",
    source: str = OCR_TEST_SOURCE_TEXT, candidates: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "x1": x1, "y1": y1, "x2": x2, "y2": y2, "expected": expected,
        "source": source, "candidates": list(candidates or []),
    }


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
    # How well the read matched the expected text (0..1), and the score it had to reach. Sent on a
    # miss too, as the best any framing managed, which is what separates "the region is showing
    # something else entirely" (near 0) from "the right text, read badly" (just under threshold).
    score: float = 0.0
    threshold: float = 0.0
    max_side: int = 0
    # How many things the read was compared against, and which one won. For a single expected text
    # the label is that text again, but a "Detect Map" step is scored against every map profile and
    # an Advanced Detection against every outcome, where naming the winner ("Kings Tomb") is the
    # entire answer. On a miss the label is the closest candidate, so the user knows what to adjust.
    #
    # -1 means the bridge did not report a count at all, which is what an engine build older than
    # this field looks like. It has to stay distinct from a real 0: reading "absent" as "zero"
    # would tell the user no map profiles are configured when the truth is that this engine cannot
    # say, and that message would send them off to fix a setting that is not broken.
    candidate_count: int = -1
    candidate_label: str = ""

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
            score=_as_float_or_none(value.get("score")) or 0.0,
            threshold=_as_float_or_none(value.get("threshold")) or 0.0,
            candidate_count=_as_int(value.get("candidateCount"), -1),
            candidate_label=_as_str(value.get("candidateLabel")),
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


def ocr_score_percent(score: float) -> int:
    """One 0..1 OCR score or threshold as the whole percent the user is shown.

    Public because the General tab's threshold field renders the same number: the field and the
    score reported by the log and the Test OCR result are meant to be compared directly, so a
    second copy of this conversion is exactly how the two would end up one percent apart.

    Rounds half AWAY FROM ZERO to agree with the engine, whose OcrMatchNote/OcrMissNote in
    macro/ocr_matching.ahk render the same numbers through AHK's Round(). Python's own round() is
    half-to-EVEN and would put 0.985 at 98 where AHK gives 99.
    """
    return math.floor(score * 100 + 0.5)


def _ocr_score_body(result: OcrTestResult) -> str:
    """The score wording without punctuation around it, so callers can compose their own sentence.

    A near-threshold percentage means the region and the expected text are right and only the read
    was poor; a percentage near zero means the region is showing something else. Empty when the
    bridge sent no threshold, which is what an older engine build looks like.
    """
    if result.threshold <= 0:
        return ""
    return (
        f"score {ocr_score_percent(result.score)}%, "
        f"needs {ocr_score_percent(result.threshold)}%"
    )


def _ocr_score_phrase(result: OcrTestResult) -> str:
    """State how well the read matched, since "not found" alone does not say how close it came."""
    body = _ocr_score_body(result)
    return f" ({body})" if body else ""


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


def _format_ocr_multi_candidate_result(result: OcrTestResult, kind: str) -> str:
    """Word the verdict for a step matched against a SET of candidates, not one expected text.

    A "Detect Map" step is scored against every map profile and an Advanced Detection against every
    outcome, so "detected" is only half the answer: which one won is the other half, and on a miss
    the closest one is what tells the user which expected text to adjust.
    """
    plural = f"{kind}s"
    coverage = _ocr_coverage_phrase(result)
    if result.candidate_count == 0:
        # Nothing to compare against. Saying "not detected" here would blame the region for a
        # configuration gap that has nothing to do with it. Only an engine that actually reported
        # a count of zero reaches this: see OcrTestResult.candidate_count on why -1 must not.
        if result.text:
            return (
                f'No {plural} with an expected text are configured, so nothing could match. '
                f'The region reads "{result.text}".'
            )
        return f"No {plural} with an expected text are configured, and the region read nothing."
    if result.detected:
        return (
            f'DETECTED: {kind} "{result.candidate_label}" matched from '
            f'{_ocr_framing_phrase(result)}{_ocr_score_phrase(result)}. Read: "{result.text}"'
        )
    if not result.text:
        return f"NOT DETECTED: the region read nothing at all.{coverage}"
    score_body = _ocr_score_body(result)
    if result.candidate_count == 1 and result.candidate_label:
        detail = f" ({score_body})" if score_body else ""
        return (
            f'NOT DETECTED: the only {kind}, "{result.candidate_label}", did not match{detail}. '
            f'Best read: "{result.text}".{coverage}'
        )
    closest = f'closest {kind} "{result.candidate_label}"' if result.candidate_label else ""
    detail = ", ".join(part for part in (closest, score_body) if part)
    detail = f" ({detail})" if detail else ""
    # An engine that reported no count (-1) still gets a truthful sentence, just without the
    # number: "none of the -1 map profiles" would be nonsense.
    subject = f"none of the {result.candidate_count} {plural}" if result.candidate_count > 0 else f"no {kind}"
    return (
        f'NOT DETECTED: {subject} matched{detail}. '
        f'Best read: "{result.text}".{coverage}'
    )


def format_ocr_test_result(result: OcrTestResult, expected: str, candidate_kind: str = "") -> str:
    """Render the one sentence every "Test OCR" button shows.

    Lives here rather than in any window so they cannot drift apart, and next to the wire type it
    reads, since every branch below depends on which fields the bridge actually sends.

    ``candidate_kind`` names what the region was compared against when that is a set rather than a
    single expected text ("map profile", "outcome"); empty for the ordinary one-text case.
    """
    if candidate_kind:
        return _format_ocr_multi_candidate_result(result, candidate_kind)
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
            f'{_ocr_framing_phrase(result)}{_ocr_score_phrase(result)}. Read: "{result.text}"'
        )
    if result.text:
        return (
            f'NOT DETECTED: "{expected}" was not found in any framing'
            f'{_ocr_score_phrase(result)}. '
            f'Best read: "{result.text}".{_ocr_coverage_phrase(result)}'
        )
    return f"NOT DETECTED: the region read nothing at all.{_ocr_coverage_phrase(result)}"


def save_ocr_sample_payload(
    x1: float, y1: float, x2: float, y2: float, expected: str = "",
) -> dict[str, Any]:
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "expected": expected}


def set_ocr_sample_payload(expected: str, source: str) -> dict[str, Any]:
    return {"expected": expected, "source": source}


def get_ocr_sample_payload(expected: str) -> dict[str, Any]:
    return {"expected": expected}


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
