from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from app import roblox_display, roblox_launch, session_commands, session_shell
from app.engine_process import EngineProcess


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


def _write_config(tmp_path: Path, body: str) -> None:
    # utf-16, not utf-16-le: config.ini carries a BOM and the reader relies on it.
    (tmp_path / "config.ini").write_text(f"[General]\n{body}\n", encoding="utf-16")


def test_roblox_is_set_to_start_fullscreen_when_the_opening_is_the_whole_screen(
    monkeypatch, tmp_path: Path
) -> None:
    _write_config(tmp_path, "FullscreenOpening=1")
    enable = MagicMock(return_value=roblox_display.FullscreenOutcome(True, True, "set"))
    monkeypatch.setattr(roblox_display, "enable_fullscreen", enable)

    assert session_shell.ensure_roblox_starts_fullscreen(tmp_path) is True
    enable.assert_called_once()


def test_roblox_settings_are_untouched_while_the_engine_positions_the_window(
    monkeypatch, tmp_path: Path
) -> None:
    """The two are one decision: a smaller opening is one the engine still moves the window into."""
    _write_config(tmp_path, "FullscreenOpening=0")
    enable = MagicMock()
    monkeypatch.setattr(roblox_display, "enable_fullscreen", enable)

    assert session_shell.ensure_roblox_starts_fullscreen(tmp_path) is False
    enable.assert_not_called()


def test_an_unreadable_config_leaves_another_applications_settings_alone(
    monkeypatch, tmp_path: Path
) -> None:
    """Failing to false: a config that cannot be read is no basis for rewriting Roblox' own file."""
    enable = MagicMock()
    monkeypatch.setattr(roblox_display, "enable_fullscreen", enable)

    assert session_shell.ensure_roblox_starts_fullscreen(tmp_path) is False
    enable.assert_not_called()


def test_a_failing_fullscreen_step_never_takes_the_session_down(monkeypatch, tmp_path: Path) -> None:
    """It runs on the shell's start-up path, where a raised exception logs the session off."""
    _write_config(tmp_path, "FullscreenOpening=1")

    def explode() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(roblox_display, "enable_fullscreen", explode)

    assert session_shell.ensure_roblox_starts_fullscreen(tmp_path) is False


def test_fullscreen_is_asserted_before_roblox_is_launched(monkeypatch, tmp_path: Path) -> None:
    """Roblox reads the setting when it starts, and nothing resizes its window afterwards."""
    order: list[str] = []
    monkeypatch.setattr(
        session_shell,
        "ensure_roblox_starts_fullscreen",
        lambda *_args, **_kwargs: order.append("fullscreen") is None,
    )
    monkeypatch.setattr(
        session_shell, "launch_game", lambda *_args, **_kwargs: order.append("launch") is None
    )
    monkeypatch.setattr(session_shell, "ensure_engine_running", lambda _directory: None)
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    application = MagicMock(exec=MagicMock(return_value=0))
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    session_shell.run_session_shell(tmp_path, "https://www.roblox.com/share?code=a&type=Server")

    assert order == ["fullscreen", "launch"]


def test_launching_an_empty_target_is_refused_rather_than_opening_something(monkeypatch) -> None:
    start_and_own = MagicMock(return_value=roblox_launch.ShellLaunch(True, None, None))
    monkeypatch.setattr(roblox_launch, "start_and_own", start_and_own)

    assert session_shell.launch_game("   ") is False
    start_and_own.assert_not_called()


def test_launching_an_invalid_target_is_refused_without_opening_it(monkeypatch) -> None:
    start_and_own = MagicMock(return_value=roblox_launch.ShellLaunch(True, None, None))
    monkeypatch.setattr(roblox_launch, "start_and_own", start_and_own)

    assert session_shell.launch_game("file:///C:/Windows/System32/calc.exe") is False
    start_and_own.assert_not_called()


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


def test_run_session_shell_keeps_qt_alive_in_both_modes(monkeypatch, tmp_path: Path) -> None:
    """With no window at all, a transient dialog closing must not end the loop or the session."""
    monkeypatch.setattr(session_shell, "ensure_engine_running", lambda _: None)
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    application = MagicMock(exec=MagicMock(return_value=0))
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    session_shell.run_session_shell(tmp_path, owns_session=True)
    session_shell.run_session_shell(tmp_path, owns_session=False)

    assert application.setQuitOnLastWindowClosed.call_args_list == [
        ((False,),),
        ((False,),),
    ]


def test_run_session_shell_installs_and_starts_the_command_timer(monkeypatch, tmp_path: Path) -> None:
    class Timer:
        def __init__(self) -> None:
            self.timeout = MagicMock()
            self.timeout.connect = MagicMock()
            self.interval = None
            self.started = False

        def setInterval(self, interval: int) -> None:
            self.interval = interval

        def start(self) -> None:
            self.started = True

    timer = Timer()
    monkeypatch.setattr(session_shell, "QTimer", lambda *_args: timer)
    monkeypatch.setattr(session_shell, "ensure_engine_running", lambda _: None)
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    application = MagicMock(exec=MagicMock(return_value=0))
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    session_shell.run_session_shell(tmp_path)

    assert timer.interval == 500
    assert timer.started is True
    assert timer.timeout.connect.call_count == 1


def test_serve_session_command_dispatches_explorer_and_acknowledges(monkeypatch, tmp_path: Path) -> None:
    token = "explorer-token"
    monkeypatch.setattr(
        session_commands, "take_command", lambda *_: (token, session_commands.START_EXPLORER)
    )
    explorer = MagicMock(return_value=True)
    ack = MagicMock()
    monkeypatch.setattr(session_shell, "start_explorer", explorer)
    monkeypatch.setattr(session_commands, "write_ack", ack)

    session_shell._serve_session_command(tmp_path, "")

    explorer.assert_called_once()
    assert ack.call_args.args[:3] == (tmp_path, token, True)
    assert "Explorer started" in ack.call_args.args[3]


def test_serve_session_command_asks_for_this_sessions_own_commands_only(
    monkeypatch, tmp_path: Path
) -> None:
    """The id it passes is what stops a stopped session's command running in its replacement."""
    monkeypatch.setattr(session_shell, "_current_session", lambda: 7)
    seen: list[object] = []
    monkeypatch.setattr(
        session_commands,
        "take_command",
        lambda _directory, own_session: seen.append(own_session) or None,
    )

    session_shell._serve_session_command(tmp_path, "")

    assert seen == [7]


def test_serve_session_command_reasserts_fullscreen_before_roblox(monkeypatch, tmp_path: Path) -> None:
    order: list[str] = []
    monkeypatch.setattr(
        session_commands,
        "take_command",
        lambda *_: ("roblox-token", session_commands.START_ROBLOX),
    )
    monkeypatch.setattr(
        session_shell,
        "ensure_roblox_starts_fullscreen",
        lambda *_: order.append("fullscreen"),
    )
    monkeypatch.setattr(
        session_shell, "launch_game", lambda *_args, **_kwargs: order.append("launch") or True
    )
    ack = MagicMock()
    monkeypatch.setattr(session_commands, "write_ack", ack)

    session_shell._serve_session_command(tmp_path, "https://www.roblox.com/share?code=a&type=Server")

    assert order == ["fullscreen", "launch"]
    assert ack.call_args.args[:3] == (tmp_path, "roblox-token", True)


def test_serve_session_command_acks_missing_roblox_target(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        session_commands,
        "take_command",
        lambda *_: ("roblox-token", session_commands.START_ROBLOX),
    )
    ack = MagicMock()
    monkeypatch.setattr(session_commands, "write_ack", ack)

    session_shell._serve_session_command(tmp_path, "")

    assert ack.call_args.args[:3] == (tmp_path, "roblox-token", False)
    assert "No Roblox launch target" in ack.call_args.args[3]


def test_serve_session_command_swallows_an_explorer_exception(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        session_commands,
        "take_command",
        lambda *_: ("explorer-token", session_commands.START_EXPLORER),
    )
    monkeypatch.setattr(session_shell, "start_explorer", MagicMock(side_effect=RuntimeError("boom")))
    ack = MagicMock()
    monkeypatch.setattr(session_commands, "write_ack", ack)

    session_shell._serve_session_command(tmp_path, "")

    assert ack.call_args.args[:3] == (tmp_path, "explorer-token", False)
    assert ack.call_args.args[3] == "Could not handle the session command."
    assert "Session command handling failed: boom" in (
        tmp_path / session_shell.SESSION_SHELL_LOG_FILE_NAME
    ).read_text(encoding="utf-8")


def test_the_event_loop_is_still_entered_when_every_startup_step_failed(
    monkeypatch, tmp_path: Path
) -> None:
    """Returning early from the shell logs the session off, so it must survive its own failures."""
    monkeypatch.setattr(
        session_shell, "ensure_engine_running", MagicMock(side_effect=OSError("no engine"))
    )
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    monkeypatch.setattr(
        session_shell, "QTimer", MagicMock(side_effect=RuntimeError("no timer"))
    )
    explorer = MagicMock(return_value=True)
    monkeypatch.setattr(session_shell, "start_explorer", explorer)
    executed = MagicMock(return_value=0)
    application = MagicMock(exec=executed)
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    assert session_shell.run_session_shell(tmp_path) == 0
    # Explorer instead of an exit: the channel is the way into this session, so losing it leaves
    # a normal desktop as the best remaining failure state, exactly as a lost window used to.
    explorer.assert_called_once()
    executed.assert_called_once()
    application.setQuitOnLastWindowClosed.assert_called_once_with(False)
    log_text = (tmp_path / session_shell.SESSION_SHELL_LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "Engine startup failed: no engine" in log_text
    assert "Could not install the session command channel: no timer" in log_text
    assert "Explorer fallback started." in log_text


def test_a_lost_command_channel_starts_no_explorer_alongside_one(
    monkeypatch, tmp_path: Path
) -> None:
    """Explorer is already running in autostart mode, so there is nothing there to recover."""
    monkeypatch.setattr(session_shell, "ensure_engine_running", lambda _: None)
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    monkeypatch.setattr(session_shell, "QTimer", MagicMock(side_effect=RuntimeError("no timer")))
    explorer = MagicMock(return_value=True)
    monkeypatch.setattr(session_shell, "start_explorer", explorer)
    application = MagicMock(exec=MagicMock(return_value=0))
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    session_shell.run_session_shell(tmp_path, owns_session=False)

    explorer.assert_not_called()


def test_session_shell_logs_startup_without_recording_the_private_server_link(
    monkeypatch, tmp_path: Path
) -> None:
    launch_target = "https://www.roblox.com/share?code=private-code&type=Server"
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: False)
    monkeypatch.setattr(session_shell, "ensure_engine_running", MagicMock(return_value=MagicMock()))
    launch = MagicMock(return_value=True)
    monkeypatch.setattr(session_shell, "launch_game", launch)
    application = MagicMock(exec=MagicMock(return_value=0))
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    assert session_shell.run_session_shell(tmp_path, launch_target) == 0

    log_text = (tmp_path / session_shell.SESSION_SHELL_LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "Background session shell mode starting." in log_text
    assert "The engine was started in this session." in log_text
    assert "A Roblox launch target is configured." in log_text
    assert "Configured Roblox launch target started." in log_text
    assert "The session command channel is being served." in log_text
    assert launch_target not in log_text
    assert "private-code" not in log_text
    assert launch.call_count == 1
    assert launch.call_args.args == (launch_target,)
    # The launch reports what it did through this sink, so it writes into the same log the
    # assertions above cover: whatever it says, it may not say the link.
    assert callable(launch.call_args.kwargs["log"])


def test_session_shell_redacts_a_private_server_link_code_value() -> None:
    launch_target = "https://www.roblox.com/share?privateServerLinkCode=private-code&type=Server"

    redacted = session_shell._redacted_exception_text(
        RuntimeError("Roblox rejected private-code."), launch_target
    )

    assert "private-code" not in redacted
    assert "[redacted]" in redacted


def test_session_shell_excepthook_records_an_event_loop_failure(monkeypatch, tmp_path: Path) -> None:
    previous_hook = MagicMock()
    monkeypatch.setattr(sys, "excepthook", previous_hook)
    monkeypatch.setattr(session_shell, "_engine_is_already_running_here", lambda: True)
    monkeypatch.setattr(session_shell, "ensure_engine_running", MagicMock(return_value=None))
    application = MagicMock(exec=MagicMock(return_value=0))
    monkeypatch.setattr(session_shell.QApplication, "instance", staticmethod(lambda: application))

    session_shell.run_session_shell(tmp_path)
    error = RuntimeError("event loop failed")
    sys.excepthook(RuntimeError, error, None)

    assert "Unhandled session shell exception: RuntimeError: event loop failed" in (
        tmp_path / session_shell.SESSION_SHELL_LOG_FILE_NAME
    ).read_text(encoding="utf-8")
    previous_hook.assert_called_once_with(RuntimeError, error, None)
