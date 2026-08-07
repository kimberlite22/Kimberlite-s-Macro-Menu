from __future__ import annotations

import socket
from unittest.mock import MagicMock

import pytest

from app import roblox_launch
from app.roblox_launch import PrivateServer


PRIVATE_SERVER_LINK = (
    "https://www.roblox.com/games/12345/Anime-Expedition?privateServerLinkCode=abc123DEF"
)
SHARE_LINK = "https://www.roblox.com/share?code=shareCode1&type=Server"


class _RecordingThread:
    """Runs the worker inline, so a test sees what the launch actually did."""

    instances: list["_RecordingThread"] = []

    def __init__(self, *, target, args=(), kwargs=None, daemon=False) -> None:
        self.target = target
        self.args = args
        self.kwargs = dict(kwargs or {})
        self.daemon = daemon
        self.started = False
        _RecordingThread.instances.append(self)

    def start(self) -> None:
        self.started = True
        self.target(*self.args, **self.kwargs)


# ---------------------------------------------------------------------------------------------
# Turning a link into something the Roblox client understands, without a browser
# ---------------------------------------------------------------------------------------------


def test_a_private_server_link_carries_both_halves_and_needs_no_network() -> None:
    """The place id is in the path and the link code in the query, so nothing has to be asked."""
    server = roblox_launch.private_server_from_link(PRIVATE_SERVER_LINK)

    assert server == PrivateServer("12345", "abc123DEF")
    assert server.deep_link() == "roblox://experiences/start?placeId=12345&linkCode=abc123DEF"


def test_a_share_link_has_no_place_id_to_read() -> None:
    assert roblox_launch.private_server_from_link(SHARE_LINK) is None
    assert roblox_launch.share_link_code(SHARE_LINK) == "shareCode1"


def test_a_link_that_is_not_a_roblox_link_never_becomes_a_deep_link() -> None:
    """The result is handed to the shell, so the validator gates this the same way it gates a URL."""
    assert roblox_launch.private_server_from_link("file:///C:/Windows/System32/calc.exe") is None
    assert roblox_launch.share_link_code("https://evil.example.com/share?code=x&type=Server") is None
    assert roblox_launch.deep_link_for("https://www.roblox.com/games/1/x") is None


def test_a_link_code_outside_the_expected_alphabet_is_refused_rather_than_escaped() -> None:
    """This value is interpolated into a URL the shell opens; anything odd must not get through."""
    hostile = "https://www.roblox.com/games/12345/x?privateServerLinkCode=a%20b%26c"

    assert roblox_launch.private_server_from_link(hostile) is None


def test_a_share_link_becomes_a_deep_link_without_asking_anyone(monkeypatch) -> None:
    """The web link and the protocol link are the same code under two prefixes.

    Verified against Roblox' own redirect for a share link, which answers with exactly this string,
    and which returns a fabricated code unchanged: it fills a template rather than looking anything
    up. So this conversion may not reach the network, and the test proves it does not.
    """
    monkeypatch.setattr(
        roblox_launch,
        "_start_plain",
        lambda _target: pytest.fail("the conversion must not launch anything"),
    )

    link = roblox_launch.deep_link_for(SHARE_LINK)

    assert link == "roblox://navigation/share_links?code=shareCode1&type=Server"


def test_a_share_link_reaches_the_shell_as_a_deep_link_with_no_network(monkeypatch) -> None:
    """End to end, and offline: opening a socket at all fails the test rather than the launch.

    The API this replaced could only ever answer 401 for an application, so a launch that depends
    on reaching the network is a launch that does not work. Asserted through behaviour rather than
    by grepping the source, so a future implementation that reached the network by some other route
    would still be caught.
    """
    monkeypatch.setattr(
        socket, "socket", lambda *_a, **_k: pytest.fail("the launch must not open a socket")
    )
    started: list[str] = []
    _patch_launch(monkeypatch, roblox_after=[True], started=started)

    assert roblox_launch.run_launch(SHARE_LINK, log=lambda _message: None) is True

    assert started == ["roblox://navigation/share_links?code=shareCode1&type=Server"]


def test_a_share_link_for_something_other_than_a_server_is_refused() -> None:
    """A link to a profile or an experience has no business being launched as a private server."""
    assert (
        roblox_launch.share_deep_link("https://www.roblox.com/share?code=abc&type=Profile") is None
    )
    assert roblox_launch.share_deep_link(PRIVATE_SERVER_LINK) is None


# ---------------------------------------------------------------------------------------------
# The launch itself
# ---------------------------------------------------------------------------------------------


DEEP_LINK = "roblox://experiences/start?placeId=12345&linkCode=abc123DEF"


def _patch_launch(
    monkeypatch, *, roblox_after: list[bool], started: list[str], browser_pid: int | None = 4242
):
    """Pin the three things the launch chain reacts to.

    What it starts, which pid the shell reports having started for it, and whether a NEW Roblox
    process shows up afterwards.
    """

    def start_and_own(target: str) -> roblox_launch.ShellLaunch:
        started.append(target)
        if target.startswith("roblox://") or browser_pid is None:
            return roblox_launch.ShellLaunch(True, None, None)
        return roblox_launch.ShellLaunch(True, browser_pid, 0xBEEF)

    monkeypatch.setattr(roblox_launch, "start_and_own", start_and_own)
    monkeypatch.setattr(
        roblox_launch,
        "wait_for_new_roblox",
        lambda *_args, **_kwargs: roblox_after.pop(0) if roblox_after else False,
    )
    monkeypatch.setattr(roblox_launch, "roblox_pids", set)


def test_a_working_deep_link_opens_no_browser_at_all(monkeypatch) -> None:
    started: list[str] = []
    messages: list[str] = []
    _patch_launch(monkeypatch, roblox_after=[True], started=started)

    assert roblox_launch.run_launch(PRIVATE_SERVER_LINK, log=messages.append) is True

    assert started == [DEEP_LINK]
    assert any("without a browser" in message for message in messages)


def test_a_deep_link_that_does_not_bring_roblox_up_falls_back_to_the_browser(monkeypatch) -> None:
    """An installed client that ignores the protocol link must not leave the session with nothing."""
    started: list[str] = []
    messages: list[str] = []
    _patch_launch(monkeypatch, roblox_after=[False, True], started=started)
    closed: list[int] = []
    monkeypatch.setattr(roblox_launch, "_close_pid", closed.append)

    assert roblox_launch.run_launch(PRIVATE_SERVER_LINK, log=messages.append) is True

    assert started == [DEEP_LINK, PRIVATE_SERVER_LINK]
    assert closed == [4242]


def test_only_the_process_the_shell_started_for_this_link_is_ever_closed(monkeypatch) -> None:
    """A browser that was already running gets no handle back, and must survive untouched.

    This is the whole ownership rule: the pid comes from ShellExecuteExW's own process handle, so
    it can only be a process that exists because of this launch. A shell that routed the link into
    a running browser starts nothing, reports no pid, and nothing is closed.
    """
    started: list[str] = []
    messages: list[str] = []
    _patch_launch(monkeypatch, roblox_after=[False, True], started=started, browser_pid=None)
    closed: list[int] = []
    monkeypatch.setattr(roblox_launch, "_close_pid", closed.append)

    assert roblox_launch.run_launch(PRIVATE_SERVER_LINK, log=messages.append) is True

    assert closed == []
    assert any("already running" in message for message in messages)


def test_a_roblox_that_was_already_open_does_not_count_as_a_successful_handoff(monkeypatch) -> None:
    """Otherwise every launch reports instant success and the browser is closed doing nothing."""
    monkeypatch.setattr(roblox_launch, "roblox_pids", lambda: {111})
    slept: list[float] = []
    clock = iter([0.0, 1.0, 99.0])

    result = roblox_launch.wait_for_new_roblox(
        {111}, 5.0, sleep=slept.append, monotonic=lambda: next(clock)
    )

    assert result is False


def test_a_new_roblox_process_is_what_counts_as_the_handoff(monkeypatch) -> None:
    monkeypatch.setattr(roblox_launch, "roblox_pids", lambda: {111, 222})

    assert roblox_launch.wait_for_new_roblox({111}, 5.0, monotonic=lambda: 0.0) is True


def test_the_browser_is_left_open_when_roblox_never_came_up(monkeypatch) -> None:
    """The page it is showing is then the only thing that says why nothing started."""
    started: list[str] = []
    messages: list[str] = []
    _patch_launch(monkeypatch, roblox_after=[False, False], started=started)
    closed: list[int] = []
    monkeypatch.setattr(roblox_launch, "_close_pid", closed.append)

    assert roblox_launch.run_launch(PRIVATE_SERVER_LINK, log=messages.append) is False

    assert closed == []
    assert any("left open" in message for message in messages)


def test_an_unconvertible_link_still_reaches_the_browser(monkeypatch) -> None:
    """A share code that cannot be resolved has to keep working exactly like it did before."""
    started: list[str] = []
    messages: list[str] = []
    _patch_launch(monkeypatch, roblox_after=[True], started=started)
    monkeypatch.setattr(roblox_launch, "deep_link_for", lambda *_a, **_k: None)
    monkeypatch.setattr(roblox_launch, "_close_pid", lambda _pid: None)

    assert roblox_launch.run_launch(SHARE_LINK, log=messages.append) is True

    assert started == [SHARE_LINK]


# ---------------------------------------------------------------------------------------------
# The Win32 boundary: what the shell handed back is the only thing that may ever be closed
# ---------------------------------------------------------------------------------------------


def test_a_shell_call_that_cannot_hand_back_a_handle_still_launches(monkeypatch) -> None:
    """The floor under the whole module: never worse than the plain shell open it replaced."""
    monkeypatch.setattr(roblox_launch.sys, "platform", "not-win32")
    opened: list[str] = []
    monkeypatch.setattr(
        roblox_launch.os, "startfile", lambda target: opened.append(target), raising=False
    )

    assert roblox_launch.start_and_own(DEEP_LINK) == (True, None, None)
    assert opened == [DEEP_LINK]


def test_the_handle_is_kept_so_the_pid_cannot_be_recycled_under_us(monkeypatch) -> None:
    """The pid is only meaningful while a handle to that process is still open."""
    closed: list[int] = []
    monkeypatch.setattr(roblox_launch, "close_process_handle", closed.append)

    launch = roblox_launch.start_and_own(
        SHARE_LINK, execute=lambda _target: (True, 0x1234), process_id=lambda _handle: 777
    )

    assert launch == (True, 777, 0x1234)
    assert closed == []


def test_a_shell_that_started_nothing_reports_nothing_to_close() -> None:
    """The link went to a running browser, whose window may be the user's own."""
    launch = roblox_launch.start_and_own(SHARE_LINK, execute=lambda _target: (True, 0))

    assert launch == (True, None, None)


def test_a_handle_with_no_readable_pid_is_released_instead_of_leaked(monkeypatch) -> None:
    closed: list[int] = []
    monkeypatch.setattr(roblox_launch, "close_process_handle", closed.append)

    def failing_pid(_handle: int) -> int:
        raise OSError("no pid")

    launch = roblox_launch.start_and_own(
        SHARE_LINK, execute=lambda _target: (True, 0x99), process_id=failing_pid
    )

    assert launch == (True, None, None)
    assert closed == [0x99]


def test_a_link_the_shell_already_opened_is_never_opened_a_second_time(monkeypatch) -> None:
    """The plain fallback belongs to a shell call that did NOT run; anything else double-launches."""
    opened: list[str] = []
    monkeypatch.setattr(
        roblox_launch.os, "startfile", lambda target: opened.append(target), raising=False
    )

    def failing_pid(_handle: int) -> int:
        raise OSError("no pid")

    roblox_launch.start_and_own(
        SHARE_LINK, execute=lambda _target: (True, 0x99), process_id=failing_pid
    )

    assert opened == []


def test_a_shell_call_that_refused_falls_back_to_the_plain_open(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        roblox_launch.os, "startfile", lambda target: opened.append(target), raising=False
    )

    assert roblox_launch.start_and_own(SHARE_LINK, execute=lambda _target: (False, 0)).ok is True
    assert roblox_launch.start_and_own(
        SHARE_LINK, execute=lambda _target: (_ for _ in ()).throw(OSError("boom"))
    ).ok is True
    assert opened == [SHARE_LINK, SHARE_LINK]


def test_the_handle_is_released_on_every_way_out_of_the_browser_path(monkeypatch) -> None:
    started: list[str] = []
    released: list[int | None] = []
    monkeypatch.setattr(roblox_launch, "close_process_handle", released.append)
    monkeypatch.setattr(roblox_launch, "_close_pid", lambda _pid: None)
    _patch_launch(monkeypatch, roblox_after=[False, False], started=started)

    roblox_launch.run_launch(PRIVATE_SERVER_LINK, log=lambda _message: None)

    # Once for the roblox:// attempt, once for the browser attempt, and the browser's is released
    # even though Roblox never came up and nothing was closed.
    assert released == [None, 0xBEEF]


def test_launch_game_validates_before_it_starts_any_work(monkeypatch) -> None:
    start_and_own = MagicMock(return_value=roblox_launch.ShellLaunch(True, None, None))
    monkeypatch.setattr(roblox_launch, "start_and_own", start_and_own)
    _RecordingThread.instances.clear()

    assert roblox_launch.launch_game("   ", spawn=_RecordingThread) is False
    assert roblox_launch.launch_game("file:///C:/calc.exe", spawn=_RecordingThread) is False

    assert _RecordingThread.instances == []
    start_and_own.assert_not_called()


def test_launch_game_does_the_work_off_the_calling_thread(monkeypatch) -> None:
    """Both callers reach this from a path that must not block: the shell start-up and the GUI."""
    started: list[str] = []
    _patch_launch(monkeypatch, roblox_after=[True], started=started)
    _RecordingThread.instances.clear()

    assert roblox_launch.launch_game(PRIVATE_SERVER_LINK, spawn=_RecordingThread) is True

    assert len(_RecordingThread.instances) == 1
    worker = _RecordingThread.instances[0]
    assert worker.daemon is True
    assert worker.started is True
    assert started == [DEEP_LINK]
