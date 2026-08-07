from __future__ import annotations

import ctypes
import threading
from pathlib import Path

from app import window_branding


class _FakeUser32:
    """Stands in for user32, modelling each window's title and its two icon slots.

    Both icon sizes are tracked separately because apply_branding checks both: a window carrying
    our big icon but somebody else's small one is not branded, and the taskbar shows the small one.
    """

    def __init__(
        self, titles: dict[int, str], icons: dict[tuple[int, int], int] | None = None
    ) -> None:
        self.titles = titles
        # Keyed by (hwnd, ICON_SMALL/ICON_BIG), matching WM_GETICON/WM_SETICON's own wParam.
        self.icons = icons or {}
        self.set_titles: list[tuple[int, str]] = []
        self.icon_messages: list[tuple[int, int, int, int]] = []
        self.message_calls: list[tuple[int, int, int, int]] = []
        self.load_image_calls: list[tuple[object, str, int, int, int, int]] = []
        self.timeout_messages: set[tuple[int, int]] = set()

    def GetWindowTextLengthW(self, hwnd: int) -> int:
        return len(self.titles[hwnd])

    def GetWindowTextW(self, hwnd: int, buffer, _length: int) -> int:
        buffer.value = self.titles[hwnd]
        return len(buffer.value)

    def SendMessageTimeoutW(
        self, hwnd: int, message: int, wparam: int, lparam: int, _flags: int, _timeout: int, result
    ) -> int:
        self.message_calls.append((hwnd, message, wparam, lparam))
        if (hwnd, message) in self.timeout_messages:
            return 0
        if message == window_branding.WM_GETICON:
            result._obj.value = self.icons.get((hwnd, wparam), 0)
            return 1
        if message == window_branding.WM_SETTEXT:
            title = ctypes.wstring_at(lparam)
            self.titles[hwnd] = title
            self.set_titles.append((hwnd, title))
            result._obj.value = 1
            return 1
        if message == window_branding.WM_SETICON:
            self.icon_messages.append((hwnd, message, wparam, lparam))
            self.icons[(hwnd, wparam)] = lparam
            result._obj.value = 0
            return 1
        return 0

    def LoadImageW(
        self, instance: object, path: str, image_type: int, width: int, height: int, flags: int
    ) -> int:
        self.load_image_calls.append((instance, path, image_type, width, height, flags))
        return 100 + len(self.load_image_calls)

    def GetSystemMetrics(self, metric: int) -> int:
        return metric


def _icon_path(tmp_path: Path) -> Path:
    path = tmp_path / "app.ico"
    path.touch()
    return path


def _branded(user32: _FakeUser32, hwnd: int) -> list[tuple[int, int, int, int]]:
    return [message for message in user32.icon_messages if message[0] == hwnd]


def test_apply_branding_leaves_already_branded_windows_alone(monkeypatch, tmp_path: Path) -> None:
    """Window 10 already carries our title and both our icons; window 11 carries none of it."""
    title = "Kimberlite's Macro Menu - Background Session"
    user32 = _FakeUser32(
        {10: title, 11: "Connecting"},
        {
            (10, window_branding.ICON_SMALL): 101,
            (10, window_branding.ICON_BIG): 102,
            (11, window_branding.ICON_BIG): 999,
        },
    )
    icon = _icon_path(tmp_path)
    monkeypatch.setattr(window_branding, "_user32", lambda: user32)
    monkeypatch.setattr(window_branding, "top_level_windows_for_process", lambda _pid: [10, 11])
    monkeypatch.setattr(window_branding, "_icon_handles", None)

    assert window_branding.apply_branding(123, title, icon)
    assert user32.set_titles == [(11, title)]
    assert _branded(user32, 10) == []
    assert _branded(user32, 11) == [
        (11, window_branding.WM_SETICON, window_branding.ICON_SMALL, 101),
        (11, window_branding.WM_SETICON, window_branding.ICON_BIG, 102),
    ]

    # Everything now matches, so a second pass of the caller's bounded retry is a no-op. The icons
    # are also loaded once for the process, not once per pass.
    assert window_branding.apply_branding(123, title, icon)
    assert user32.set_titles == [(11, title)]
    assert len(user32.icon_messages) == 2
    assert len(user32.load_image_calls) == 2


def test_apply_branding_applies_title_without_an_icon(monkeypatch) -> None:
    user32 = _FakeUser32({10: "Connecting"})
    monkeypatch.setattr(window_branding, "_user32", lambda: user32)
    monkeypatch.setattr(window_branding, "top_level_windows_for_process", lambda _pid: [10])
    monkeypatch.setattr(window_branding, "_icon_handles", None)

    assert window_branding.apply_branding(123, "Branded", None)
    assert user32.set_titles == [(10, "Branded")]
    assert user32.icon_messages == []


def test_apply_branding_reasserts_icon_when_big_icon_is_not_ours(
    monkeypatch, tmp_path: Path
) -> None:
    user32 = _FakeUser32(
        {10: "Branded"},
        {(10, window_branding.ICON_SMALL): 101, (10, window_branding.ICON_BIG): 999},
    )
    monkeypatch.setattr(window_branding, "_user32", lambda: user32)
    monkeypatch.setattr(window_branding, "top_level_windows_for_process", lambda _pid: [10])
    monkeypatch.setattr(window_branding, "_icon_handles", None)

    assert window_branding.apply_branding(123, "Branded", _icon_path(tmp_path))
    assert user32.icon_messages == [
        (10, window_branding.WM_SETICON, window_branding.ICON_SMALL, 101),
        (10, window_branding.WM_SETICON, window_branding.ICON_BIG, 102),
    ]


def test_apply_branding_reasserts_icon_when_only_the_small_icon_is_not_ours(
    monkeypatch, tmp_path: Path
) -> None:
    """The big icon alone is not proof of branding: the taskbar shows the small one."""
    user32 = _FakeUser32(
        {10: "Branded"},
        {(10, window_branding.ICON_BIG): 102, (10, window_branding.ICON_SMALL): 999},
    )
    monkeypatch.setattr(window_branding, "_user32", lambda: user32)
    monkeypatch.setattr(window_branding, "top_level_windows_for_process", lambda _pid: [10])
    monkeypatch.setattr(window_branding, "_icon_handles", None)

    assert window_branding.apply_branding(123, "Branded", _icon_path(tmp_path))
    assert user32.icon_messages == [
        (10, window_branding.WM_SETICON, window_branding.ICON_SMALL, 101),
        (10, window_branding.WM_SETICON, window_branding.ICON_BIG, 102),
    ]


def test_timed_out_message_does_not_raise(monkeypatch) -> None:
    user32 = _FakeUser32({10: "Connecting"})
    user32.timeout_messages.add((10, window_branding.WM_SETTEXT))
    monkeypatch.setattr(window_branding, "_user32", lambda: user32)
    monkeypatch.setattr(window_branding, "top_level_windows_for_process", lambda _pid: [10])
    monkeypatch.setattr(window_branding, "_icon_handles", None)

    assert window_branding.apply_branding(123, "Branded", None) is False


def test_apply_branding_returns_false_when_no_window_matches(monkeypatch, tmp_path: Path) -> None:
    user32 = _FakeUser32({})
    monkeypatch.setattr(window_branding, "_user32", lambda: user32)
    monkeypatch.setattr(window_branding, "top_level_windows_for_process", lambda _pid: [])
    monkeypatch.setattr(window_branding, "_icon_handles", None)

    assert window_branding.apply_branding(123, "Anything", _icon_path(tmp_path)) is False
    assert user32.load_image_calls == []


def test_apply_branding_never_raises_when_user32_is_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(window_branding, "_user32", lambda: None)
    monkeypatch.setattr(window_branding, "top_level_windows_for_process", lambda _pid: [10])

    assert window_branding.apply_branding(123, "Anything", _icon_path(tmp_path)) is False


def test_run_branding_loop_returns_without_work_when_already_cancelled(monkeypatch) -> None:
    cancel = threading.Event()
    cancel.set()
    branding = []
    sleeps = []
    monkeypatch.setattr(window_branding, "apply_branding", lambda *_: branding.append(True))

    window_branding.run_branding_loop(
        123, "Branded", None, cancel, attempts=3, sleep=sleeps.append
    )

    assert branding == []
    assert sleeps == []


def test_run_branding_loop_uses_every_attempt_without_sleeping_after_the_last(monkeypatch) -> None:
    branding = []
    sleeps = []
    monkeypatch.setattr(window_branding, "apply_branding", lambda *args: branding.append(args))

    window_branding.run_branding_loop(
        123, "Branded", None, threading.Event(), attempts=3, interval=0.25, sleep=sleeps.append
    )

    assert branding == [(123, "Branded", None)] * 3
    assert sleeps == [0.25, 0.25]


def test_run_branding_loop_stops_without_sleeping_after_cancellation(monkeypatch) -> None:
    cancel = threading.Event()
    branding = []
    sleeps = []

    def apply(*_args) -> None:
        branding.append(True)
        cancel.set()

    monkeypatch.setattr(window_branding, "apply_branding", apply)

    window_branding.run_branding_loop(123, "Branded", None, cancel, attempts=3, sleep=sleeps.append)

    assert branding == [True]
    assert sleeps == []


def test_run_branding_loop_quietly_stops_when_branding_raises(monkeypatch) -> None:
    sleeps = []

    def raise_error(*_args) -> None:
        raise RuntimeError("brand failure")

    monkeypatch.setattr(window_branding, "apply_branding", raise_error)

    window_branding.run_branding_loop(
        123, "Branded", None, threading.Event(), attempts=3, sleep=sleeps.append
    )

    assert sleeps == []
