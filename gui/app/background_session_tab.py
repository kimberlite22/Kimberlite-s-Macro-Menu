"""Background Session tab: start, show and stop the hidden background Windows session."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import background_session, rdp_wrapper, session_shell, window_branding
from app.launcher_paths import APP_NAME, app_icon_path, install_dir
from app.widgets import FormLayout


class BackgroundSessionTab(QWidget):
    """Lets the user run the macro in a second, hidden Windows session, physical desktop free."""

    def __init__(
        self,
        data_dir: Path,
        parent: QWidget | None = None,
        *,
        entry_file: Path | None = None,
        check_setup: object | None = None,
        thread_starter: object = threading.Thread,
    ) -> None:
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self._entry_file = entry_file
        self._branding_cancel: threading.Event | None = None
        self._branding_thread: threading.Thread | None = None
        self._branding_process: object | None = None
        # Injectable so the tab's own tests can drive every setup verdict without needing the real
        # machine to be in that state; production always uses the real detection.
        self._check_setup = check_setup or rdp_wrapper.check_setup
        # Injectable so tests do not start a real worker while they verify the tab's lifecycle.
        self._thread_starter = thread_starter
        self._can_start = False
        self._build_ui()
        self._refresh_setup()
        self._refresh_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        description = QLabel(
            "Runs the macro in a second Windows session so the physical desktop stays free for "
            "other work. This needs RDP Wrapper, a third-party tool that is deliberately not "
            "bundled with this app: several antivirus products flag it, which would break the "
            "app's own updates. Installing it needs administrator rights and a reboot. Note that "
            "running several sessions at once on a Windows client edition goes beyond what "
            "Microsoft's licensing intends."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        setup = QGroupBox("Setup")
        setup_layout = QVBoxLayout(setup)
        self.setup_summary_label = QLabel()
        self.setup_summary_label.setObjectName("background_session_setup_summary_label")
        self.setup_summary_label.setWordWrap(True)
        setup_layout.addWidget(self.setup_summary_label)
        self.setup_details_label = QLabel()
        self.setup_details_label.setObjectName("background_session_setup_details_label")
        self.setup_details_label.setWordWrap(True)
        setup_layout.addWidget(self.setup_details_label)
        recheck_row = QHBoxLayout()
        self.recheck_button = QPushButton("Re-check")
        self.recheck_button.setObjectName("background_session_recheck_button")
        self.recheck_button.setToolTip(
            "Runs the four setup checks again. Use it after installing RDP Wrapper and rebooting, "
            "or after changing one of the settings named above."
        )
        recheck_row.addWidget(self.recheck_button)
        recheck_row.addStretch(1)
        setup_layout.addLayout(recheck_row)
        root.addWidget(setup)

        credentials = QGroupBox("Sign-in credential")
        credentials_layout = QVBoxLayout(credentials)
        form = FormLayout()
        self.username_edit = QLineEdit(os.environ.get("USERNAME", ""))
        self.username_edit.setObjectName("background_session_username_edit")
        self.username_edit.setToolTip(
            "The Windows account to sign in to the background session with - normally this "
            "account, already filled in."
        )
        form.addRow("Username", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("background_session_password_edit")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setToolTip(
            "Only needed once: click Save Credential to store it in Windows Credential Manager, "
            "then leave this blank. Never written to config.ini or anywhere else this app persists."
        )
        form.addRow("Password", self.password_edit)
        credentials_layout.addLayout(form)

        credential_actions = QHBoxLayout()
        self.save_credential_button = QPushButton("Save Credential")
        self.save_credential_button.setObjectName("background_session_save_credential_button")
        self.forget_credential_button = QPushButton("Forget Credential")
        self.forget_credential_button.setObjectName("background_session_forget_credential_button")
        credential_actions.addWidget(self.save_credential_button)
        credential_actions.addWidget(self.forget_credential_button)
        credential_actions.addStretch(1)
        credentials_layout.addLayout(credential_actions)
        root.addWidget(credentials)

        self.status_label = QLabel("Background session: unknown.")
        self.status_label.setObjectName("background_session_status_label")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.minimal_shell_checkbox = QCheckBox()
        self.minimal_shell_checkbox.setObjectName("background_session_minimal_shell")
        minimal_shell_label = QLabel("Boot straight into the macro, with no Windows desktop")
        minimal_shell_label.setBuddy(self.minimal_shell_checkbox)
        minimal_shell_tooltip = (
            "Starts the background session with this app as its Windows shell instead of Explorer, "
            "so the session holds only Roblox and the macro engine: no desktop, no start menu, "
            "less memory and CPU used in the background. A small control window inside that "
            "session can bring Explorer back if you ever need to fix something there."
        )
        # Only offered when there is an installed executable to point the session's shell at.
        # Windows logs a session off the instant its shell fails to start, so an unavailable shell
        # must not merely fail later: it must never be selectable. A source checkout, and any
        # launch that never self-installed, therefore keeps Explorer.
        shell_available = session_shell.session_shell_available()
        self.minimal_shell_checkbox.setChecked(shell_available)
        self.minimal_shell_checkbox.setEnabled(shell_available)
        if not shell_available:
            minimal_shell_tooltip += (
                "\n\nUnavailable here: this launch has no installed copy of the app to use as the "
                "session's shell, so the background session keeps the normal Windows desktop."
            )
        self.minimal_shell_checkbox.setToolTip(minimal_shell_tooltip)
        minimal_shell_label.setToolTip(minimal_shell_tooltip)
        minimal_shell_row = QHBoxLayout()
        minimal_shell_row.addWidget(minimal_shell_label)
        minimal_shell_row.addWidget(self.minimal_shell_checkbox)
        minimal_shell_row.addStretch(1)
        root.addLayout(minimal_shell_row)

        session_actions = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("background_session_start_button")
        self.start_button.setToolTip(
            "Creates the background session and disconnects it immediately, so it keeps running "
            "with no window open. Can take up to a minute the first time a session logs on."
        )
        self.show_button = QPushButton("Show")
        self.show_button.setObjectName("background_session_show_button")
        self.show_button.setToolTip("Reconnects to the running background session for a look.")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("background_session_stop_button")
        self.stop_button.setToolTip("Ends the background session outright (signs it out).")
        session_actions.addWidget(self.start_button)
        session_actions.addWidget(self.show_button)
        session_actions.addWidget(self.stop_button)
        session_actions.addStretch(1)
        root.addLayout(session_actions)

        self.result_text = QPlainTextEdit()
        self.result_text.setObjectName("background_session_result_text")
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(90)
        root.addWidget(self.result_text, 1)

        self.save_credential_button.clicked.connect(self._save_credential)
        self.forget_credential_button.clicked.connect(self._forget_credential)
        self.recheck_button.clicked.connect(self._refresh_setup)
        self.start_button.clicked.connect(self._start)
        self.show_button.clicked.connect(self._show)
        self.stop_button.clicked.connect(self._stop)

    def _save_credential(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username:
            self._set_result("Enter the username first.")
            return
        if not password:
            self._set_result("Enter the password first.")
            return
        ok = background_session.store_credential(background_session.TARGET_ADDRESS, username, password)
        self.password_edit.clear()
        self._set_result(
            "Credential saved." if ok else "Could not save the credential to Windows Credential Manager."
        )

    def _forget_credential(self) -> None:
        result = background_session.forget_credential(background_session.TARGET_ADDRESS)
        self._set_result(result.message)

    def _start(self) -> None:
        # The real gate. A disabled button only hides the action from a mouse click; this is what
        # actually keeps a start off a machine with a genuine setup problem.
        if not self._can_start:
            self._set_result(
                "Setup is not ready yet. Resolve the points in the Setup box above, then press "
                "Re-check."
            )
            return
        username = self.username_edit.text().strip()
        if not username:
            self._set_result("Enter the username first.")
            return
        self._set_result("Starting background session...")
        self._set_buttons_enabled(False)
        alternate_shell = None
        shell_working_directory = None
        if self.minimal_shell_checkbox.isChecked() and session_shell.session_shell_available():
            alternate_shell = session_shell.session_shell_command()
            shell_working_directory = str(install_dir())
        try:
            result = background_session.start_background_session(
                self.data_dir, background_session.TARGET_ADDRESS, username,
                alternate_shell=alternate_shell,
                shell_working_directory=shell_working_directory,
                pump=QApplication.processEvents,
            )
        finally:
            self._set_buttons_enabled(True)
        self._set_result(result.message)
        self._refresh_status()

    def _show(self) -> None:
        self._stop_window_branding()
        username = self.username_edit.text().strip()
        if not username:
            self._set_result("Enter the username first.")
            return
        result = background_session.show_background_session(self.data_dir, username)
        if result.ok and result.client_pid is not None and result.client_process is not None:
            try:
                self._start_window_branding(result.client_pid, result.client_process)
            except Exception:
                pass
        self._set_result(result.message)
        self._refresh_status()

    def _start_window_branding(self, client_pid: int, client_process: object) -> None:
        """Retry Win32 window branding while mstsc is still replacing its connecting title."""
        self._stop_window_branding()
        icon = app_icon_path(self._entry_file) if self._entry_file is not None else None
        title = f"{APP_NAME} - Background Session"
        cancel = threading.Event()
        thread = self._thread_starter(
            target=window_branding.run_branding_loop,
            args=(client_pid, title, icon, cancel),
            # Handed to the worker as well, not only held here: see run_branding_loop's own
            # docstring for why the reference has to live on the worker's frame.
            kwargs={"keep_alive": client_process},
            daemon=True,
        )
        self._branding_cancel = cancel
        self._branding_thread = thread
        # Deliberately kept for its side effect: its open process handle reserves client_pid.
        # No method is called on it.
        self._branding_process = client_process
        thread.start()

    def _stop_window_branding(self) -> None:
        if self._branding_cancel is not None:
            self._branding_cancel.set()
        self._branding_cancel = None
        self._branding_thread = None
        self._branding_process = None

    def _stop(self) -> None:
        # Once the session is stopped, mstsc is going away, and a recycled pid could otherwise
        # have an unrelated program's window branded.
        self._stop_window_branding()
        result = background_session.stop_background_session(self.data_dir)
        self._set_result(result.message)
        self._refresh_status()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in (self.start_button, self.show_button, self.stop_button):
            button.setEnabled(enabled)
        if enabled:
            # Never re-enable Start past the can-start gate: _start's own finally block runs
            # through here, and without this a failed attempt would leave Start clickable again
            # on a machine with a genuine setup problem.
            self.start_button.setEnabled(self._can_start)

    def _refresh_setup(self) -> None:
        """Re-run the setup checks and render them, gating Start on the outcome."""
        status = self._check_setup()
        self._can_start = bool(status.can_start)
        if status.ok and not status.undetermined:
            self.setup_summary_label.setText("Setup: ready. All four checks passed.")
        elif self._can_start:
            self.setup_summary_label.setText(
                "Setup: could not be fully confirmed. Start is enabled anyway. Only start with "
                "warnings if you know what you are doing."
            )
        else:
            self.setup_summary_label.setText(
                "Setup: not ready. Start stays disabled until the points below are resolved."
            )
        lines = []
        for check in status.checks:
            prefix = "OK" if check.ok else "Warning" if check.undetermined else "Needs attention"
            lines.append(f"{prefix}: {check.name} - {check.detail}")
            if not check.ok and check.remediation:
                lines.append(f"    {check.remediation}")
        self.setup_details_label.setText("\n".join(lines))
        self.start_button.setEnabled(self._can_start)

    def _refresh_status(self) -> None:
        active = background_session.is_background_session_active(self.data_dir)
        self.status_label.setText(
            "Background session: running (disconnected)." if active else "Background session: not running."
        )

    def _set_result(self, message: str) -> None:
        self.result_text.setPlainText(message)
