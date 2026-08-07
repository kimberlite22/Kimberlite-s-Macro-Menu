from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from app import background_session, engine_process, rdp_wrapper, session_autostart, session_shell
from app import window_branding
from app.background_session_tab import (
    BOOT_ROUTE_AUTOSTART,
    BOOT_ROUTE_NONE,
    BOOT_ROUTE_SHELL,
    BackgroundSessionTab,
)
from app.rdp_wrapper import CheckResult, ElevatedChangeResult, SetupStatus


@pytest.fixture(autouse=True)
def _never_touch_the_real_autostart_entry(monkeypatch):
    """No test may leave a real Windows autostart entry on the machine it runs on.

    Start installs one when it takes the autostart route, and WHICH route it takes depends on the
    real machine's own settings (whether an installed copy exists, and whether the RemoteApp allow
    list is switched off). So without this, whether a plain Start test writes to the developer's
    HKCU Run key is decided by their PC's configuration rather than by the test. Autouse, so a test
    added later inherits the protection instead of having to remember it; the tests that assert on
    these calls re-patch them with their own recording versions on top.
    """
    monkeypatch.setattr(session_autostart, "install_autostart_entry", lambda *_a, **_k: True)
    monkeypatch.setattr(session_autostart, "remove_autostart_entry", lambda *_a, **_k: True)
    monkeypatch.setattr(session_autostart, "arm", lambda *_a, **_k: True)
    monkeypatch.setattr(session_autostart, "disarm", lambda *_a, **_k: None)


def _ready() -> SetupStatus:
    return SetupStatus(
        tuple(
            CheckResult(name, True, f"{name} is fine.", "")
            for name in (
                "Remote Desktop",
                "Multiple sessions per user",
                "RDP Wrapper installed",
                "RDP Wrapper supports this Windows build",
            )
        )
    )


def _not_ready() -> SetupStatus:
    return SetupStatus(
        (
            CheckResult("Remote Desktop", True, "Remote Desktop is enabled.", ""),
            CheckResult(
                "Multiple sessions per user",
                False,
                "Windows hands the same account its existing session.",
                "Set fSingleSessionPerUser to 0.",
            ),
            CheckResult(
                "RDP Wrapper installed",
                False,
                "Remote Desktop is not configured to load rdpwrap.dll.",
                "Install RDP Wrapper with administrator rights, then reboot.",
            ),
            CheckResult(
                "RDP Wrapper supports this Windows build",
                False,
                "RDP Wrapper is not installed or active.",
                "Install and activate RDP Wrapper first.",
            ),
        )
    )


def _warnings_only() -> SetupStatus:
    return SetupStatus(
        (
            CheckResult("Remote Desktop", True, "Remote Desktop is enabled.", ""),
            CheckResult("Multiple sessions per user", True, "Multiple sessions are enabled.", ""),
            CheckResult("RDP Wrapper installed", True, "RDP Wrapper is installed.", ""),
            CheckResult(
                "RDP Wrapper supports this Windows build",
                False,
                "The Windows build version of termsrv.dll could not be determined.",
                "Check that Windows termsrv.dll is present.",
                undetermined=True,
            ),
        )
    )


class _FakeThread:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True


class _ThreadStarter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, tuple[object, ...], bool, _FakeThread]] = []
        self.kwargs: list[dict[str, object]] = []
        self.cancel_to_observe: threading.Event | None = None
        self.observed_cancel_states: list[bool] = []

    def __call__(
        self,
        *,
        target: object,
        args: tuple[object, ...],
        daemon: bool,
        kwargs: dict[str, object] | None = None,
    ) -> _FakeThread:
        if self.cancel_to_observe is not None:
            self.observed_cancel_states.append(self.cancel_to_observe.is_set())
        thread = _FakeThread()
        self.calls.append((target, args, daemon, thread))
        self.kwargs.append(dict(kwargs or {}))
        return thread


def _tab(
    qtbot,
    tmp_path: Path,
    status: SetupStatus,
    *,
    thread_starter: object | None = None,
    confirm_stop_engine: object | None = None,
) -> BackgroundSessionTab:
    tab = BackgroundSessionTab(
        tmp_path,
        check_setup=lambda: status,
        thread_starter=thread_starter or _ThreadStarter(),
        confirm_stop_engine=confirm_stop_engine,
    )
    qtbot.addWidget(tab)
    tab.show()
    return tab


def test_a_ready_machine_enables_start_and_says_so(qtbot, tmp_path: Path) -> None:
    tab = _tab(qtbot, tmp_path, _ready())

    assert tab.start_button.isEnabled() is True
    assert "ready" in tab.setup_summary_label.text().casefold()
    assert "know what you are doing" not in tab.setup_summary_label.text().casefold()
    assert "Needs attention" not in tab.setup_details_label.text()


def test_status_reports_the_recorded_sessions_actual_windows_state(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    marker = background_session._BackgroundSessionMarker(
        4, "127.0.0.2", "HOSTNAME", "trainer", 1.0
    )
    monkeypatch.setattr(background_session, "_resolve_marker", lambda _: (marker, "ok"))
    session = MagicMock(
        return_value=background_session.SessionInfo(4, background_session.SessionState.ACTIVE)
    )
    monkeypatch.setattr(background_session, "find_session_by_id", session)
    tab = _tab(qtbot, tmp_path, _ready())

    tab._refresh_status()

    assert tab.status_label.text() == "Background session: running (active)."
    session.return_value = background_session.SessionInfo(
        4, background_session.SessionState.DISCONNECTED
    )

    tab._refresh_status()

    assert tab.status_label.text() == "Background session: running (disconnected)."


def test_an_unready_machine_disables_start_and_lists_every_instruction(
    qtbot, tmp_path: Path
) -> None:
    tab = _tab(qtbot, tmp_path, _not_ready())

    assert tab.start_button.isEnabled() is False
    details = tab.setup_details_label.text()
    assert "Set fSingleSessionPerUser to 0." in details
    assert "Install RDP Wrapper with administrator rights, then reboot." in details
    # The one passing check is still shown, so the user sees the whole picture, not only failures.
    assert "OK: Remote Desktop" in details
    assert "know what you are doing" not in tab.setup_summary_label.text().casefold()


def test_an_undetermined_check_enables_start_with_a_warning(qtbot, tmp_path: Path) -> None:
    tab = _tab(qtbot, tmp_path, _warnings_only())

    assert tab.start_button.isEnabled() is True
    assert "could not be fully confirmed" in tab.setup_summary_label.text().casefold()
    assert "know what you are doing" in tab.setup_summary_label.text().casefold()
    assert "Warning: RDP Wrapper supports this Windows build" in tab.setup_details_label.text()


def test_start_is_never_reached_while_the_setup_gate_is_closed(qtbot, tmp_path: Path, monkeypatch) -> None:
    start = MagicMock()
    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = _tab(qtbot, tmp_path, _not_ready())

    tab.start_button.click()

    start.assert_not_called()


def test_re_checking_after_the_machine_was_fixed_opens_the_gate(qtbot, tmp_path: Path) -> None:
    statuses = [_not_ready(), _ready()]
    tab = BackgroundSessionTab(tmp_path, check_setup=lambda: statuses.pop(0))
    qtbot.addWidget(tab)
    tab.show()
    assert tab.start_button.isEnabled() is False

    tab.recheck_button.click()

    assert tab.start_button.isEnabled() is True


def test_the_tab_stores_the_entry_file_for_window_branding(qtbot, tmp_path: Path) -> None:
    entry_file = tmp_path / "gui.py"
    tab = BackgroundSessionTab(tmp_path, entry_file=entry_file, check_setup=_ready)
    qtbot.addWidget(tab)

    assert tab._entry_file == entry_file


def test_show_with_no_client_pid_does_not_start_window_branding(qtbot, tmp_path: Path, monkeypatch) -> None:
    thread_starter = _ThreadStarter()
    tab = _tab(qtbot, tmp_path, _ready(), thread_starter=thread_starter)

    def show(*_, pump):
        assert pump is QApplication.processEvents
        assert tab.start_button.isEnabled() is False
        assert tab.show_button.isEnabled() is False
        assert tab.stop_button.isEnabled() is False
        return background_session.BackgroundSessionResult(
            True, "Reconnecting to the background session."
        )

    monkeypatch.setattr(
        background_session,
        "show_background_session",
        show,
    )
    tab.username_edit.setText("trainer")

    tab._show()

    assert tab.start_button.isEnabled() is True
    assert tab.show_button.isEnabled() is True
    assert tab.stop_button.isEnabled() is True
    assert tab._branding_cancel is None
    assert thread_starter.calls == []


def test_show_with_a_client_pid_starts_window_branding(qtbot, tmp_path: Path, monkeypatch) -> None:
    thread_starter = _ThreadStarter()
    client_process = MagicMock()
    monkeypatch.setattr(
        background_session,
        "show_background_session",
        lambda *_, **__: background_session.BackgroundSessionResult(
            True,
            "Reconnecting to the background session.",
            client_pid=2468,
            client_process=client_process,
        ),
    )
    tab = _tab(qtbot, tmp_path, _ready(), thread_starter=thread_starter)
    tab.username_edit.setText("trainer")

    tab._show()

    assert len(thread_starter.calls) == 1
    target, args, daemon, thread = thread_starter.calls[0]
    assert target is window_branding.run_branding_loop
    assert args[0] == 2468
    assert args[-1] is tab._branding_cancel
    assert daemon is True
    assert thread.started is True
    assert tab._branding_process is client_process
    # Also handed to the worker itself, so its open process handle keeps the operating system
    # from recycling the pid while a pass is still in flight after cancellation.
    assert thread_starter.kwargs[0]["keep_alive"] is client_process


def test_a_second_show_cancels_the_first_branding_event(qtbot, tmp_path: Path, monkeypatch) -> None:
    thread_starter = _ThreadStarter()
    pids = iter((2468, 8642))
    first_process = MagicMock()
    second_process = MagicMock()
    client_processes = iter((first_process, second_process))
    monkeypatch.setattr(
        background_session,
        "show_background_session",
        lambda *_, **__: background_session.BackgroundSessionResult(
            True,
            "Reconnecting to the background session.",
            client_pid=next(pids),
            client_process=next(client_processes),
        ),
    )
    tab = _tab(qtbot, tmp_path, _ready(), thread_starter=thread_starter)
    tab.username_edit.setText("trainer")

    tab._show()
    first_cancel = tab._branding_cancel
    thread_starter.cancel_to_observe = first_cancel
    tab._show()

    assert first_cancel is not None
    assert first_cancel.is_set() is True
    assert thread_starter.observed_cancel_states == [True]
    assert tab._branding_cancel is not first_cancel
    assert tab._branding_process is second_process
    assert tab._branding_process is not first_process
    assert len(thread_starter.calls) == 2


def test_stop_cancels_the_running_branding_event(qtbot, tmp_path: Path, monkeypatch) -> None:
    thread_starter = _ThreadStarter()
    client_process = MagicMock()
    monkeypatch.setattr(
        background_session,
        "show_background_session",
        lambda *_, **__: background_session.BackgroundSessionResult(
            True,
            "Reconnecting to the background session.",
            client_pid=2468,
            client_process=client_process,
        ),
    )
    monkeypatch.setattr(
        background_session,
        "stop_background_session",
        lambda *_, **__: background_session.BackgroundSessionResult(True, "Stopped."),
    )
    tab = _tab(qtbot, tmp_path, _ready(), thread_starter=thread_starter)
    tab.username_edit.setText("trainer")
    tab._show()
    cancel = tab._branding_cancel
    assert tab._branding_process is client_process

    tab._stop()

    assert cancel is not None
    assert cancel.is_set() is True
    assert tab._branding_cancel is None
    assert tab._branding_process is None


def test_calling_start_directly_still_refuses_on_an_unready_machine(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """The disabled button only hides the action; _start itself has to enforce the verdict."""
    start = MagicMock(return_value=background_session.BackgroundSessionResult(False, "nope"))
    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = _tab(qtbot, tmp_path, _ready())
    tab._can_start = False

    tab._start()

    start.assert_not_called()
    assert "Re-check" in tab.result_text.toPlainText()


def test_a_failed_start_does_not_reopen_the_gate_on_an_unready_machine(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """_start's finally block re-enables the buttons; Start must still respect the setup verdict."""
    monkeypatch.setattr(
        background_session,
        "start_background_session",
        MagicMock(return_value=background_session.BackgroundSessionResult(False, "nope")),
    )
    tab = _tab(qtbot, tmp_path, _ready())

    tab._start()
    tab._can_start = False
    tab._set_buttons_enabled(True)

    assert tab.start_button.isEnabled() is False
    assert tab.show_button.isEnabled() is True


def test_start_stops_the_engine_enumerated_after_confirmation(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    before_confirmation = engine_process.EngineProcess(2468, 3)
    after_confirmation = engine_process.EngineProcess(1357, 3)
    engines = [before_confirmation]

    def confirm() -> bool:
        engines[:] = [after_confirmation]
        return True

    def clear_stopped_engine(pid: int) -> None:
        assert pid == after_confirmation.pid
        engines.clear()

    stop = MagicMock(side_effect=clear_stopped_engine)
    start = MagicMock(return_value=background_session.BackgroundSessionResult(True, "Started."))
    monkeypatch.setattr(engine_process, "current_session_id", lambda: 3)
    monkeypatch.setattr(engine_process, "find_engine_processes", lambda: engines)
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    monkeypatch.setattr(background_session, "start_background_session", start)
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: False)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    tab = _tab(qtbot, tmp_path, _ready(), confirm_stop_engine=confirm)

    tab._start()

    stop.assert_called_once_with(after_confirmation.pid)
    assert engines == []
    start.assert_called_once()


def test_start_leaves_a_local_engine_running_when_the_user_declines(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    local_engine = engine_process.EngineProcess(2468, 3)
    stop = MagicMock()
    start = MagicMock()
    monkeypatch.setattr(engine_process, "current_session_id", lambda: 3)
    monkeypatch.setattr(engine_process, "find_engine_processes", lambda: [local_engine])
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    monkeypatch.setattr(background_session, "start_background_session", start)
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: False)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    tab = _tab(qtbot, tmp_path, _ready(), confirm_stop_engine=lambda: False)

    tab._start()

    stop.assert_not_called()
    start.assert_not_called()
    assert tab.result_text.toPlainText() == "Nothing was changed. The background session was not started."


def test_start_ignores_an_engine_in_another_session(qtbot, tmp_path: Path, monkeypatch) -> None:
    remote_engine = engine_process.EngineProcess(2468, 4)
    stop = MagicMock()
    confirm = MagicMock(return_value=True)
    start = MagicMock(return_value=background_session.BackgroundSessionResult(True, "Started."))
    monkeypatch.setattr(engine_process, "current_session_id", lambda: 3)
    monkeypatch.setattr(engine_process, "find_engine_processes", lambda: [remote_engine])
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    monkeypatch.setattr(background_session, "start_background_session", start)
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: False)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    tab = _tab(qtbot, tmp_path, _ready(), confirm_stop_engine=confirm)

    tab._start()

    stop.assert_not_called()
    confirm.assert_not_called()
    start.assert_called_once()


def test_start_refuses_when_engine_sessions_cannot_be_verified(qtbot, tmp_path: Path, monkeypatch) -> None:
    stop = MagicMock()
    start = MagicMock()
    message = (
        "The macro engine is running on this desktop right now. Stop it first: starting a "
        "background session while it runs would leave two engines sharing one config."
    )
    cases = (
        (lambda: 3, [engine_process.EngineProcess(2468, None)]),
        (lambda: None, [engine_process.EngineProcess(2468, 3)]),
    )
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    monkeypatch.setattr(background_session, "start_background_session", start)
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: False)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)

    for current_session_id, engines in cases:
        monkeypatch.setattr(engine_process, "current_session_id", current_session_id)
        monkeypatch.setattr(engine_process, "find_engine_processes", lambda engines=engines: engines)
        tab = _tab(qtbot, tmp_path, _ready(), confirm_stop_engine=lambda: True)

        tab._start()

        assert tab.result_text.toPlainText() == message

    stop.assert_not_called()
    start.assert_not_called()


def test_start_refuses_when_a_local_engine_survives_stopping(qtbot, tmp_path: Path, monkeypatch) -> None:
    local_engine = engine_process.EngineProcess(2468, 3)
    stop = MagicMock()
    start = MagicMock()
    monkeypatch.setattr(engine_process, "current_session_id", lambda: 3)
    monkeypatch.setattr(
        engine_process,
        "find_engine_processes",
        MagicMock(side_effect=([local_engine], [local_engine], [local_engine])),
    )
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    monkeypatch.setattr(background_session, "start_background_session", start)
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: False)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    tab = _tab(qtbot, tmp_path, _ready(), confirm_stop_engine=lambda: True)

    tab._start()

    stop.assert_called_once_with(2468)
    start.assert_not_called()
    assert tab.result_text.toPlainText() == "The macro engine on this desktop could not be stopped."


def test_start_proceeds_when_no_engine_runs_and_its_session_is_unknown(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    start = MagicMock(return_value=background_session.BackgroundSessionResult(True, "Started."))
    current_session_id = MagicMock(return_value=None)
    stop = MagicMock()
    monkeypatch.setattr(engine_process, "current_session_id", current_session_id)
    monkeypatch.setattr(engine_process, "find_engine_processes", lambda: [])
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: False)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = _tab(qtbot, tmp_path, _ready())

    tab._start()

    current_session_id.assert_not_called()
    stop.assert_not_called()
    start.assert_called_once()


def test_start_leaves_the_engine_alone_for_an_active_background_session(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    local_engine = engine_process.EngineProcess(2468, 3)
    stop = MagicMock()
    find_engines = MagicMock(return_value=[local_engine])
    current_session_id = MagicMock(return_value=3)
    message = "Canonical active-session refusal."
    start = MagicMock(return_value=background_session.BackgroundSessionResult(False, message))
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: True)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    monkeypatch.setattr(background_session, "start_background_session", start)
    monkeypatch.setattr(engine_process, "find_engine_processes", find_engines)
    monkeypatch.setattr(engine_process, "current_session_id", current_session_id)
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    tab = _tab(qtbot, tmp_path, _ready(), confirm_stop_engine=lambda: True)

    tab._start()

    stop.assert_not_called()
    find_engines.assert_not_called()
    current_session_id.assert_not_called()
    start.assert_called_once()
    assert tab.result_text.toPlainText() == message


def test_start_reports_a_missing_credential_before_stopping_a_local_engine(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    local_engine = engine_process.EngineProcess(2468, 3)
    stop = MagicMock()
    tab_find_engines = MagicMock(return_value=[local_engine])
    session_find_engines = MagicMock(return_value=[local_engine])
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: False)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: False)
    monkeypatch.setattr(background_session, "find_engine_processes", session_find_engines)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 3)
    monkeypatch.setattr(engine_process, "find_engine_processes", tab_find_engines)
    monkeypatch.setattr(engine_process, "current_session_id", lambda: 3)
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    tab = _tab(qtbot, tmp_path, _ready(), confirm_stop_engine=lambda: True)

    tab._start()

    assert tab.result_text.toPlainText() == (
        "No saved sign-in credential for the background session. Enter the password and "
        "click Save Credential first."
    )
    stop.assert_not_called()
    tab_find_engines.assert_not_called()
    session_find_engines.assert_not_called()


def test_start_proceeds_when_the_engine_exits_while_confirmation_is_open(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    local_engine = engine_process.EngineProcess(2468, 3)
    engines = [local_engine]
    stop = MagicMock()
    start = MagicMock(return_value=background_session.BackgroundSessionResult(True, "Started."))

    def confirm() -> bool:
        engines.clear()
        return True

    monkeypatch.setattr(engine_process, "current_session_id", lambda: 3)
    monkeypatch.setattr(engine_process, "find_engine_processes", lambda: engines)
    monkeypatch.setattr(engine_process, "stop_engine_by_pid", stop)
    monkeypatch.setattr(background_session, "is_background_session_active", lambda _: False)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = _tab(qtbot, tmp_path, _ready(), confirm_stop_engine=confirm)

    tab._start()

    stop.assert_not_called()
    start.assert_called_once()


def test_the_tab_states_the_third_party_and_licensing_caveats_up_front(qtbot, tmp_path: Path) -> None:
    tab = _tab(qtbot, tmp_path, _ready())
    described = " ".join(
        label.text() for label in tab.findChildren(type(tab.setup_summary_label))
    ).casefold()

    assert "not bundled" in described
    assert "administrator" in described
    assert "licensing" in described


# ---------------------------------------------------------------------------------------------
# Which route the "boot straight into the macro" option takes, and what it promises while doing it
# ---------------------------------------------------------------------------------------------


def _routes(monkeypatch, *, shell_installed: bool, allow_list: bool | None, installed: bool = True):
    """Pin the three machine facts the route decision is made from."""
    monkeypatch.setattr(session_shell, "session_shell_available", lambda *_: shell_installed)
    monkeypatch.setattr(rdp_wrapper, "initial_program_allow_list_disabled", lambda: allow_list)
    monkeypatch.setattr(session_autostart, "autostart_available", lambda *_: installed)


def test_the_alternate_shell_is_used_when_windows_will_actually_start_it(
    monkeypatch, tmp_path: Path
) -> None:
    _routes(monkeypatch, shell_installed=True, allow_list=True)

    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)

    assert tab.boot_route() == BOOT_ROUTE_SHELL
    assert "no Windows desktop" in tab.minimal_shell_label.text()


def test_an_enforced_allow_list_falls_back_to_autostart(monkeypatch, tmp_path: Path) -> None:
    """Windows refuses to launch an RDP initial program while its allow list is enforced."""
    _routes(monkeypatch, shell_installed=True, allow_list=False)

    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)

    assert tab.boot_route() == BOOT_ROUTE_AUTOSTART
    assert tab.minimal_shell_checkbox.isEnabled() is True


def test_an_unreadable_allow_list_never_risks_the_alternate_shell(
    monkeypatch, tmp_path: Path
) -> None:
    """Guessing wrong here produces a session with no shell at all, which is the bug being fixed."""
    _routes(monkeypatch, shell_installed=True, allow_list=None)

    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)

    assert tab.boot_route() == BOOT_ROUTE_AUTOSTART


def test_the_label_never_promises_a_missing_desktop_on_the_autostart_route(
    monkeypatch, tmp_path: Path
) -> None:
    """The option must either work or say what it really does; it may not promise the wrong one."""
    _routes(monkeypatch, shell_installed=True, allow_list=False)

    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)

    assert "no Windows desktop" not in tab.minimal_shell_label.text()
    assert "normal Windows desktop" in tab.boot_mode_label.text()


def test_the_option_is_not_offered_when_neither_route_can_work(monkeypatch, tmp_path: Path) -> None:
    _routes(monkeypatch, shell_installed=False, allow_list=False, installed=False)

    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)

    assert tab.boot_route() == BOOT_ROUTE_NONE
    assert tab.minimal_shell_checkbox.isEnabled() is False
    assert tab.minimal_shell_checkbox.isChecked() is False


def test_the_elevated_switch_is_offered_only_when_it_would_change_something(
    qtbot, monkeypatch, tmp_path: Path
) -> None:
    """With no installed shell executable there is nothing for the no-desktop route to start."""
    _routes(monkeypatch, shell_installed=False, allow_list=False, installed=True)

    tab = _tab(qtbot, tmp_path, _ready())

    assert tab.no_desktop_checkbox.isVisible() is False
    assert tab.no_desktop_label.isVisible() is False


def test_the_elevated_switch_is_offered_when_it_would_unlock_the_better_route(
    qtbot, monkeypatch, tmp_path: Path
) -> None:
    _routes(monkeypatch, shell_installed=True, allow_list=False, installed=True)

    tab = _tab(qtbot, tmp_path, _ready())

    assert tab.no_desktop_checkbox.isVisible() is True
    assert tab.no_desktop_checkbox.isChecked() is False


def test_the_checkbox_starts_out_showing_what_the_machine_is_already_set_to(
    monkeypatch, tmp_path: Path
) -> None:
    """It renders a machine setting, so it may not claim the mode is off while it is on."""
    _routes(monkeypatch, shell_installed=True, allow_list=True)

    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)

    assert tab.no_desktop_checkbox.isChecked() is True


def test_ticking_the_checkbox_changes_nothing_until_start(monkeypatch, tmp_path: Path) -> None:
    """The whole point of the checkbox: no administrator prompt out of nowhere."""
    _routes(monkeypatch, shell_installed=True, allow_list=False)
    calls: list[bool] = []
    monkeypatch.setattr(
        rdp_wrapper,
        "set_initial_program_allow_list_disabled",
        lambda disabled, **_kwargs: calls.append(disabled) or ElevatedChangeResult(True, "Done."),
    )
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)

    tab.no_desktop_checkbox.setChecked(True)

    assert calls == []
    assert tab.boot_route() == BOOT_ROUTE_AUTOSTART


def test_a_re_check_leaves_a_pending_tick_alone(monkeypatch, tmp_path: Path) -> None:
    """Re-check re-renders from the machine, which must not undo a tick Start has not seen yet."""
    _routes(monkeypatch, shell_installed=True, allow_list=False)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.no_desktop_checkbox.setChecked(True)

    tab._recheck()

    assert tab.no_desktop_checkbox.isChecked() is True


def test_the_box_is_synced_the_first_time_it_can_be_shown_at_all(
    monkeypatch, tmp_path: Path
) -> None:
    """A hidden render may not be remembered as "already showing this machine value".

    Without this, a tab built before the shell executable existed keeps the box on its unchecked
    default, the next re-check sees an unchanged machine value and syncs nothing, and Start reads
    that default as the user asking to restore the Windows default: it would switch OFF a mode the
    user never touched.
    """
    machine = {"shell": False, "disabled": True}
    monkeypatch.setattr(session_shell, "session_shell_available", lambda *_: machine["shell"])
    monkeypatch.setattr(
        rdp_wrapper, "initial_program_allow_list_disabled", lambda: machine["disabled"]
    )
    monkeypatch.setattr(session_autostart, "autostart_available", lambda *_: True)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    assert tab.no_desktop_checkbox.isChecked() is False

    machine["shell"] = True
    tab._recheck()

    assert tab.no_desktop_checkbox.isChecked() is True


def test_start_applies_the_ticked_setting_and_then_takes_the_unlocked_route(
    monkeypatch, tmp_path: Path
) -> None:
    state = {"disabled": False}
    monkeypatch.setattr(session_shell, "session_shell_available", lambda *_: True)
    monkeypatch.setattr(
        rdp_wrapper, "initial_program_allow_list_disabled", lambda: state["disabled"]
    )
    monkeypatch.setattr(session_autostart, "autostart_available", lambda *_: True)
    monkeypatch.setattr(session_shell, "session_shell_command", lambda *_: "C:\\shell.exe")

    def apply(disabled: bool, **_kwargs) -> ElevatedChangeResult:
        state["disabled"] = disabled
        return ElevatedChangeResult(True, "Done.")

    monkeypatch.setattr(rdp_wrapper, "set_initial_program_allow_list_disabled", apply)
    captured: dict[str, object] = {}

    def start(*args, **kwargs):
        captured.update(kwargs)
        return background_session.BackgroundSessionResult(True, "Started.", 9)

    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(True)
    tab.no_desktop_checkbox.setChecked(True)

    tab._start_background_session("user")

    assert state["disabled"] is True
    # The route has to be read AFTER the change, or the session starts in the mode the machine was
    # in a moment ago instead of the one the elevation just unlocked.
    assert captured["alternate_shell"] == "C:\\shell.exe"
    assert "no Windows desktop" in tab.minimal_shell_label.text()


def test_start_restores_the_windows_default_when_the_box_is_unticked(
    monkeypatch, tmp_path: Path
) -> None:
    """The way back has to be the same control that switched it on."""
    state = {"disabled": True}
    monkeypatch.setattr(session_shell, "session_shell_available", lambda *_: True)
    monkeypatch.setattr(
        rdp_wrapper, "initial_program_allow_list_disabled", lambda: state["disabled"]
    )
    monkeypatch.setattr(session_autostart, "autostart_available", lambda *_: True)

    def apply(disabled: bool, **_kwargs) -> ElevatedChangeResult:
        state["disabled"] = disabled
        return ElevatedChangeResult(True, "Restored the Windows default.")

    monkeypatch.setattr(rdp_wrapper, "set_initial_program_allow_list_disabled", apply)
    monkeypatch.setattr(
        background_session,
        "start_background_session",
        lambda *args, **kwargs: background_session.BackgroundSessionResult(True, "Started.", 9),
    )
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    assert tab.no_desktop_checkbox.isChecked() is True
    tab.no_desktop_checkbox.setChecked(False)

    tab._start_background_session("user")

    assert state["disabled"] is False


def test_a_declined_administrator_prompt_still_starts_the_session_and_says_why(
    monkeypatch, tmp_path: Path
) -> None:
    """A session with a desktop still works, so a refused elevation may not cost the user one."""
    _routes(monkeypatch, shell_installed=True, allow_list=False)
    monkeypatch.setattr(
        rdp_wrapper,
        "set_initial_program_allow_list_disabled",
        lambda *_args, **_kwargs: ElevatedChangeResult(
            False, "The administrator prompt was declined, so nothing was changed."
        ),
    )
    started: list[str] = []

    def start(*args, **kwargs):
        started.append("started")
        return background_session.BackgroundSessionResult(True, "Started.", 9)

    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.no_desktop_checkbox.setChecked(True)

    tab._start_background_session("user")

    assert started == ["started"]
    result = tab.result_text.toPlainText()
    assert "declined" in result
    assert "Started." in result


def test_start_asks_for_nothing_when_the_machine_already_matches_the_box(
    monkeypatch, tmp_path: Path
) -> None:
    """No elevation prompt on every Start once the setting is where the user wants it."""
    _routes(monkeypatch, shell_installed=True, allow_list=True)
    calls: list[bool] = []
    monkeypatch.setattr(
        rdp_wrapper,
        "set_initial_program_allow_list_disabled",
        lambda disabled, **_kwargs: calls.append(disabled) or ElevatedChangeResult(True, "Done."),
    )
    monkeypatch.setattr(session_shell, "session_shell_command", lambda *_: "C:\\shell.exe")
    monkeypatch.setattr(
        background_session,
        "start_background_session",
        lambda *args, **kwargs: background_session.BackgroundSessionResult(True, "Started.", 9),
    )
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)

    tab._start_background_session("user")

    assert calls == []


def test_start_never_touches_the_setting_where_the_option_does_not_apply(
    monkeypatch, tmp_path: Path
) -> None:
    """The control is hidden without an installed shell, so its state means nothing there.

    Deliberately not judged by isVisible(): an unopened tab reports every widget invisible, and a
    Start from there must behave exactly like a Start from the open tab.
    """
    _routes(monkeypatch, shell_installed=False, allow_list=True, installed=True)
    calls: list[bool] = []
    monkeypatch.setattr(
        rdp_wrapper,
        "set_initial_program_allow_list_disabled",
        lambda disabled, **_kwargs: calls.append(disabled) or ElevatedChangeResult(True, "Done."),
    )
    monkeypatch.setattr(
        background_session,
        "start_background_session",
        lambda *args, **kwargs: background_session.BackgroundSessionResult(True, "Started.", 9),
    )
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.no_desktop_checkbox.setChecked(False)

    tab._start_background_session("user")

    assert calls == []


def test_the_shell_route_passes_the_alternate_shell_and_arms_nothing(
    monkeypatch, tmp_path: Path
) -> None:
    _routes(monkeypatch, shell_installed=True, allow_list=True)
    monkeypatch.setattr(session_shell, "session_shell_command", lambda *_: "C:\\shell.exe")
    captured = {}

    def start(*args, **kwargs):
        captured.update(kwargs)
        return background_session.BackgroundSessionResult(True, "Started.", 9)

    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(True)

    tab._start_background_session("trainer")

    assert captured["alternate_shell"] == "C:\\shell.exe"
    assert captured["before_launch"] is None


def test_the_autostart_route_installs_the_entry_and_arms_at_launch_time(
    monkeypatch, tmp_path: Path
) -> None:
    """Arming has to happen inside the helper, after every refusal it can still make."""
    _routes(monkeypatch, shell_installed=False, allow_list=False, installed=True)
    monkeypatch.setattr(session_autostart, "install_autostart_entry", lambda *_: True)
    armed: list[Path] = []
    monkeypatch.setattr(session_autostart, "arm", lambda directory: armed.append(directory))
    captured = {}

    def start(*args, **kwargs):
        captured.update(kwargs)
        assert armed == [], "the marker must not be armed before the helper accepted the start"
        kwargs["before_launch"]()
        return background_session.BackgroundSessionResult(True, "Started.", 9)

    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(True)

    tab._start_background_session("trainer")

    assert captured["alternate_shell"] is None
    assert armed == [tmp_path]


def test_a_start_that_produced_no_session_retracts_the_authorisation(
    monkeypatch, tmp_path: Path
) -> None:
    """Otherwise an RDP logon the user makes minutes later would be met with a macro starting."""
    _routes(monkeypatch, shell_installed=False, allow_list=False, installed=True)
    monkeypatch.setattr(session_autostart, "install_autostart_entry", lambda *_: True)
    monkeypatch.setattr(session_autostart, "arm", lambda directory: True)
    disarmed: list[Path] = []
    removed: list[bool] = []
    monkeypatch.setattr(session_autostart, "disarm", lambda directory: disarmed.append(directory))
    monkeypatch.setattr(
        session_autostart, "remove_autostart_entry", lambda: removed.append(True) or True
    )
    monkeypatch.setattr(
        background_session,
        "start_background_session",
        lambda *a, **k: background_session.BackgroundSessionResult(False, "Timed out.", None),
    )
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(True)

    tab._start_background_session("trainer")

    assert disarmed == [tmp_path]
    assert removed == [True]


def test_a_tracked_but_unconfirmed_session_keeps_its_authorisation(
    monkeypatch, tmp_path: Path
) -> None:
    """That session may still be logging on, and it is the one that needs the marker."""
    _routes(monkeypatch, shell_installed=False, allow_list=False, installed=True)
    monkeypatch.setattr(session_autostart, "install_autostart_entry", lambda *_: True)
    monkeypatch.setattr(session_autostart, "arm", lambda directory: True)
    disarmed: list[Path] = []
    monkeypatch.setattr(session_autostart, "disarm", lambda directory: disarmed.append(directory))
    monkeypatch.setattr(
        background_session,
        "start_background_session",
        lambda *a, **k: background_session.BackgroundSessionResult(False, "Not confirmed.", 12),
    )
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(True)

    tab._start_background_session("trainer")

    assert disarmed == []


def test_an_unchecked_option_uses_neither_route(monkeypatch, tmp_path: Path) -> None:
    _routes(monkeypatch, shell_installed=True, allow_list=True)
    captured = {}

    def start(*args, **kwargs):
        captured.update(kwargs)
        return background_session.BackgroundSessionResult(True, "Started.", 9)

    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(False)

    tab._start_background_session("trainer")

    assert captured["alternate_shell"] is None
    assert captured["before_launch"] is None


def test_a_failed_arm_is_reported_instead_of_looking_like_success(
    monkeypatch, tmp_path: Path
) -> None:
    """The session comes up fine but empty, which reads as success unless it is said out loud."""
    _routes(monkeypatch, shell_installed=False, allow_list=False, installed=True)
    monkeypatch.setattr(session_autostart, "install_autostart_entry", lambda *_: True)
    monkeypatch.setattr(session_autostart, "arm", lambda _directory: False)
    removed: list[bool] = []
    monkeypatch.setattr(
        session_autostart, "remove_autostart_entry", lambda: removed.append(True) or True
    )

    def start(*args, **kwargs):
        kwargs["before_launch"]()
        return background_session.BackgroundSessionResult(True, "Started.", 9)

    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(True)

    tab._start_background_session("trainer")

    assert "will not start the macro by itself" in tab.result_text.toPlainText()
    assert removed == [True]


def test_a_successful_arm_says_nothing_extra(monkeypatch, tmp_path: Path) -> None:
    _routes(monkeypatch, shell_installed=False, allow_list=False, installed=True)
    monkeypatch.setattr(session_autostart, "install_autostart_entry", lambda *_: True)
    monkeypatch.setattr(session_autostart, "arm", lambda _directory: True)

    def start(*args, **kwargs):
        kwargs["before_launch"]()
        return background_session.BackgroundSessionResult(True, "Started.", 9)

    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(True)

    tab._start_background_session("trainer")

    assert tab.result_text.toPlainText() == "Started."


def test_an_arm_that_raises_is_not_read_as_success(monkeypatch, tmp_path: Path) -> None:
    """start_background_session calls before_launch inside a catch-everything block.

    So a flag that recorded FAILURE would stay unset when arm() raised, and the user would be told
    the session was started when nothing in it will run the macro.
    """
    _routes(monkeypatch, shell_installed=False, allow_list=False, installed=True)
    monkeypatch.setattr(session_autostart, "install_autostart_entry", lambda *_: True)

    def explode(_directory):
        raise OSError("disk full")

    monkeypatch.setattr(session_autostart, "arm", explode)

    def start(*args, **kwargs):
        # Mirrors the real helper, which must not let a before_launch failure abort the session.
        try:
            kwargs["before_launch"]()
        except Exception:
            pass
        return background_session.BackgroundSessionResult(True, "Started.", 9)

    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = BackgroundSessionTab(tmp_path, check_setup=_ready)
    tab.minimal_shell_checkbox.setChecked(True)

    tab._start_background_session("trainer")

    assert "will not start the macro by itself" in tab.result_text.toPlainText()
