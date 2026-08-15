"""What the background session boots into: the engine, Roblox, and a command channel.

There are two ways to reach this, and the difference between them is `owns_session`.

As the session's SHELL (`owns_session=True`), reached through the .rdp "alternate shell" directive.
Windows starts exactly one program as a session's shell and logs the session off the moment that
program exits, so this does two things at once: the session comes up with no Explorer, no desktop
and no start menu (which is the point, and saves the RAM and CPU all of that would cost), and this
process staying alive is what keeps the session alive. Two consequences shape the code:

- Nothing in this mode may exit on its own. In particular the normal launch path's self-install
  step relaunches the app and returns immediately, which as a shell would log the session off a
  second after it started. `main()` skips that entirely for this mode.
- The physical desktop's main window can ask this process to start Explorer through a local command
  channel. The process already runs inside this session, which avoids needing administrator rights
  to start a process across sessions.

As an AUTOSTART program (`owns_session=False`), reached through the HKCU Run entry in
session_autostart.py. That route needs no administrator rights and is the one available when the
alternate shell is blocked, but Explorer starts too, so this process is an ordinary program in an
ordinary session. Exiting it does not end the session and there is no desktop to restore, but the
same command channel still reaches the macro process that runs inside that session.

In both modes this headless process is still recoverable without a window. The main window's
Background Session tab can start Explorer inside the session through the command channel, and its
Stop button can always end the session outright through Windows itself, independently of anything
running in the session.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.engine_process import (
    find_engine_executable,
    find_engine_processes,
    launch_engine_hidden,
)
from app import roblox_display, roblox_launch
from app import session_commands
from app.launcher_paths import install_dir, is_frozen, session_shell_exe_path


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
SESSION_SHELL_FLAG = "--session-shell"
SESSION_SHELL_LOG_FILE_NAME = "session_shell_log.txt"


def _log_session_shell(data_directory: Path, message: str) -> None:
    """Append diagnostic evidence without ever risking the session shell's lifetime."""
    try:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        path = Path(data_directory) / SESSION_SHELL_LOG_FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{timestamp} {message}\n")
    except Exception:
        pass


def _redacted_exception_text(error: BaseException, launch_target: str = "") -> str:
    """Return exception text without retaining a configured private-server secret in the log."""
    try:
        text = str(error).replace("\r", " ").replace("\n", " ")
        redactions = [launch_target]
        if launch_target:
            redactions.extend(
                value
                for name, value in parse_qsl(urlsplit(launch_target).query, keep_blank_values=True)
                if "code" in name.casefold()
            )
        for value in redactions:
            if value:
                text = text.replace(value, "[redacted]")
        return re.sub(r"https?://\S+", "[redacted]", text, flags=re.IGNORECASE)
    except Exception:
        return error.__class__.__name__


def _install_session_shell_excepthook(data_directory: Path, launch_target: str) -> None:
    """Record event-loop crashes that otherwise log off the whole background session."""
    try:
        previous_hook = sys.excepthook

        def log_unhandled_exception(
            error_type: type[BaseException], error: BaseException, traceback: Any
        ) -> None:
            _log_session_shell(
                data_directory,
                f"Unhandled session shell exception: {error_type.__name__}: "
                f"{_redacted_exception_text(error, launch_target)}",
            )
            try:
                previous_hook(error_type, error, traceback)
            except Exception:
                pass

        sys.excepthook = log_unhandled_exception
    except Exception as error:
        _log_session_shell(
            data_directory,
            "Could not install the session shell exception hook: "
            f"{_redacted_exception_text(error)}",
        )


def _engine_is_already_running_here() -> bool:
    """Mirror ensure_engine_running's ownership rule so its startup outcome can be logged."""
    own_session = _current_session()
    engines = find_engine_processes()
    if own_session is None:
        return bool(engines)
    return any(
        process.session_id is None or process.session_id == own_session for process in engines
    )


def session_shell_command(directory: Path | None = None) -> str:
    """Return the application name the .rdp alternate shell directive must start.

    RDP hands this value to CreateProcess as the application name, not as a command line. It
    therefore cannot carry quotes or arguments. The separate launcher executable communicates
    session-shell mode through its name instead.
    """
    return str(session_shell_exe_path(directory))


def session_shell_available(directory: Path | None = None) -> bool:
    """Whether an installed executable exists to serve as the session's shell.

    Checked before offering the option at all, because Windows logs a session off immediately when
    its shell cannot start. A source checkout and any launch that never self-installed have no
    installed session-shell launcher to point at, so for them the answer is no and the session
    keeps Explorer.
    """
    try:
        return session_shell_exe_path(directory).is_file()
    except (OSError, ValueError):
        return False


def read_launch_target(data_directory: Path) -> str:
    """Return the configured private server link, or "" when there is none.

    Best effort on purpose: a config this session cannot read must still leave a working shell
    behind, since a shell that refuses to start takes the whole session with it. The user can
    always start Roblox from the main window's Background Session tab instead.
    """
    from ipc.config_reader import read_config

    try:
        return read_config(Path(data_directory) / "config.ini").general.private_server_link.strip()
    except Exception as error:
        _log_session_shell(
            data_directory,
            f"Could not read the Roblox launch target: {_redacted_exception_text(error)}",
        )
        return ""


def read_fullscreen_opening(data_directory: Path) -> bool:
    """Whether the opening is configured to be the whole screen.

    This is the gate for touching Roblox' own fullscreen setting, and it is the same value the
    engine gates on (FullscreenOpeningEnabled() in tower_defense_macro_gui.ahk). The two have to
    agree, because they are two halves of one decision: the engine only stops asserting the game
    window's geometry in a background session while the opening IS the whole screen, and a full
    screen Roblox is only the right window for the macro's stored coordinates under exactly that
    same condition. With the option off the opening is a smaller rectangle the engine still moves
    the window into, and making Roblox full screen would fight it.

    Best effort like read_launch_target above, and it fails to FALSE: a config this session cannot
    read is not a reason to rewrite a file belonging to another application.
    """
    from ipc.config_reader import read_config

    try:
        return bool(read_config(Path(data_directory) / "config.ini").general.fullscreen_opening)
    except Exception as error:
        _log_session_shell(
            data_directory,
            "Could not read whether the opening is the whole screen, so Roblox' fullscreen "
            f"setting was left alone: {_redacted_exception_text(error)}",
        )
        return False


def ensure_roblox_starts_fullscreen(
    data_directory: Path, *, log: Callable[[str], None] | None = None
) -> bool:
    """Make the next Roblox launch in this session come up full screen by itself.

    Called before Roblox is started rather than after its window appears, which is the whole point:
    the engine no longer moves or resizes the game window in a background session, so nothing is
    going to correct a window that came up the wrong size. The size has to be right at launch.

    Returns whether Roblox will start full screen. Never raises: this sits on the session start-up
    path, where a shell that dies takes the session with it.
    """
    sink: Callable[[str], None] = log if log is not None else (
        lambda message: _log_session_shell(data_directory, message)
    )
    try:
        if not read_fullscreen_opening(data_directory):
            sink(
                "The opening is not the whole screen, so Roblox' own fullscreen setting was left "
                "alone and the engine keeps positioning the window."
            )
            return False
        outcome = roblox_display.enable_fullscreen()
        sink(outcome.message)
        return outcome.ready
    except Exception as error:
        sink(f"Could not set Roblox to start full screen: {_redacted_exception_text(error)}")
        return False


def launch_game(target: str, *, log: Callable[[str], None] | None = None) -> bool:
    """Open a configured private server link in this session.

    Stays this module's entry point, because both command handling and the session start-up path
    below launch Roblox through it. HOW that happens belongs to roblox_launch: a ``roblox://``
    protocol link wherever one can be built, so no browser is opened at all, and the browser only as
    a fallback that is closed again once Roblox is up.

    Returns whether a launch was STARTED. The rest runs on a worker thread, since this is called
    both before the event loop starts and from the Qt GUI thread, and neither may block.
    """
    return roblox_launch.launch_game(target, log=log)


def start_explorer() -> bool:
    """Start Explorer so this session has a normal desktop again, for troubleshooting."""
    try:
        subprocess.Popen(["explorer.exe"], creationflags=DETACHED_PROCESS)
        return True
    except OSError:
        return False


def ensure_engine_running(data_directory: Path) -> subprocess.Popen[Any] | None:
    """Start the engine in this session unless one is already running here.

    Returns the handle only when this call actually spawned it. Note the deliberate difference from
    main.py: it looks for an engine in ANY session, because a GUI on the physical desktop should
    attach to a background session's engine rather than start a rival. Here the opposite is true.
    This IS the background session, so an engine belonging to some other session is not ours to
    use, and the session would otherwise come up with nothing driving it.
    """
    own_session = _current_session()
    engines = find_engine_processes()
    if own_session is None and engines:
        # Fails closed. Without knowing this session's own id, an engine reported here cannot be
        # told apart from this shell's own, and starting a second one against the same config.ini
        # is worse than starting none: the command channel can still launch what is missing.
        return None
    for process in engines:
        if process.session_id is None or process.session_id == own_session:
            return None
    engine_argv = find_engine_executable(install_dir() if is_frozen() else None)
    if engine_argv is None:
        return None
    return launch_engine_hidden(engine_argv, data_directory)


def _current_session() -> int | None:
    from app.engine_process import current_session_id

    return current_session_id()


def _serve_session_command(data_directory: Path, launch_target: str) -> None:
    """Serve one command without allowing an event-loop exception to end the Windows session.

    Every message written back from here is rendered by the main window on the PHYSICAL desktop, not
    by anything in this session, so each one says which session it is talking about rather than
    "this session".
    """
    token: str | None = None
    try:
        # Addressed to this Windows session by id, so a command aimed at a background session the
        # user has since stopped is not carried out by the one that replaced it.
        command = session_commands.take_command(data_directory, _current_session())
        if command is None:
            return
        token, verb = command
        if verb == session_commands.START_EXPLORER:
            ok = start_explorer()
            message = (
                "Explorer started; the background session now has a normal desktop."
                if ok
                else "Could not start Explorer in the background session."
            )
        elif verb == session_commands.START_ROBLOX and not launch_target.strip():
            ok = False
            message = (
                "No Roblox launch target is configured, so the background session has nothing to "
                "launch. Set a private server link in the General tab to start Roblox from here."
            )
        elif verb == session_commands.START_ROBLOX:
            # Roblox rewrites its settings file when it exits, so start-up's earlier setting can no
            # longer be trusted after a prior launch inside this session.
            ensure_roblox_starts_fullscreen(data_directory)
            ok = launch_game(
                launch_target, log=lambda message: _log_session_shell(data_directory, message)
            )
            # "Starting", not "started": the launch continues on a worker thread, which may still
            # have to resolve a share code, wait for Roblox and close a browser. What it did lands
            # in session_shell_log.txt, which is where anything about this session is looked up.
            message = (
                "Starting Roblox in the background session."
                if ok
                else "Could not start Roblox in the background session."
            )
        else:
            ok = False
            message = "Could not handle an unknown session command."
        session_commands.write_ack(data_directory, token, ok, message)
        _log_session_shell(data_directory, message)
    except Exception as error:
        if token is not None:
            try:
                session_commands.write_ack(
                    data_directory, token, False, "Could not handle the session command."
                )
            except Exception:
                pass
        _log_session_shell(
            data_directory,
            "Session command handling failed: "
            f"{_redacted_exception_text(error, launch_target)}",
        )


def run_session_shell(
    data_dir: Path, launch_target: str = "", *, owns_session: bool = True
) -> int:
    """Run the background session's macro side: engine, optional Roblox, and command handling.

    Every step before the event loop is best-effort, and the loop is entered even if all of them
    failed. As the session's shell (`owns_session`), returning from here logs the whole session off,
    so "nothing worked, but the user can still get in and fix it" has to beat "gave up cleanly" in
    every case. Alongside Explorer the stakes are lower, but the behaviour is kept identical: a
    half-started background session is worth leaving reachable either way.
    """
    _install_session_shell_excepthook(data_dir, launch_target)
    _log_session_shell(
        data_dir,
        "Background session shell mode starting."
        if owns_session
        else "Background session autostart mode starting (Explorer is running too).",
    )
    application = QApplication.instance()
    if application is None:
        # Nothing can keep the session alive without an event loop, so there is genuinely nothing
        # useful left to do. Callers construct the QApplication before this, so this is unreachable
        # in practice and exists only so the function has no undefined path.
        _log_session_shell(data_dir, "No QApplication instance was available.")
        return 0
    # With no window this is a headless background process. A transient dialog opening and closing
    # must not end the event loop and, in shell mode, the whole Windows session.
    application.setQuitOnLastWindowClosed(False)

    try:
        engine_was_running = _engine_is_already_running_here()
        engine_process = ensure_engine_running(data_dir)
        if engine_was_running:
            _log_session_shell(data_dir, "An engine was already running in this session.")
        elif engine_process is not None:
            _log_session_shell(data_dir, "The engine was started in this session.")
        else:
            _log_session_shell(data_dir, "The engine was not started.")
    except Exception as error:
        _log_session_shell(data_dir, f"Engine startup failed: {_redacted_exception_text(error)}")

    # Before the launch below and before a command can request one, because
    # Roblox reads this setting when it starts: a session that launched Roblox first would get a
    # windowed client that nothing here is going to resize any more.
    ensure_roblox_starts_fullscreen(data_dir)

    if launch_target.strip():
        _log_session_shell(data_dir, "A Roblox launch target is configured.")
        try:
            launched = launch_game(
                launch_target, log=lambda message: _log_session_shell(data_dir, message)
            )
            _log_session_shell(
                data_dir,
                "Configured Roblox launch target started."
                if launched
                else "Configured Roblox launch target could not be started.",
            )
        except Exception as error:
            _log_session_shell(
                data_dir,
                f"Roblox launch failed: {_redacted_exception_text(error, launch_target)}",
            )
    else:
        _log_session_shell(data_dir, "No Roblox launch target is configured.")
    try:
        # Deliberately unparented and held on this frame instead: the frame lives for as long as
        # the event loop below does, which is this process's whole life, and a Qt parent here would
        # buy nothing beyond that.
        command_timer = QTimer()
        command_timer.setInterval(500)
        command_timer.timeout.connect(
            lambda: _serve_session_command(data_dir, launch_target)
        )
        command_timer.start()
        _log_session_shell(data_dir, "The session command channel is being served.")
    except Exception as error:
        _log_session_shell(
            data_dir,
            "Could not install the session command channel: "
            f"{_redacted_exception_text(error, launch_target)}",
        )
        # The channel IS the way into this session now, so failing to install it is the same
        # situation the control window's own build failure used to be: as the shell, start Explorer
        # rather than exiting, because a session with a normal desktop is a far better failure state
        # than one that signs itself out. In autostart mode Explorer is already there.
        if owns_session:
            try:
                explorer_started = start_explorer()
                _log_session_shell(
                    data_dir,
                    "Explorer fallback started."
                    if explorer_started
                    else "Explorer fallback could not be started.",
                )
            except Exception as explorer_error:
                _log_session_shell(
                    data_dir,
                    f"Explorer fallback failed: {_redacted_exception_text(explorer_error)}",
                )
    return int(application.exec())
