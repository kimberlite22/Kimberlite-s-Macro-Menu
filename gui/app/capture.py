"""Synchronous, Qt-safe client flows for AHK-owned F7/F8 capture overlays."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from PySide6.QtWidgets import QApplication

from app.engine_process import engine_is_in_current_session
from ipc.protocol import (
    CaptureResult,
    VERB_CANCEL_CAPTURE,
    VERB_START_CAPTURE,
    VERB_START_CAPTURE_REGION,
    cancel_capture_payload,
    start_capture_payload,
    start_capture_region_payload,
)


# A user can alt-tab away and never press F8/Escape, so this bounds an otherwise open-ended wait.
CAPTURE_TIMEOUT_SECONDS = 120.0
CAPTURE_POLL_INTERVAL_SECONDS = 0.125


class CaptureUnavailableError(RuntimeError):
    """Raised when a capture cannot possibly succeed from the session this GUI runs in."""


def _require_reachable_overlay(session_check: Callable[[], bool | None] | None) -> None:
    """Refuse a capture whose overlay would open on a desktop the user cannot reach.

    The overlay is drawn by the ENGINE, on the desktop of whichever Windows session the engine
    runs in. Once that is a background RDP session it is not the desktop this window is on, so
    the crosshair would sit there waiting for a click nobody can make until the 120 second
    timeout expires. Failing immediately, with a message naming the reason, beats two silent
    minutes.

    Only an explicit False blocks. None means the session could not be determined, or that no
    engine is running at all, and both have to stay non-blocking: this guard may never become a
    new way for capture to fail on an ordinary single-session machine.
    """
    # Resolved here rather than as a default argument value, which would bind the function object
    # once at import time and make the module attribute impossible to substitute afterwards. Same
    # shape as ``field_id_factory`` below.
    check = session_check or engine_is_in_current_session
    if check() is False:
        raise CaptureUnavailableError(
            "the engine runs in a background session, so the capture overlay would open on a "
            "desktop this window cannot reach. Open that session and capture there."
        )


class CaptureIpcClient(Protocol):
    """The minimal local bridge surface required by capture clients."""

    def send_command(self, verb: str, payload: dict[str, Any]) -> Any: ...

    def read_capture_result(self, consume: bool = False) -> CaptureResult | None: ...


class CaptureWindow(Protocol):
    """Only the visibility controls needed while AHK owns the overlay."""

    def hide(self) -> None: ...

    def show(self) -> None: ...


def capture_point(
    client: CaptureIpcClient,
    window: CaptureWindow,
    *,
    timeout: float = CAPTURE_TIMEOUT_SECONDS,
    poll_interval: float = CAPTURE_POLL_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    field_id_factory: Callable[[], str] | None = None,
    session_check: Callable[[], bool | None] | None = None,
) -> tuple[float, float] | None:
    """Request one F8 point capture, returning ``None`` when it is cancelled or times out."""
    _require_reachable_overlay(session_check)
    make_field_id = field_id_factory or _new_field_id
    field_id = make_field_id()
    ack = client.send_command(VERB_START_CAPTURE, start_capture_payload(field_id))
    if not getattr(ack, "ok", True):
        return None

    result = _wait_for_result(
        client, window, lambda item: item.mode == "point" and item.field_id == field_id,
        timeout=timeout, poll_interval=poll_interval, clock=clock, sleep=sleep,
    )
    if result is None or result.cancelled or result.x is None or result.y is None:
        return None
    return result.x, result.y


def capture_region(
    client: CaptureIpcClient,
    window: CaptureWindow,
    *,
    timeout: float = CAPTURE_TIMEOUT_SECONDS,
    poll_interval: float = CAPTURE_POLL_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    field_id_factory: Callable[[], str] | None = None,
    session_check: Callable[[], bool | None] | None = None,
) -> tuple[float, float, float, float] | None:
    """Request a two-corner region capture, returning ``None`` when it is not completed."""
    _require_reachable_overlay(session_check)
    make_field_id = field_id_factory or _new_field_id
    field_ids = [make_field_id() for _ in range(4)]
    ack = client.send_command(VERB_START_CAPTURE_REGION, start_capture_region_payload(field_ids))
    if not getattr(ack, "ok", True):
        return None

    expected_ids = tuple(field_ids)
    result = _wait_for_result(
        client, window, lambda item: item.mode == "region" and item.field_ids == expected_ids,
        timeout=timeout, poll_interval=poll_interval, clock=clock, sleep=sleep,
    )
    if result is None or result.cancelled or None in (result.x1, result.y1, result.x2, result.y2):
        return None
    return float(result.x1), float(result.y1), float(result.x2), float(result.y2)


def _wait_for_result(
    client: CaptureIpcClient,
    window: CaptureWindow,
    matches: Callable[[CaptureResult], bool],
    *,
    timeout: float,
    poll_interval: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> CaptureResult | None:
    """Keep Qt responsive while waiting for AHK's separately published capture result."""
    window.hide()
    deadline = clock() + timeout
    matched = False
    try:
        while clock() < deadline:
            # Other local IPC calls are synchronous from their caller's perspective. Keeping that
            # model with processEvents is simpler and more consistent than introducing the app's
            # only QTimer/callback capture flow, while still letting the hide take effect.
            QApplication.processEvents()
            # Peek first: consuming unconditionally would permanently delete a result that doesn't
            # match this wait (e.g. a stale leftover, or another in-flight request's own answer),
            # starving whoever it actually belonged to. Only consume once it's confirmed as ours.
            result = client.read_capture_result(consume=False)
            if result is not None and matches(result):
                matched = True
                return client.read_capture_result(consume=True) or result
            sleep(min(poll_interval, max(0.0, deadline - clock())))
    finally:
        if not matched:
            # We are giving up (timed out, or Escape already resolved AHK's own side with a
            # "cancelled" result we never happened to read) - tell AHK to stop waiting too, or its
            # marker/region overlay would otherwise stay open indefinitely with nobody watching,
            # and a later capture attempt would find the bridge still "busy" from this one.
            try:
                client.send_command(VERB_CANCEL_CAPTURE, cancel_capture_payload())
            except Exception:
                pass
        window.show()
    return None


def _new_field_id() -> str:
    return uuid.uuid4().hex
