"""Synchronous, Qt-safe client flows for AHK-owned F7/F8 capture overlays."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from PySide6.QtWidgets import QApplication

from ipc.protocol import (
    CaptureResult,
    VERB_START_CAPTURE,
    VERB_START_CAPTURE_REGION,
    start_capture_payload,
    start_capture_region_payload,
)


# A user can alt-tab away and never press F8/Escape, so this bounds an otherwise open-ended wait.
CAPTURE_TIMEOUT_SECONDS = 120.0
CAPTURE_POLL_INTERVAL_SECONDS = 0.125


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
) -> tuple[float, float] | None:
    """Request one F8 point capture, returning ``None`` when it is cancelled or times out."""
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
) -> tuple[float, float, float, float] | None:
    """Request a two-corner region capture, returning ``None`` when it is not completed."""
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
                return client.read_capture_result(consume=True) or result
            sleep(min(poll_interval, max(0.0, deadline - clock())))
    finally:
        window.show()
    return None


def _new_field_id() -> str:
    return uuid.uuid4().hex
