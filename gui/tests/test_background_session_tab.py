from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

from app import background_session, engine_process, window_branding
from app.background_session_tab import BackgroundSessionTab
from app.rdp_wrapper import CheckResult, SetupStatus


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
    monkeypatch.setattr(
        background_session,
        "show_background_session",
        lambda *_: background_session.BackgroundSessionResult(
            True, "Reconnecting to the background session."
        ),
    )
    tab = _tab(qtbot, tmp_path, _ready(), thread_starter=thread_starter)
    tab.username_edit.setText("trainer")

    tab._show()

    assert tab._branding_cancel is None
    assert thread_starter.calls == []


def test_show_with_a_client_pid_starts_window_branding(qtbot, tmp_path: Path, monkeypatch) -> None:
    thread_starter = _ThreadStarter()
    client_process = MagicMock()
    monkeypatch.setattr(
        background_session,
        "show_background_session",
        lambda *_: background_session.BackgroundSessionResult(
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
        lambda *_: background_session.BackgroundSessionResult(
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
        lambda *_: background_session.BackgroundSessionResult(
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
