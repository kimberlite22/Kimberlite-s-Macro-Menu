from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

from app.remote_agent_tab import PAIR_TIMEOUT_SECONDS, RemoteAgentTab
from ipc.client import CommandAck, IpcTimeoutError
from ipc.config_reader import GeneralConfig
from ipc.protocol import VERB_PAIR_REMOTE_AGENT, VERB_START_REMOTE_AGENT, VERB_STOP_REMOTE_AGENT


class RecordingClient:
    def __init__(self, acknowledgements: list[CommandAck]) -> None:
        self.acknowledgements = acknowledgements
        self.calls: list[tuple[str, dict[str, str], float]] = []
        self.credentials_contents: list[str] = []

    def send_command(
        self, verb: str, payload: dict[str, str], timeout: float = 5.0, pump=None,
    ) -> CommandAck:
        self.calls.append((verb, payload, timeout))
        credentials_file = payload.get("credentialsFile")
        if credentials_file:
            self.credentials_contents.append(Path(credentials_file).read_text(encoding="utf-8"))
        return self.acknowledgements.pop(0)


def _ack(ok: bool = True, message: str = "Pairing successful.") -> CommandAck:
    return CommandAck("test", ok, message, {})


def _tab(qtbot, client: RecordingClient, agent_path: Path) -> RemoteAgentTab:
    tab = RemoteAgentTab(
        GeneralConfig(
            remote_agent_path=str(agent_path),
            remote_server_url="https://remote.example.test",
            remote_account_email="trainer@example.test",
        ),
        client,
    )
    qtbot.addWidget(tab)
    tab.show()
    return tab


def test_prefills_persisted_remote_agent_values(qtbot, tmp_path: Path) -> None:
    client = RecordingClient([])
    agent = tmp_path / "animeexpedition-agent.exe"
    tab = _tab(qtbot, client, agent)

    assert tab.agent_path_edit.text() == str(agent)
    assert tab.server_url_edit.text() == "https://remote.example.test"
    assert tab.email_edit.text() == "trainer@example.test"
    assert tab.login_radio.isChecked() and not tab.register_radio.isChecked()
    assert tab.password_edit.echoMode() == tab.password_edit.EchoMode.Password


def test_uses_the_legacy_localhost_default_without_a_persisted_server_url(qtbot) -> None:
    tab = RemoteAgentTab(GeneralConfig(), RecordingClient([]))
    qtbot.addWidget(tab)

    assert tab.agent_path_edit.text() == ""
    assert tab.server_url_edit.text() == "http://localhost:8787"


@pytest.mark.parametrize("enabled", [True, False])
def test_prefills_remote_bridge_enabled_checkbox_from_general(qtbot, enabled: bool) -> None:
    tab = RemoteAgentTab(GeneralConfig(remote_bridge_enabled=enabled), RecordingClient([]))
    qtbot.addWidget(tab)

    assert tab.remote_bridge_enabled_checkbox.objectName() == "general_remote_bridge_enabled"
    assert tab.remote_bridge_enabled_checkbox.isChecked() is enabled


def test_clear_secret_fields_clears_password_and_totp(qtbot, tmp_path: Path) -> None:
    # RemoteAgentTab is mounted permanently inside MainWindow's tab bar now, not opened and
    # closed as its own top-level QDialog, so there is no more window-close signal to hook this
    # to - MainWindow.closeEvent calls this explicitly instead (defense in depth: clear any
    # password/2FA text still sitting in the fields before the process exits).
    tab = _tab(qtbot, RecordingClient([]), tmp_path / "animeexpedition-agent.exe")
    tab.password_edit.setText("secret")
    tab.totp_edit.setText("123456")

    tab._clear_secret_fields()

    assert tab.password_edit.text() == ""
    assert tab.totp_edit.text() == ""


@pytest.mark.parametrize("ok", [True, False])
def test_pair_uses_a_temporary_credentials_file_and_removes_it(qtbot, tmp_path: Path, ok: bool) -> None:
    agent = tmp_path / "animeexpedition-agent.exe"
    agent.touch()
    client = RecordingClient([_ack(ok, "Pairing successful." if ok else "Pairing rejected.")])
    tab = _tab(qtbot, client, agent)
    tab.password_edit.setText(" secret with spaces ")
    tab.totp_edit.setText(" 123456 ")

    qtbot.mouseClick(tab.pair_button, Qt.MouseButton.LeftButton)

    assert len(client.calls) == 1
    verb, payload, timeout = client.calls[0]
    assert verb == VERB_PAIR_REMOTE_AGENT
    assert timeout == PAIR_TIMEOUT_SECONDS
    assert payload == {
        "agentPath": str(agent),
        "serverUrl": "https://remote.example.test",
        "mode": "login",
        "email": "trainer@example.test",
        "credentialsFile": payload["credentialsFile"],
    }
    assert client.credentials_contents == [" secret with spaces \n123456"]
    assert not Path(payload["credentialsFile"]).exists()
    assert " secret with spaces " not in json.dumps(payload)
    assert "123456" not in json.dumps(payload)
    assert tab.password_edit.text() == ""
    assert tab.totp_edit.text() == ""
    assert tab.result_text.toPlainText() == ("Pairing successful." if ok else "Pairing rejected.")


@pytest.mark.parametrize(
    ("agent_path", "server_url", "email", "password", "expected"),
    [
        ("", "https://remote.example.test", "trainer@example.test", "pw", "Set a valid path to animeexpedition-agent.exe first (Browse...)."),
        ("missing.exe", "https://remote.example.test", "trainer@example.test", "pw", "Set a valid path to animeexpedition-agent.exe first (Browse...)."),
        ("agent.exe", "", "trainer@example.test", "pw", "Enter the server URL first."),
        ("agent.exe", "https://remote.example.test", "", "pw", "Enter the account email first."),
        ("agent.exe", "https://remote.example.test", "trainer@example.test", "", "Enter the account password first."),
    ],
)
def test_pair_validation_short_circuits_before_creating_credentials_file(
    qtbot, tmp_path: Path, agent_path: str, server_url: str, email: str, password: str, expected: str,
) -> None:
    real_agent = tmp_path / "agent.exe"
    real_agent.touch()
    client = RecordingClient([])
    tab = _tab(qtbot, client, real_agent)
    tab.agent_path_edit.setText(str(real_agent) if agent_path == "agent.exe" else agent_path)
    tab.server_url_edit.setText(server_url)
    tab.email_edit.setText(email)
    tab.password_edit.setText(password)

    with patch("app.remote_agent_tab.tempfile.NamedTemporaryFile") as named_temp:
        tab._pair()

    named_temp.assert_not_called()
    assert not client.calls
    assert tab.result_text.toPlainText() == expected


def test_pair_preserves_password_only_when_two_factor_is_requested(qtbot, tmp_path: Path) -> None:
    agent = tmp_path / "animeexpedition-agent.exe"
    agent.touch()
    client = RecordingClient([_ack(False, "This account has two-factor authentication enabled.")])
    tab = _tab(qtbot, client, agent)
    tab.password_edit.setText("keep this password")
    tab.totp_edit.setText("old code")

    tab._pair()

    assert tab.password_edit.text() == "keep this password"
    assert tab.totp_edit.text() == ""


def test_pair_removes_credentials_file_after_a_client_exception(qtbot, tmp_path: Path) -> None:
    agent = tmp_path / "animeexpedition-agent.exe"
    agent.touch()

    class RaisingClient:
        credentials_path = ""

        def send_command(
            self, verb: str, payload: dict[str, str], timeout: float = 5.0, pump=None,
        ) -> CommandAck:
            assert verb == VERB_PAIR_REMOTE_AGENT and timeout == PAIR_TIMEOUT_SECONDS
            self.credentials_path = payload["credentialsFile"]
            raise RuntimeError("simulated client failure")

    client = RaisingClient()
    tab = RemoteAgentTab(GeneralConfig(remote_agent_path=str(agent), remote_server_url="https://example.test", remote_account_email="a@b.test"), client)
    qtbot.addWidget(tab)
    tab.password_edit.setText("secret")

    tab._pair()

    assert client.credentials_path and not Path(client.credentials_path).exists()
    assert tab.result_text.toPlainText() == "PAIR_REMOTE_AGENT: failed before an acknowledgement was received."


def test_pair_timeout_preserves_credentials_file_and_reenables_button(qtbot, tmp_path: Path) -> None:
    # Regression test: a timeout means AHK may still be mid-RunWait with local_cmd.txt already
    # consumed - deleting the credentials file immediately would make that still-in-flight command
    # fail with a missing file the moment AHK actually gets to it. Only a definitive outcome (a real
    # ack, or a failure before the command was ever queued) should trigger Python-side cleanup.
    agent = tmp_path / "animeexpedition-agent.exe"
    agent.touch()

    class TimingOutClient:
        credentials_path = ""

        def send_command(
            self, verb: str, payload: dict[str, str], timeout: float = 5.0, pump=None,
        ) -> CommandAck:
            self.credentials_path = payload["credentialsFile"]
            raise IpcTimeoutError("simulated timeout")

    client = TimingOutClient()
    tab = RemoteAgentTab(
        GeneralConfig(remote_agent_path=str(agent), remote_server_url="https://example.test",
                      remote_account_email="a@b.test"),
        client,
    )
    qtbot.addWidget(tab)
    tab.password_edit.setText("secret")

    tab._pair()

    assert client.credentials_path and Path(client.credentials_path).exists()
    assert tab.pair_button.isEnabled()
    assert "timed out" in tab.result_text.toPlainText()
    Path(client.credentials_path).unlink()  # test-only cleanup; production leaves this to AHK


def test_start_and_stop_send_current_agent_path(qtbot, tmp_path: Path) -> None:
    agent = tmp_path / "animeexpedition-agent.exe"
    client = RecordingClient([_ack(True, "Agent started."), _ack(True, "Agent stopped.")])
    tab = _tab(qtbot, client, agent)

    qtbot.mouseClick(tab.start_agent_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(tab.stop_agent_button, Qt.MouseButton.LeftButton)

    assert client.calls == [
        (VERB_START_REMOTE_AGENT, {"agentPath": str(agent)}, 5.0),
        (VERB_STOP_REMOTE_AGENT, {"agentPath": str(agent)}, 5.0),
    ]
    assert tab.agent_status_label.text() == "Agent: Agent stopped."
    assert tab.result_text.toPlainText() == "Agent stopped."
