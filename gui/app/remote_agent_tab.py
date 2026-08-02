"""Remote-agent pairing and lifecycle controls for the local AHK bridge."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any, Protocol

from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.widgets import FormLayout
from ipc.client import CommandAck, IpcBusyError, IpcTimeoutError
from ipc.config_reader import GeneralConfig
from ipc.protocol import (
    VERB_PAIR_REMOTE_AGENT,
    VERB_START_REMOTE_AGENT,
    VERB_STOP_REMOTE_AGENT,
    pair_remote_agent_payload,
    start_remote_agent_payload,
    stop_remote_agent_payload,
)


PAIR_TIMEOUT_SECONDS = 60.0
TWO_FACTOR_REQUIRED_TEXT = "two-factor authentication enabled"


class RemoteAgentIpcClient(Protocol):
    """The command surface this tab needs, including pairing's longer timeout."""

    def send_command(
        self, verb: str, payload: dict[str, Any], timeout: float = 5.0,
        pump: Any = None,
    ) -> CommandAck: ...


class RemoteAgentTab(QWidget):
    """Remote Agent tab content: pair an agent without ever placing account credentials
    in bridge JSON, and toggle the local bridge those commands travel over.
    """

    def __init__(
        self,
        general: GeneralConfig,
        client: RemoteAgentIpcClient,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self._build_ui(general)

    def _build_ui(self, general: GeneralConfig) -> None:
        root = QVBoxLayout(self)

        bridge = QGroupBox("Local bridge")
        bridge_layout = QVBoxLayout(bridge)
        self.remote_bridge_enabled_checkbox = QCheckBox("Enable remote bridge")
        self.remote_bridge_enabled_checkbox.setObjectName("general_remote_bridge_enabled")
        self.remote_bridge_enabled_checkbox.setChecked(general.remote_bridge_enabled)
        self.remote_bridge_enabled_checkbox.setToolTip(
            "Turns on the local file-based bridge that the optional remote access feature "
            "reads from. Off by default; the macro does no networking either way - only the "
            "background agent below, once started, talks to the server."
        )
        bridge_layout.addWidget(self.remote_bridge_enabled_checkbox)
        root.addWidget(bridge)

        description = QLabel(
            "Pairs this PC with your Anime Expedition remote-control account and starts the "
            "background agent - no command line needed. Log in with an existing account, or "
            "register a new one, right here."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        form = FormLayout()
        self.agent_path_edit = QLineEdit(general.remote_agent_path)
        self.agent_path_edit.setObjectName("remote_agent_path_edit")
        self.agent_path_edit.setToolTip(
            "Path to animeexpedition-agent.exe - bundled automatically with the installed app, "
            "so this is usually already filled in. Only needs to be set once - it is remembered; "
            "Browse manually only if you moved or built your own copy (see remote/README.md)."
        )
        browse_row = QHBoxLayout()
        browse_row.addWidget(self.agent_path_edit, 1)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setObjectName("remote_agent_browse_button")
        self.browse_button.setToolTip(self.agent_path_edit.toolTip())
        browse_row.addWidget(self.browse_button)
        form.addRow("Agent executable", browse_row)

        self.server_url_edit = QLineEdit(general.remote_server_url or "http://localhost:8787")
        self.server_url_edit.setObjectName("remote_server_url_edit")
        self.server_url_edit.setToolTip(
            "The backend base URL shown by the web dashboard, e.g. http://localhost:8787 "
            "while testing locally."
        )
        form.addRow("Server URL", self.server_url_edit)

        account_row = QHBoxLayout()
        self.login_radio = QRadioButton("Log in")
        self.login_radio.setObjectName("remote_login_radio")
        self.login_radio.setChecked(True)
        self.register_radio = QRadioButton("Register")
        self.register_radio.setObjectName("remote_register_radio")
        self.account_mode_group = QButtonGroup(self)
        self.account_mode_group.addButton(self.login_radio)
        self.account_mode_group.addButton(self.register_radio)
        account_tooltip = (
            "Log in pairs this device to an account you already created (on this dashboard or "
            "another device). Register creates a brand new account and pairs this device to it "
            "in one step."
        )
        self.login_radio.setToolTip(account_tooltip)
        self.register_radio.setToolTip(account_tooltip)
        account_row.addWidget(self.login_radio)
        account_row.addWidget(self.register_radio)
        account_row.addStretch(1)
        form.addRow("Account", account_row)

        self.email_edit = QLineEdit(general.remote_account_email)
        self.email_edit.setObjectName("remote_account_email_edit")
        form.addRow("Email", self.email_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("remote_password_edit")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password", self.password_edit)

        self.totp_edit = QLineEdit()
        self.totp_edit.setObjectName("remote_totp_edit")
        self.totp_edit.setToolTip(
            "Only needed for Log in, and only if the account has two-factor authentication "
            "enabled. Leave blank otherwise; if one is required, this window will say so and "
            "you can fill it in and click Pair again."
        )
        form.addRow("2FA code", self.totp_edit)
        root.addLayout(form)

        self.pair_button = QPushButton("Pair")
        self.pair_button.setObjectName("remote_pair_button")
        root.addWidget(self.pair_button)

        self.agent_status_label = QLabel("Agent: status unavailable until an action is acknowledged.")
        self.agent_status_label.setObjectName("remote_agent_status_label")
        self.agent_status_label.setWordWrap(True)
        root.addWidget(self.agent_status_label)

        agent_actions = QHBoxLayout()
        self.start_agent_button = QPushButton("Start Agent")
        self.start_agent_button.setObjectName("remote_start_agent_button")
        self.stop_agent_button = QPushButton("Stop Agent")
        self.stop_agent_button.setObjectName("remote_stop_agent_button")
        lifecycle_tooltip = (
            "The agent is a separate background process - it keeps running (and reporting status) "
            "independently of this tab and of the macro's own Start/Stop, so it is NOT stopped "
            "automatically when this app closes."
        )
        self.start_agent_button.setToolTip(lifecycle_tooltip)
        self.stop_agent_button.setToolTip(lifecycle_tooltip)
        agent_actions.addWidget(self.start_agent_button)
        agent_actions.addWidget(self.stop_agent_button)
        agent_actions.addStretch(1)
        root.addLayout(agent_actions)

        self.result_text = QPlainTextEdit()
        self.result_text.setObjectName("remote_agent_result_text")
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(110)
        root.addWidget(self.result_text, 1)

        self.browse_button.clicked.connect(self._browse)
        self.pair_button.clicked.connect(self._pair)
        self.start_agent_button.clicked.connect(self._start_agent)
        self.stop_agent_button.clicked.connect(self._stop_agent)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Locate animeexpedition-agent.exe",
            self.agent_path_edit.text(),
            "Agent executable (*.exe)",
        )
        if path:
            self.agent_path_edit.setText(path)

    def _pair(self) -> None:
        agent_path = self.agent_path_edit.text().strip()
        server_url = self.server_url_edit.text().strip()
        email = self.email_edit.text().strip()
        password = self.password_edit.text()
        totp = self.totp_edit.text().strip()

        if not agent_path or not Path(agent_path).is_file():
            self._set_result("Set a valid path to animeexpedition-agent.exe first (Browse...).")
            return
        if not server_url:
            self._set_result("Enter the server URL first.")
            return
        if not email:
            self._set_result("Enter the account email first.")
            return
        if not password:
            self._set_result("Enter the account password first.")
            return

        credentials_path = ""
        # A timeout means AHK may still be mid-RunWait with local_cmd.txt already consumed - the
        # credentials file must survive that case (only AHK's own defense-in-depth cleanup, which
        # runs whichever way that RunWait eventually resolves, gets to remove it then). Every other
        # outcome (a real ack, or a failure before the command was ever queued at all) means Python
        # is the only party that will ever reference this path, so it is safe - and necessary - to
        # clean it up here.
        delete_credentials_on_exit = True
        self._set_result("Pairing...")
        # Disabling Pair for the whole call (not just relying on the GUI being unresponsive) matters
        # once the wait below pumps Qt events: a second click during that same wait must not queue a
        # duplicate pairing attempt with a fresh token while the first may still be in flight.
        self.pair_button.setEnabled(False)
        try:
            try:
                # A new, private temp file carries the two secret lines.  Do not add either
                # value to the bridge payload: local_cmd.txt can outlive a client timeout.
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", newline="", delete=False,
                    prefix="anime-expedition-credentials-", suffix=".txt",
                ) as credentials_file:
                    credentials_path = credentials_file.name
                    credentials_file.write(f"{password}\n{totp}")
            except OSError:
                self._set_result("Could not prepare the credentials file for pairing.")
                return

            payload = pair_remote_agent_payload(
                agent_path,
                server_url,
                "register" if self.register_radio.isChecked() else "login",
                email,
                credentials_path,
            )
            try:
                # PAIR_REMOTE_AGENT's real network round-trip can take tens of seconds - pump the
                # Qt event loop while waiting instead of freezing the whole GUI (every timer,
                # repaint, and this tab's own other buttons) solid for up to PAIR_TIMEOUT_SECONDS.
                ack = self.client.send_command(
                    VERB_PAIR_REMOTE_AGENT, payload, timeout=PAIR_TIMEOUT_SECONDS,
                    pump=QApplication.processEvents,
                )
            except IpcTimeoutError:
                delete_credentials_on_exit = False
                self._set_result(
                    "PAIR_REMOTE_AGENT: timed out - outcome unknown, check status before retrying"
                )
                return
            except IpcBusyError:
                self._set_result("PAIR_REMOTE_AGENT: not sent; another command is still pending.")
                return
            except Exception:
                # Never stringify an unknown exception here: a mocked/wrapped client could
                # include the command payload, which must never expose account credentials.
                self._set_result("PAIR_REMOTE_AGENT: failed before an acknowledgement was received.")
                return

            message = ack.message or ("Pairing successful." if ack.ok else "Pairing failed.")
            if TWO_FACTOR_REQUIRED_TEXT not in message:
                self.password_edit.clear()
            self.totp_edit.clear()
            self._set_feedback(message)
        finally:
            self.pair_button.setEnabled(True)
            if credentials_path and delete_credentials_on_exit:
                try:
                    os.unlink(credentials_path)
                except OSError:
                    pass

    def _start_agent(self) -> None:
        self._send_lifecycle_command(
            VERB_START_REMOTE_AGENT,
            start_remote_agent_payload(self.agent_path_edit.text().strip()),
        )

    def _stop_agent(self) -> None:
        self._send_lifecycle_command(
            VERB_STOP_REMOTE_AGENT,
            stop_remote_agent_payload(self.agent_path_edit.text().strip()),
        )

    def _send_lifecycle_command(self, verb: str, payload: dict[str, Any]) -> None:
        try:
            ack = self.client.send_command(verb, payload)
        except IpcTimeoutError:
            self._set_result(f"{verb}: timed out - outcome unknown, check status before retrying")
            return
        except IpcBusyError:
            self._set_result(f"{verb}: not sent; another command is still pending.")
            return
        except Exception:
            self._set_result(f"{verb}: failed before an acknowledgement was received.")
            return
        self._set_feedback(ack.message or ("Agent command succeeded." if ack.ok else "Agent command failed."))

    def _set_feedback(self, message: str) -> None:
        self.agent_status_label.setText(f"Agent: {message}")
        self._set_result(message)

    def _clear_secret_fields(self) -> None:
        self.password_edit.clear()
        self.totp_edit.clear()

    def _set_result(self, message: str) -> None:
        self.result_text.setPlainText(message)
