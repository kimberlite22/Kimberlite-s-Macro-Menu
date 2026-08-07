"""The minimal shell the background session boots into instead of Explorer.

Windows starts exactly one program as a session's shell, and logs the session off the moment that
program exits. Pointing the .rdp "alternate shell" directive at this mode therefore does two things
at once: the background session comes up with no Explorer, no desktop and no start menu (which is
the point, and saves the RAM and CPU all of that would cost), and this process staying alive is
what keeps the session alive.

Two consequences shape everything here:

- Nothing in this mode may exit on its own. In particular the normal launch path's self-install
  step relaunches the app and returns immediately, which as a shell would log the session off a
  second after it started. `main()` skips that entirely for this mode.
- There has to be a way back to a normal desktop. With Explorer gone, a session whose shell offers
  no escape is very hard to get into and fix, so the control window below can start Explorer on
  demand. That window is the troubleshooting hatch, not a second GUI: the macro is still driven
  from the real GUI on the physical desktop, over the bridge files both sessions share.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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
from app.launcher_paths import APP_NAME, install_dir, is_frozen


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
SESSION_SHELL_FLAG = "--session-shell"


def session_shell_command(directory: Path | None = None) -> str:
    """Return the command line the .rdp alternate shell directive should point at.

    Quoted because the installed path sits under the user's profile and routinely contains spaces
    (the app name itself does), and mstsc passes this string on to Windows as a command line.
    """
    from app.self_install import installed_gui_path

    return f'"{installed_gui_path(directory)}" {SESSION_SHELL_FLAG}'


def session_shell_available(directory: Path | None = None) -> bool:
    """Whether an installed executable exists to serve as the session's shell.

    Checked before offering the option at all, because Windows logs a session off immediately when
    its shell cannot start. A source checkout and any launch that never self-installed have no
    installed exe to point at, so for them the answer is no and the session keeps Explorer.
    """
    from app.self_install import installed_gui_path

    try:
        return installed_gui_path(directory).is_file()
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
    except Exception:
        return ""


def launch_game(target: str) -> bool:
    """Open a Roblox launch target (a private server link or a roblox: URL) in this session.

    A share link resolves server side and then hands off to the Roblox protocol handler, so simply
    opening it is enough; nothing here needs to understand the link format. os.startfile is the
    shell "open" verb, which is what performs that handoff.
    """
    target = target.strip()
    if not target:
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

    def __init__(self, data_dir: Path, launch_target: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.launch_target = launch_target
        self.setWindowTitle(f"{APP_NAME} - Background Session")
        # Always on top, and deliberately WITHOUT the minimize and close buttons. This session has
        # no taskbar and no desktop, so a window that fell behind Roblox, got minimized, or was
        # closed could not be brought back, and it is the only way to reach Explorer from inside.
        # Closing it would additionally end the last window and thus the event loop, which for a
        # session shell means logging the session off by accident. "Sign out" is the deliberate way.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self._build_ui()

    def closeEvent(self, event: Any) -> None:
        """Refuse to close: only "Sign out" may end this session, and it quits Qt directly."""
        event.ignore()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.status_label = QLabel(
            "This session runs the macro engine with no Windows desktop. Control the macro from "
            "the main window on your physical desktop; these buttons are only here so this "
            "session can be fixed from the inside if something goes wrong."
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
        # Quitting IS the sign-out: Windows logs a session off when its shell exits, so there is
        # nothing else to call here. Going through Qt rather than exiting the process directly
        # lets the engine shutdown wired to aboutToQuit still run.
        QApplication.quit()


def run_session_shell(data_dir: Path, launch_target: str = "") -> int:
    """Run the background session's shell: engine, optional Roblox, and the control window.

    Every step before the event loop is best-effort, and the loop is entered even if all of them
    failed. Returning from here logs the whole session off, so "nothing worked, but the user can
    still get in and fix it" has to beat "gave up cleanly" in every case.
    """
    application = QApplication.instance()
    if application is None:
        # Nothing can keep the session alive without an event loop, so there is genuinely nothing
        # useful left to do. Callers construct the QApplication before this, so this is unreachable
        # in practice and exists only so the function has no undefined path.
        return 0
    # Qt would otherwise end the event loop when the last window closes. The control window already
    # refuses to close, and this covers the rest: a window destroyed some other way must not take
    # the session with it.
    application.setQuitOnLastWindowClosed(False)

    try:
        ensure_engine_running(data_dir)
    except Exception:
        pass
    if launch_target:
        try:
            launch_game(launch_target)
        except Exception:
            pass
    try:
        window = SessionShellWindow(data_dir, launch_target)
        window.resize(460, 200)
        window.show()
    except Exception:
        # No control window means no escape hatch, so start Explorer instead of exiting: a normal
        # desktop is a far better failure state than an immediate sign-out.
        start_explorer()
    return int(application.exec())
