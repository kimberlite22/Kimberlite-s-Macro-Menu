"""Background Session tab: start, show and stop the hidden background Windows session."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import background_session
from app.widgets import FormLayout


class BackgroundSessionTab(QWidget):
    """Lets the user run the macro in a second, hidden Windows session, physical desktop free."""

    def __init__(self, data_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self._build_ui()
        self._refresh_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        description = QLabel(
            "Runs the macro in a second Windows session so the physical desktop stays free for "
            "other work. Requires RDP Wrapper to be installed and working - see the setup wizard "
            "if Start fails."
        )
        description.setWordWrap(True)
        root.addWidget(description)

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
        username = self.username_edit.text().strip()
        if not username:
            self._set_result("Enter the username first.")
            return
        self._set_result("Starting background session...")
        self._set_buttons_enabled(False)
        try:
            result = background_session.start_background_session(
                self.data_dir, background_session.TARGET_ADDRESS, username,
                pump=QApplication.processEvents,
            )
        finally:
            self._set_buttons_enabled(True)
        self._set_result(result.message)
        self._refresh_status()

    def _show(self) -> None:
        username = self.username_edit.text().strip()
        if not username:
            self._set_result("Enter the username first.")
            return
        result = background_session.show_background_session(self.data_dir, username)
        self._set_result(result.message)
        self._refresh_status()

    def _stop(self) -> None:
        result = background_session.stop_background_session(self.data_dir)
        self._set_result(result.message)
        self._refresh_status()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in (self.start_button, self.show_button, self.stop_button):
            button.setEnabled(enabled)

    def _refresh_status(self) -> None:
        active = background_session.is_background_session_active(self.data_dir)
        self.status_label.setText(
            "Background session: running (disconnected)." if active else "Background session: not running."
        )

    def _set_result(self, message: str) -> None:
        self.result_text.setPlainText(message)
