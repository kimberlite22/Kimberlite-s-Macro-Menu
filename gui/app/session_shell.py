"""What the background session boots into: the engine, Roblox, and a small control window.

There are two ways to reach this, and the difference between them is `owns_session`.

As the session's SHELL (`owns_session=True`), reached through the .rdp "alternate shell" directive.
Windows starts exactly one program as a session's shell and logs the session off the moment that
program exits, so this does two things at once: the session comes up with no Explorer, no desktop
and no start menu (which is the point, and saves the RAM and CPU all of that would cost), and this
process staying alive is what keeps the session alive. Two consequences shape the code:

- Nothing in this mode may exit on its own. In particular the normal launch path's self-install
  step relaunches the app and returns immediately, which as a shell would log the session off a
  second after it started. `main()` skips that entirely for this mode.
- There has to be a way back to a normal desktop. With Explorer gone, a session whose shell offers
  no escape is very hard to get into and fix, so the control window below can start Explorer on
  demand.

As an AUTOSTART program (`owns_session=False`), reached through the HKCU Run entry in
session_autostart.py. That route needs no administrator rights and is the one available when the
alternate shell is blocked, but Explorer starts too, so this process is an ordinary program in an
ordinary session. Exiting it does not end the session, there is no desktop to restore, and the
window must not claim otherwise: every button below that would mean something different here is
either relabelled or not shown.

In both modes this window is a troubleshooting hatch, not a second GUI: the macro is still driven
from the real GUI on the physical desktop, over the bridge files both sessions share.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.engine_process import (
    find_engine_executable,
    find_engine_processes,
    launch_engine_hidden,
)
from app.launcher_paths import APP_NAME, install_dir, is_frozen, session_shell_exe_path
from app.private_server_link import validation_error


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
    always start Roblox from the control window instead.
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


def launch_game(target: str) -> bool:
    """Open a configured private server link in this session.

    A share link resolves server side and then hands off to the Roblox protocol handler, so simply
    opening it is enough; nothing here needs to understand the link format. os.startfile is the
    shell "open" verb, which is what performs that handoff.
    """
    target = target.strip()
    if not target:
        # Checked separately from the validator below, which treats an empty link as VALID because
        # there it means "no private server configured, keep today's behavior". Here that same
        # value would reach os.startfile("") instead, so it has to be its own refusal.
        return False
    if validation_error(target) is not None:
        # config.ini can be hand-edited, so only a validated target may reach os.startfile.
        return False
    try:
        os.startfile(target)  # noqa: S606 - the shell open verb is exactly what launches Roblox
        return True
    except (AttributeError, OSError, ValueError):
        return False


def start_explorer() -> bool:
    """Start Explorer so this session has a normal desktop again, for troubleshooting."""
    try:
        subprocess.Popen(["explorer.exe"], creationflags=DETACHED_PROCESS)
        return True
    except OSError:
        return False


def sign_out_this_session() -> bool:
    """Log this Windows session off, for the mode where exiting would not do it by itself.

    Imported lazily: background_session.py is the console side's module and pulling it in at import
    time would make every session-shell launch pay for machinery it does not otherwise touch.
    """
    try:
        from app.background_session import logoff_session

        session = _current_session()
        if session is None:
            return False
        return logoff_session(session)
    except Exception:
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
        # is worse than starting none: the control window can still launch what is missing.
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


class SessionShellWindow(QWidget):
    """The small control window that doubles as this session's escape hatch."""

    def __init__(
        self,
        data_dir: Path,
        launch_target: str = "",
        parent: QWidget | None = None,
        *,
        owns_session: bool = True,
    ) -> None:
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.launch_target = launch_target
        self.owns_session = owns_session
        self.setWindowTitle(f"{APP_NAME} - Background Session")
        flags = Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        if owns_session:
            # Always on top, and deliberately WITHOUT the minimize and close buttons. As the
            # session's shell there is no taskbar and no desktop, so a window that fell behind
            # Roblox, got minimized, or was closed could not be brought back, and it is the only
            # way to reach Explorer from inside. Closing it would additionally end the last window
            # and thus the event loop, which for a session shell means logging the session off by
            # accident. "Sign out" is the deliberate way.
            flags |= Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        self.setWindowFlags(flags)
        self._build_ui()

    def closeEvent(self, event: Any) -> None:
        """Refuse to close only while this window IS the session's shell.

        There the close button would log the session off by accident and there is no taskbar to get
        the window back from, so "Sign out" is made the only deliberate way out. Alongside Explorer
        none of that applies: the session has a taskbar, closing this window ends nothing but this
        window, and refusing would just be an unclosable window sitting on top of everything.
        """
        if self.owns_session:
            event.ignore()
            return
        super().closeEvent(event)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.status_label = QLabel(
            "This session runs the macro engine with no Windows desktop. Control the macro from "
            "the main window on your physical desktop; these buttons are only here so this "
            "session can be fixed from the inside if something goes wrong."
            if self.owns_session
            else "This session runs the macro engine and keeps a normal Windows desktop. Control "
            "the macro from the main window on your physical desktop; these buttons are only "
            "here so this session can be fixed from the inside if something goes wrong."
        )
        self.status_label.setObjectName("session_shell_status_label")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.result_label = QLabel("")
        self.result_label.setObjectName("session_shell_result_label")
        self.result_label.setWordWrap(True)
        root.addWidget(self.result_label)

        buttons = QHBoxLayout()
        self.launch_game_button = QPushButton("Start Roblox")
        self.launch_game_button.setObjectName("session_shell_launch_game_button")
        self.explorer_button = QPushButton("Start Explorer")
        self.explorer_button.setObjectName("session_shell_explorer_button")
        self.explorer_button.setToolTip(
            "Troubleshooting only. Gives this session a normal Windows desktop, which it "
            "deliberately does not have."
        )
        # Explorer is already running in the autostart mode, so the button would do nothing a user
        # could observe. Kept as an attribute either way so the widget lookups in the tests and the
        # handlers below do not have to care which mode built the window.
        self.explorer_button.setVisible(self.owns_session)
        self.sign_out_button = QPushButton("Sign out")
        self.sign_out_button.setObjectName("session_shell_sign_out_button")
        self.sign_out_button.setToolTip(
            "Ends this background session. Everything running in it, including the macro, stops."
        )
        for button in (self.launch_game_button, self.explorer_button, self.sign_out_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        root.addLayout(buttons)

        self.launch_game_button.clicked.connect(self._launch_game)
        self.explorer_button.clicked.connect(self._start_explorer)
        self.sign_out_button.clicked.connect(self._sign_out)

    def _launch_game(self) -> None:
        if not self.launch_target:
            self.result_label.setText(
                "No Roblox launch target is configured, so Roblox has to be started another way. "
                "Set a private server link in the main window's settings to launch it from here."
            )
            return
        ok = launch_game(self.launch_target)
        self.result_label.setText("Starting Roblox." if ok else "Could not start Roblox.")

    def _start_explorer(self) -> None:
        ok = start_explorer()
        self.result_label.setText(
            "Explorer started; this session now has a normal desktop."
            if ok
            else "Could not start Explorer."
        )

    def _sign_out(self) -> None:
        if self.owns_session:
            # Quitting IS the sign-out: Windows logs a session off when its shell exits, so there
            # is nothing else to call here. Going through Qt rather than exiting the process
            # directly lets the engine shutdown wired to aboutToQuit still run.
            QApplication.quit()
            return
        # Alongside Explorer this process is not the shell, so quitting would close this window and
        # leave the session logged on with the macro still running in it. The button says "Ends
        # this background session", so end it: ask Windows to log this session off by id, the same
        # call the main window's Stop button makes from the other side.
        if not sign_out_this_session():
            self.result_label.setText(
                "Could not sign this session out. Use Stop in the main window on your physical "
                "desktop instead."
            )


def run_session_shell(
    data_dir: Path, launch_target: str = "", *, owns_session: bool = True
) -> int:
    """Run the background session's macro side: engine, optional Roblox, and the control window.

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
    # As the shell, Qt would otherwise end the event loop when the last window closes. The control
    # window already refuses to close, and this covers the rest: a window destroyed some other way
    # must not take the session with it. In autostart mode the window CAN be closed on purpose, and
    # a process with no window left is then just an invisible process, so let Qt end it.
    application.setQuitOnLastWindowClosed(not owns_session)

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

    if launch_target.strip():
        _log_session_shell(data_dir, "A Roblox launch target is configured.")
        try:
            launched = launch_game(launch_target)
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
        window = SessionShellWindow(data_dir, launch_target, owns_session=owns_session)
        window.resize(460, 200)
        window.show()
        _log_session_shell(data_dir, "The session control window was built.")
    except Exception as error:
        _log_session_shell(
            data_dir,
            "Could not build the session control window: "
            f"{_redacted_exception_text(error, launch_target)}",
        )
        # As the shell, no control window means no escape hatch, so start Explorer instead of
        # exiting: a normal desktop is a far better failure state than an immediate sign-out. In
        # autostart mode Explorer is already there, so there is nothing to recover.
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
