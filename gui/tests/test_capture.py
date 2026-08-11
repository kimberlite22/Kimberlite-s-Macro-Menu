from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app import capture as capture_module
from app.capture import CaptureUnavailableError, capture_point, capture_region
from ipc.protocol import CaptureResult, VERB_CANCEL_CAPTURE, VERB_START_CAPTURE, VERB_START_CAPTURE_REGION


@pytest.fixture(autouse=True)
def _engine_in_this_session(monkeypatch) -> None:
    """Keep every capture test independent of the machine's real Windows session layout.

    Without this the guard added for background sessions would run the real tasklist.exe scrape,
    so these tests would start failing on any machine that happens to have an engine running in
    another session, which is exactly the setup this feature exists for.
    """
    monkeypatch.setattr(capture_module, "engine_is_in_current_session", lambda: True)


@dataclass
class _Ack:
    ok: bool = True


class _Client:
    def __init__(self, results: list[CaptureResult | None]) -> None:
        self.results = deque(results)
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.read_consumes: list[bool] = []

    def send_command(self, verb: str, payload: dict[str, Any]) -> _Ack:
        self.sent.append((verb, payload))
        return _Ack()

    def read_capture_result(self, consume: bool = False) -> CaptureResult | None:
        self.read_consumes.append(consume)
        return self.results.popleft() if self.results else None


class _Window:
    def __init__(self) -> None:
        self.hide_count = 0
        self.show_count = 0

    def hide(self) -> None:
        self.hide_count += 1

    def show(self) -> None:
        self.show_count += 1


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration


def test_point_capture_polls_until_matching_result_and_restores_window(qapp) -> None:
    client = _Client([None, None, CaptureResult(mode="point", field_id="point-id", x=12.5, y=34.25)])
    window = _Window()
    clock = _Clock()

    result = capture_point(
        client, window, timeout=1, poll_interval=0.1, clock=clock, sleep=clock.sleep,
        field_id_factory=lambda: "point-id",
    )

    assert result == (12.5, 34.25)
    assert client.sent == [(VERB_START_CAPTURE, {"fieldId": "point-id"})]
    # Non-matching polls only peek (consume=False); the matching poll peeks once, confirms the
    # match, then makes a second, consuming read to actually remove the result from disk.
    assert client.read_consumes == [False, False, False, True]
    assert (window.hide_count, window.show_count) == (1, 1)


def test_cancelled_point_capture_leaves_window_restored(qapp) -> None:
    client = _Client([CaptureResult(mode="point", field_id="point-id", cancelled=True)])
    window = _Window()
    clock = _Clock()

    assert capture_point(
        client, window, timeout=1, clock=clock, sleep=clock.sleep,
        field_id_factory=lambda: "point-id",
    ) is None
    assert (window.hide_count, window.show_count) == (1, 1)


def test_unresolved_capture_times_out_without_real_wait(qapp) -> None:
    client = _Client([])
    window = _Window()
    clock = _Clock()

    assert capture_point(
        client, window, timeout=0.25, poll_interval=0.1, clock=clock, sleep=clock.sleep,
        field_id_factory=lambda: "point-id",
    ) is None
    assert (window.hide_count, window.show_count) == (1, 1)
    # Regression test: a timeout used to just re-show the Python window and leave AHK's own
    # marker/overlay waiting forever - CANCEL_CAPTURE must be sent so AHK stops waiting too.
    assert client.sent[-1][0] == VERB_CANCEL_CAPTURE
    assert len(client.read_consumes) == 3


class _FileLikeClient:
    """Mimics a real result file: a peek (consume=False) never removes the current value."""

    def __init__(self, value: CaptureResult | None) -> None:
        self._current = value
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.read_consumes: list[bool] = []

    def send_command(self, verb: str, payload: dict[str, Any]) -> _Ack:
        self.sent.append((verb, payload))
        return _Ack()

    def read_capture_result(self, consume: bool = False) -> CaptureResult | None:
        self.read_consumes.append(consume)
        value = self._current
        if consume:
            self._current = None
        return value


def test_mismatched_result_is_not_consumed_while_waiting(qapp) -> None:
    # Regression test: a stale or concurrently-arriving result for a DIFFERENT field id must be
    # left on disk, not deleted just because it happened to be read while polling for our own -
    # deleting it would starve whichever request it actually belonged to.
    client = _FileLikeClient(CaptureResult(mode="point", field_id="someone-elses-id", x=1.0, y=2.0))
    window = _Window()
    clock = _Clock()

    assert capture_point(
        client, window, timeout=0.25, poll_interval=0.1, clock=clock, sleep=clock.sleep,
        field_id_factory=lambda: "point-id",
    ) is None
    # Every read was a non-consuming peek; the mismatched result is still sitting there, untouched.
    assert all(consume is False for consume in client.read_consumes)
    assert client._current is not None


def test_region_capture_matches_all_four_field_ids(qapp) -> None:
    ids = iter(["x1", "y1", "x2", "y2"])
    client = _Client([
        CaptureResult(
            mode="region", field_ids=("x1", "y1", "x2", "y2"),
            x1=1.0, y1=2.0, x2=3.0, y2=4.0,
        ),
    ])
    window = _Window()
    clock = _Clock()

    result = capture_region(
        client, window, timeout=1, clock=clock, sleep=clock.sleep,
        field_id_factory=lambda: next(ids),
    )

    assert result == (1.0, 2.0, 3.0, 4.0)
    assert client.sent == [(VERB_START_CAPTURE_REGION, {"fieldIds": ["x1", "y1", "x2", "y2"]})]
    assert (window.hide_count, window.show_count) == (1, 1)


@dataclass
class _VisibilityResult:
    ok: bool
    message: str = ""


def test_capture_brings_the_background_session_up_and_then_proceeds(qapp) -> None:
    # The overlay opens on the background session's desktop, so that desktop is put in front of the
    # user instead of the capture being refused: the click is made inside the session's own window.
    client = _Client([CaptureResult(mode="point", field_id="point-id", x=5.0, y=6.0)])
    window = _Window()
    clock = _Clock()
    calls: list[str] = []

    def make_visible() -> _VisibilityResult:
        calls.append("shown")
        return _VisibilityResult(True)

    result = capture_point(
        client, window, timeout=1, poll_interval=0.1, clock=clock, sleep=clock.sleep,
        field_id_factory=lambda: "point-id",
        session_check=lambda: False,
        make_visible=make_visible,
    )

    assert result == (5.0, 6.0)
    assert calls == ["shown"]
    # The session is brought up BEFORE the bridge is told to open an overlay, so the crosshair is
    # never left waiting on a desktop that is still hidden.
    assert client.sent[0][0] == VERB_START_CAPTURE


def test_capture_refuses_when_the_background_session_cannot_be_brought_up(qapp) -> None:
    client = _Client([])
    window = _Window()
    unavailable = lambda: _VisibilityResult(False, "No background session is currently running.")

    with pytest.raises(CaptureUnavailableError) as point_error:
        capture_point(client, window, session_check=lambda: False, make_visible=unavailable)
    with pytest.raises(CaptureUnavailableError):
        capture_region(client, window, session_check=lambda: False, make_visible=unavailable)

    # Nothing may reach the bridge. Failing here is the whole point: an overlay opened on a desktop
    # nobody can click would hold the bridge "busy" for the full 120 second timeout, and the window
    # must not be hidden for a capture that never started.
    assert client.sent == []
    assert window.hide_count == 0
    # The reason the session could not be shown is carried through, not swallowed: it is the only
    # thing that tells the user which of several situations they are in.
    assert "No background session is currently running." in str(point_error.value)


def test_a_second_capture_started_from_inside_the_first_is_refused(qapp) -> None:
    # Both flows pump Qt events, so the button that started a capture stays clickable throughout.
    # Without the guard, a second click during the background session's reconnect would launch a
    # competing Remote Desktop client, and during the wait it would send a second overlay command.
    client = _Client([])
    window = _Window()
    clock = _Clock()
    second: list[Exception] = []

    def make_visible() -> _VisibilityResult:
        try:
            capture_point(client, window, session_check=lambda: True)
        except Exception as error:  # noqa: BLE001 - the type is what the assertion checks
            second.append(error)
        return _VisibilityResult(True)

    capture_point(
        client, window, timeout=0.2, poll_interval=0.1, clock=clock, sleep=clock.sleep,
        field_id_factory=lambda: "point-id", session_check=lambda: False,
        make_visible=make_visible,
    )

    assert len(second) == 1
    assert isinstance(second[0], CaptureUnavailableError)
    # The flag is released again, so the refusal costs the user only that one click.
    assert capture_module._capture_in_progress is False


def test_the_session_is_looked_for_in_the_data_directory_this_launch_uses(monkeypatch) -> None:
    # Not launcher_paths.data_dir(): a launch started with --dir keeps its session marker in that
    # directory, and looking anywhere else would report "no background session" for a live one.
    client = _Client([])
    client.data_dir = Path("D:/somewhere/else")
    seen: list[Path] = []
    monkeypatch.setattr(
        capture_module,
        "ensure_background_session_visible",
        lambda directory, **_kwargs: seen.append(directory) or _VisibilityResult(True),
    )

    capture_module._show_background_session(client)

    assert seen == [Path("D:/somewhere/else")]


def test_capture_proceeds_when_the_session_cannot_be_determined(qapp) -> None:
    client = _Client([CaptureResult(mode="point", field_id="point-id", x=1.0, y=2.0)])
    window = _Window()
    clock = _Clock()

    # None means "cannot tell", which has to stay non-blocking: this guard may never become a new
    # way for capture to fail on an ordinary single-session machine.
    result = capture_point(
        client, window, timeout=1, poll_interval=0.1, clock=clock, sleep=clock.sleep,
        field_id_factory=lambda: "point-id", session_check=lambda: None,
    )

    assert result == (1.0, 2.0)
    assert client.sent[0][0] == VERB_START_CAPTURE
