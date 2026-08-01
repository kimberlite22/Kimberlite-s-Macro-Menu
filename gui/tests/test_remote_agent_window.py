from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

from app.remote_agent_window import PAIR_TIMEOUT_SECONDS, RemoteAgentWindow
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


def _window(qtbot, client: RecordingClient, agent_path: Path) -> RemoteAgentWindow:
    window = RemoteAgentWindow(
        GeneralConfig(
            remote_agent_path=str(agent_path),
            remote_server_url="https://remote.example.test",
            remote_account_email="trainer@example.test",
        ),
        client,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def test_prefills_persisted_remote_agent_values(qtbot, tmp_path: Path) -> None:
    client = RecordingClient([])
    agent = tmp_path / "animeexpedition-agent.exe"
    window = _window(qtbot, client, agent)

    assert window.agent_path_edit.text() == str(agent)
    assert window.server_url_edit.text() == "https://remote.example.test"
    assert window.email_edit.text() == "trainer@example.test"
    assert window.login_radio.isChecked() and not window.register_radio.isChecked()
    assert window.password_edit.echoMode() == window.password_edit.EchoMode.Password


def test_window_has_independent_minimize_button(qtbot, tmp_path: Path) -> None:
    # Regression guard, see make_independently_minimizable: RemoteAgentWindow would otherwise
    # have no minimize button of its own, and its caller (MainWindow) deliberately constructs
    # it with no Qt parent since a parented QDialog would be a native Windows "owned window"
    # that auto-hides whenever its owner is minimized.
    client = RecordingClient([])
    agent = tmp_path / "animeexpedition-agent.exe"
    window = _window(qtbot, client, agent)
    assert window.windowFlags() & Qt.WindowMinimizeButtonHint


def test_uses_the_legacy_localhost_default_without_a_persisted_server_url(qtbot) -> None:
    window = RemoteAgentWindow(GeneralConfig(), RecordingClient([]))
    qtbot.addWidget(window)

    assert window.agent_path_edit.text() == ""
    assert window.server_url_edit.text() == "http://localhost:8787"


def test_close_clears_any_remaining_secret_fields(qtbot, tmp_path: Path) -> None:
    window = _window(qtbot, RecordingClient([]), tmp_path / "animeexpedition-agent.exe")
    window.password_edit.setText("secret")
    window.totp_edit.setText("123456")

    window.close()

    assert window.password_edit.text() == ""
    assert window.totp_edit.text() == ""


@pytest.mark.parametrize("ok", [True, False])
def test_pair_uses_a_temporary_credentials_file_and_removes_it(qtbot, tmp_path: Path, ok: bool) -> None:
    agent = tmp_path / "animeexpedition-agent.exe"
    agent.touch()
    client = RecordingClient([_ack(ok, "Pairing successful." if ok else "Pairing rejected.")])
    window = _window(qtbot, client, agent)
    window.password_edit.setText(" secret with spaces ")
    window.totp_edit.setText(" 123456 ")

    qtbot.mouseClick(window.pair_button, Qt.MouseButton.LeftButton)

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
    assert window.password_edit.text() == ""
    assert window.totp_edit.text() == ""
    assert window.result_text.toPlainText() == ("Pairing successful." if ok else "Pairing rejected.")


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
    window = _window(qtbot, client, real_agent)
    window.agent_path_edit.setText(str(real_agent) if agent_path == "agent.exe" else agent_path)
    window.server_url_edit.setText(server_url)
    window.email_edit.setText(email)
    window.password_edit.setText(password)

    with patch("app.remote_agent_window.tempfile.NamedTemporaryFile") as named_temp:
        window._pair()

    named_temp.assert_not_called()
    assert not client.calls
    assert window.result_text.toPlainText() == expected


def test_pair_preserves_password_only_when_two_factor_is_requested(qtbot, tmp_path: Path) -> None:
    agent = tmp_path / "animeexpedition-agent.exe"
    agent.touch()
    client = RecordingClient([_ack(False, "This account has two-factor authentication enabled.")])
    window = _window(qtbot, client, agent)
    window.password_edit.setText("keep this password")
    window.totp_edit.setText("old code")

    window._pair()

    assert window.password_edit.text() == "keep this password"
    assert window.totp_edit.text() == ""


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
    window = RemoteAgentWindow(GeneralConfig(remote_agent_path=str(agent), remote_server_url="https://example.test", remote_account_email="a@b.test"), client)
    qtbot.addWidget(window)
    window.password_edit.setText("secret")

    window._pair()

    assert client.credentials_path and not Path(client.credentials_path).exists()
    assert window.result_text.toPlainText() == "PAIR_REMOTE_AGENT: failed before an acknowledgement was received."


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
    window = RemoteAgentWindow(
        GeneralConfig(remote_agent_path=str(agent), remote_server_url="https://example.test",
                      remote_account_email="a@b.test"),
        client,
    )
    qtbot.addWidget(window)
    window.password_edit.setText("secret")

    window._pair()

    assert client.credentials_path and Path(client.credentials_path).exists()
    assert window.pair_button.isEnabled()
    assert "timed out" in window.result_text.toPlainText()
    Path(client.credentials_path).unlink()  # test-only cleanup; production leaves this to AHK


def test_start_and_stop_send_current_agent_path(qtbot, tmp_path: Path) -> None:
    agent = tmp_path / "animeexpedition-agent.exe"
    client = RecordingClient([_ack(True, "Agent started."), _ack(True, "Agent stopped.")])
    window = _window(qtbot, client, agent)

    qtbot.mouseClick(window.start_agent_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.stop_agent_button, Qt.MouseButton.LeftButton)

    assert client.calls == [
        (VERB_START_REMOTE_AGENT, {"agentPath": str(agent)}, 5.0),
        (VERB_STOP_REMOTE_AGENT, {"agentPath": str(agent)}, 5.0),
    ]
    assert window.agent_status_label.text() == "Agent: Agent stopped."
    assert window.result_text.toPlainText() == "Agent stopped."
