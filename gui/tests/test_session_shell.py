from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from app import session_shell
from app.engine_process import EngineProcess
from app.session_shell import SessionShellWindow


def test_the_shell_command_is_a_bare_session_shell_launcher_path(tmp_path: Path) -> None:
    """The alternate shell is CreateProcess's application name, not a command line."""
    directory = tmp_path / "Programs" / "Kimberlite's Macro Menu"

    command = session_shell.session_shell_command(directory)

    assert command == str(session_shell.session_shell_exe_path(directory))
    assert '"' not in command
    assert " --" not in command


def test_the_engine_is_started_when_this_session_has_none(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_shell, "_current_session", lambda: 3)
    # An engine in ANOTHER session is not this session's to use, unlike main.py's own startup.
    monkeypatch.setattr(session_shell, "find_engine_processes", lambda: [EngineProcess(42, 1)])
    monkeypatch.setattr(session_shell, "find_engine_executable", lambda _: ["engine.exe"])
    launch = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(session_shell, "launch_engine_hidden", launch)

    assert session_shell.ensure_engine_running(tmp_path) is not None
    launch.assert_called_once()


def test_no_second_engine_is_started_when_one_already_runs_here(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_shell, "_current_session", lambda: 3)
    monkeypatch.setattr(session_shell, "find_engine_processes", lambda: [EngineProcess(42, 3)])
    launch = MagicMock()
    monkeypatch.setattr(session_shell, "launch_engine_hidden", launch)

    assert session_shell.ensure_engine_running(tmp_path) is None
    launch.assert_not_called()


def test_an_engine_of_unknown_session_is_treated_as_ours(monkeypatch, tmp_path: Path) -> None:
    """Starting a rival engine against the same config is worse than starting none."""
    monkeypatch.setattr(session_shell, "_current_session", lambda: 3)
    monkeypatch.setattr(session_shell, "find_engine_processes", lambda: [EngineProcess(42, None)])
    launch = MagicMock()
    monkeypatch.setattr(session_shell, "launch_engine_hidden", launch)

    assert session_shell.ensure_engine_running(tmp_path) is None
    launch.assert_not_called()


def test_a_missing_config_still_leaves_a_usable_shell(tmp_path: Path) -> None:
    """A shell that refused to start would take the whole session down with it."""
    assert session_shell.read_launch_target(tmp_path) == ""


def test_the_configured_private_server_link_becomes_the_launch_target(tmp_path: Path) -> None:
    config = tmp_path / "config.ini"
    # utf-16, not utf-16-le: config.ini carries a BOM and the reader relies on it.
    config.write_text(
        "[General]\nPrivateServerLink=https://www.roblox.com/share?code=abc&type=Server\n",
        encoding="utf-16",
    )

    target = session_shell.read_launch_target(tmp_path)

    assert target == "https://www.roblox.com/share?code=abc&type=Server"


def test_launching_an_empty_target_is_refused_rather_than_opening_something(monkeypatch) -> None:
    startfile = MagicMock()
    monkeypatch.setattr(session_shell.os, "startfile", startfile, raising=False)

    assert session_shell.launch_game("   ") is False
    startfile.assert_not_called()


def test_launching_an_invalid_target_is_refused_without_opening_it(monkeypatch) -> None:
    startfile = MagicMock()
    monkeypatch.setattr(session_shell.os, "startfile", startfile, raising=False)

    assert session_shell.launch_game("file:///C:/Windows/System32/calc.exe") is False
    startfile.assert_not_called()


def test_the_control_window_offers_explorer_as_the_way_back(qtbot, tmp_path: Path, monkeypatch) -> None:
    start_explorer = MagicMock(return_value=True)
    monkeypatch.setattr(session_shell, "start_explorer", start_explorer)
    window = SessionShellWindow(tmp_path)
    qtbot.addWidget(window)

    window.explorer_button.click()

    start_explorer.assert_called_once()
    assert "normal desktop" in window.result_label.text()


def test_the_control_window_explains_itself_when_no_launch_target_is_set(qtbot, tmp_path: Path) -> None:
    window = SessionShellWindow(tmp_path, "")
    qtbot.addWidget(window)

    window.launch_game_button.click()

    assert "No Roblox launch target" in window.result_label.text()


def test_the_control_window_stays_on_top_so_the_escape_hatch_cannot_be_lost(
    qtbot, tmp_path: Path
) -> None:
    """This session has no taskbar, so a window that fell behind Roblox could not be recovered."""
    from PySide6.QtCore import Qt

    window = SessionShellWindow(tmp_path)
    qtbot.addWidget(window)
    flags = window.windowFlags()

    assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)
    # No minimize and no close: either one would strand or end the only way into this session.
    assert not bool(flags & Qt.WindowType.WindowMinimizeButtonHint)
    assert not bool(flags & Qt.WindowType.WindowCloseButtonHint)


def test_closing_the_control_window_is_refused(qtbot, tmp_path: Path) -> None:
    """Closing it would end the last window, the event loop, and with it the whole session."""
    window = SessionShellWindow(tmp_path)
    qtbot.addWidget(window)
    window.show()

    assert window.close() is False
    assert window.isVisible() is True


def test_the_shell_is_not_offered_without_an_installed_executable(monkeypatch, tmp_path: Path) -> None:
    """Windows logs a session off instantly when its shell cannot start, so this must fail closed."""
    monkeypatch.setattr(session_shell, "install_dir", lambda: tmp_path)

    assert session_shell.session_shell_available(tmp_path) is False


def test_the_shell_is_not_offered_for_gui_without_its_launcher(tmp_path: Path) -> None:
    from app.launcher_paths import GUI_EXE_NAME

    (tmp_path / GUI_EXE_NAME).write_bytes(b"gui")

    assert session_shell.session_shell_available(tmp_path) is False


def test_the_shell_is_offered_once_the_launcher_exists(tmp_path: Path) -> None:
    from app.launcher_paths import SESSION_SHELL_EXE_NAME

    (tmp_path / SESSION_SHELL_EXE_NAME).write_bytes(b"launcher")

    assert session_shell.session_shell_available(tmp_path) is True


def test_no_engine_is_started_when_this_processs_own_session_is_unknown(
    monkeypatch, tmp_path: Path
) -> None:
    """A known-session engine could be this shell's own; duplicating it is the worse outcome."""
    monkeypatch.setattr(session_shell, "_current_session", lambda: None)
    monkeypatch.setattr(session_shell, "find_engine_processes", lambda: [EngineProcess(42, 1)])
    launch = MagicMock()
    monkeypatch.setattr(session_shell, "launch_engine_hidden", launch)

    assert session_shell.ensure_engine_running(tmp_path) is None
    launch.assert_not_called()


def test_the_event_loop_is_still_entered_when_every_startup_step_failed(
    monkeypatch, qtbot, tmp_path: Path
) -> None:
    """Returning early from the shell logs the session off, so it must survive its own failures."""
    monkeypatch.setattr(
        session_shell, "ensure_engine_running", MagicMock(side_effect=OSError("no engine"))
    )
    monkeypatch.setattr(
        session_shell, "SessionShellWindow", MagicMock(side_effect=RuntimeError("no window"))
    )
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    explorer = MagicMock(return_value=True)
    monkeypatch.setattr(session_shell, "start_explorer", explorer)
    executed = MagicMock(return_value=0)
    application = MagicMock(exec=executed)
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    assert session_shell.run_session_shell(tmp_path) == 0
    # Explorer instead of an exit: a normal desktop beats an immediate sign-out.
    explorer.assert_called_once()
    executed.assert_called_once()
    application.setQuitOnLastWindowClosed.assert_called_once_with(False)
    log_text = (tmp_path / session_shell.SESSION_SHELL_LOG_FILE_NAME).read_text(
        encoding="utf-8"
    )
    assert "Engine startup failed: no engine" in log_text
    assert "Could not build the session control window: no window" in log_text


def test_session_shell_logs_startup_without_recording_the_private_server_link(
    monkeypatch, tmp_path: Path
) -> None:
    launch_target = "https://www.roblox.com/share?code=private-code&type=Server"
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    monkeypatch.setattr(session_shell, "ensure_engine_running", MagicMock(return_value=MagicMock()))
    launch = MagicMock(return_value=True)
    monkeypatch.setattr(session_shell, "launch_game", launch)
    monkeypatch.setattr(session_shell, "SessionShellWindow", MagicMock(return_value=MagicMock()))
    application = MagicMock(exec=MagicMock(return_value=0))
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    assert session_shell.run_session_shell(tmp_path, launch_target) == 0

    log_text = (tmp_path / session_shell.SESSION_SHELL_LOG_FILE_NAME).read_text(
        encoding="utf-8"
    )
    assert "Background session shell mode starting." in log_text
    assert "The engine was started in this session." in log_text
    assert "A Roblox launch target is configured." in log_text
    assert "Configured Roblox launch target started." in log_text
    assert "The session control window was built." in log_text
    assert launch_target not in log_text
    assert "private-code" not in log_text
    launch.assert_called_once_with(launch_target)


def test_session_shell_redacts_a_private_server_link_code_value() -> None:
    launch_target = "https://www.roblox.com/share?privateServerLinkCode=private-code&type=Server"

    redacted = session_shell._redacted_exception_text(
        RuntimeError("Roblox rejected private-code."), launch_target
    )

    assert "private-code" not in redacted
    assert "[redacted]" in redacted


def test_session_shell_excepthook_records_an_event_loop_failure(
    monkeypatch, tmp_path: Path
) -> None:
    previous_hook = MagicMock()
    monkeypatch.setattr(sys, "excepthook", previous_hook)
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: True)
    monkeypatch.setattr(session_shell, "ensure_engine_running", MagicMock(return_value=None))
    monkeypatch.setattr(session_shell, "SessionShellWindow", MagicMock(return_value=MagicMock()))
    application = MagicMock(exec=MagicMock(return_value=0))
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    session_shell.run_session_shell(tmp_path)
    error = RuntimeError("event loop failed")
    sys.excepthook(RuntimeError, error, None)

    log_text = (tmp_path / session_shell.SESSION_SHELL_LOG_FILE_NAME).read_text(
        encoding="utf-8"
    )
    assert "Unhandled session shell exception: RuntimeError: event loop failed" in log_text
    previous_hook.assert_called_once_with(RuntimeError, error, None)


# ---------------------------------------------------------------------------------------------
# The autostart mode, where this process is NOT the session's Windows shell
# ---------------------------------------------------------------------------------------------


def test_the_autostart_window_can_be_closed(qtbot, tmp_path: Path) -> None:
    """Alongside Explorer the session has a taskbar, so an unclosable window is just a nuisance."""
    from PySide6.QtGui import QCloseEvent

    window = SessionShellWindow(tmp_path, owns_session=False)
    qtbot.addWidget(window)
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted() is True


def test_the_shell_window_still_refuses_to_close(qtbot, tmp_path: Path) -> None:
    """As the shell, closing it would log the session off with no way to get the window back."""
    from PySide6.QtGui import QCloseEvent

    window = SessionShellWindow(tmp_path, owns_session=True)
    qtbot.addWidget(window)
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted() is False


def test_the_explorer_button_is_hidden_when_explorer_already_runs(qtbot, tmp_path: Path) -> None:
    window = SessionShellWindow(tmp_path, owns_session=False)
    qtbot.addWidget(window)
    window.show()

    assert window.explorer_button.isVisible() is False


def test_the_explorer_button_is_offered_as_the_way_back_from_a_shell(qtbot, tmp_path: Path) -> None:
    window = SessionShellWindow(tmp_path, owns_session=True)
    qtbot.addWidget(window)
    window.show()

    assert window.explorer_button.isVisible() is True


def test_the_autostart_window_does_not_claim_the_desktop_is_gone(qtbot, tmp_path: Path) -> None:
    """Explorer is running here, so promising "no Windows desktop" would simply be false."""
    window = SessionShellWindow(tmp_path, owns_session=False)
    qtbot.addWidget(window)

    assert "no Windows desktop" not in window.status_label.text()
    assert "normal Windows desktop" in window.status_label.text()


def test_signing_out_of_an_autostart_session_logs_the_session_off(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """Quitting Qt would close this window and leave the macro running in a logged-on session."""
    calls: list[bool] = []
    monkeypatch.setattr(
        session_shell, "sign_out_this_session", lambda: calls.append(True) or True
    )
    window = SessionShellWindow(tmp_path, owns_session=False)
    qtbot.addWidget(window)

    window.sign_out_button.click()

    assert calls == [True]


def test_a_failed_sign_out_says_so_instead_of_pretending(qtbot, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_shell, "sign_out_this_session", lambda: False)
    window = SessionShellWindow(tmp_path, owns_session=False)
    qtbot.addWidget(window)

    window.sign_out_button.click()

    assert "Could not sign this session out" in window.result_label.text()


def test_signing_out_of_a_shell_session_quits_qt(qtbot, tmp_path: Path, monkeypatch) -> None:
    """Windows logs a session off when its shell exits, so quitting IS the sign-out there."""
    quits: list[bool] = []
    monkeypatch.setattr(
        session_shell.QApplication, "quit", staticmethod(lambda: quits.append(True))
    )
    window = SessionShellWindow(tmp_path, owns_session=True)
    qtbot.addWidget(window)

    window.sign_out_button.click()

    assert quits == [True]


def test_the_autostart_mode_lets_qt_end_when_its_window_closes(
    monkeypatch, qtbot, tmp_path: Path
) -> None:
    """A process with no window left in a session that has a desktop is just an invisible process."""
    monkeypatch.setattr(session_shell, "ensure_engine_running", lambda _: None)
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    monkeypatch.setattr(session_shell, "SessionShellWindow", MagicMock(return_value=MagicMock()))
    application = session_shell.QApplication.instance()
    monkeypatch.setattr(application, "exec", lambda: 0)

    session_shell.run_session_shell(tmp_path, "", owns_session=False)

    assert application.quitOnLastWindowClosed() is True


def test_the_shell_mode_keeps_qt_alive_when_a_window_closes(
    monkeypatch, qtbot, tmp_path: Path
) -> None:
    monkeypatch.setattr(session_shell, "ensure_engine_running", lambda _: None)
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    monkeypatch.setattr(session_shell, "SessionShellWindow", MagicMock(return_value=MagicMock()))
    application = session_shell.QApplication.instance()
    monkeypatch.setattr(application, "exec", lambda: 0)

    session_shell.run_session_shell(tmp_path, "", owns_session=True)

    assert application.quitOnLastWindowClosed() is False
