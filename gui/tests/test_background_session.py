from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

from app import background_session
from app.background_session import SessionInfo, SessionState
from app.engine_process import EngineProcess


def _no_engines(monkeypatch) -> None:
    monkeypatch.setattr(background_session, "find_engine_processes", lambda: [])
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)


def _owned_by(monkeypatch, owners: dict[int, str]) -> None:
    """Give each session id a signed-in account name; anything absent is unreadable."""
    monkeypatch.setattr(
        background_session,
        "session_owner",
        lambda session_id: ("HOSTNAME", owners[session_id]) if session_id in owners else None,
    )


def _sessions(monkeypatch, *sequences: list[SessionInfo]) -> None:
    """Return each supplied session list on successive list_sessions() calls, last one repeating."""
    remaining = list(sequences)

    def next_sessions() -> list[SessionInfo]:
        if len(remaining) > 1:
            return remaining.pop(0)
        return remaining[0]

    monkeypatch.setattr(background_session, "list_sessions", next_sessions)


def _write_marker(
    directory: Path, session_id: int = 4, username: str = "trainer", domain: str = "HOSTNAME"
) -> Path:
    path = directory / background_session.STATE_FILE_NAME
    path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "address": "127.0.0.2",
                "domain": domain,
                "username": username,
                "started_at": 1.0,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_rdp_file_disables_prompts_that_a_hidden_window_could_never_answer(tmp_path: Path) -> None:
    path = tmp_path / "session.rdp"
    background_session.write_rdp_file(path, "127.0.0.2", "trainer")
    content = path.read_text(encoding="utf-8")

    assert "full address:s:127.0.0.2" in content
    assert "username:s:trainer" in content
    assert "prompt for credentials:i:0" in content
    assert "authentication level:i:0" in content
    assert "smart sizing:i:1" in content
    assert "dynamic resolution" not in content
    # No alternate shell unless one was asked for: that is background-session-minimal-shell's job.
    assert "alternate shell" not in content


def test_rdp_file_carries_an_alternate_shell_when_one_is_given(tmp_path: Path) -> None:
    path = tmp_path / "session.rdp"
    background_session.write_rdp_file(
        path, "127.0.0.2", "trainer",
        alternate_shell="C:\\Programs\\launcher.exe", shell_working_directory="C:\\Programs",
    )
    content = path.read_text(encoding="utf-8")

    assert "alternate shell:s:C:\\Programs\\launcher.exe" in content
    assert "shell working directory:s:C:\\Programs" in content


def test_credential_target_matches_the_name_mstsc_looks_up() -> None:
    assert background_session.credential_target("127.0.0.2") == "TERMSRV/127.0.0.2"


def test_store_credential_never_puts_the_password_on_a_command_line(monkeypatch) -> None:
    """The whole reason this uses CredWriteW instead of cmdkey.exe /pass:<password>."""
    run = MagicMock()
    monkeypatch.setattr(background_session.subprocess, "run", run)
    popen = MagicMock()
    monkeypatch.setattr(background_session.subprocess, "Popen", popen)
    written: list[str] = []

    class FakeAdvapi:
        def CredWriteW(self, credential, flags):
            blob = credential._obj
            raw = bytes(
                bytearray(blob.CredentialBlob[index] & 0xFF for index in range(blob.CredentialBlobSize))
            )
            written.append(raw.decode("utf-16-le"))
            return 1

    monkeypatch.setattr(background_session, "_advapi32", lambda: FakeAdvapi())

    assert background_session.store_credential("127.0.0.2", "trainer", "hunter2") is True
    assert written == ["hunter2"]
    run.assert_not_called()
    popen.assert_not_called()


def test_store_credential_reports_failure_rather_than_raising(monkeypatch) -> None:
    class FailingAdvapi:
        def CredWriteW(self, credential, flags):
            raise OSError("credential store unavailable")

    monkeypatch.setattr(background_session, "_advapi32", lambda: FailingAdvapi())

    assert background_session.store_credential("127.0.0.2", "trainer", "hunter2") is False


def test_credential_functions_are_false_when_the_api_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(background_session, "_advapi32", lambda: None)

    assert background_session.store_credential("127.0.0.2", "trainer", "hunter2") is False
    assert background_session.credential_exists("127.0.0.2") is False
    assert background_session.delete_credential("127.0.0.2") is False


def test_account_splitting_accepts_the_three_spellings_windows_uses() -> None:
    assert background_session.split_account("trainer") == (None, "trainer")
    assert background_session.split_account("CORP\\trainer") == ("CORP", "trainer")
    assert background_session.split_account("CORP/trainer") == ("CORP", "trainer")
    assert background_session.split_account("trainer@corp.example") == ("corp.example", "trainer")


def test_claiming_a_session_compares_a_typed_domain_when_one_was_given(monkeypatch) -> None:
    _owned_by(monkeypatch, {4: "Trainer"})  # domain reported as HOSTNAME by the helper

    assert background_session._owner_matches(4, "trainer") is True
    assert background_session._owner_matches(4, "HOSTNAME\\trainer") is True
    assert background_session._owner_matches(4, "OTHERDOMAIN\\trainer") is False
    assert background_session._owner_matches(4, "someone-else") is False


def test_verifying_a_recorded_session_compares_the_full_domain_and_account(monkeypatch) -> None:
    """A reused session id with the same account name in another domain is not ours."""
    _owned_by(monkeypatch, {4: "trainer"})

    assert background_session._owner_is(4, "HOSTNAME", "trainer") is True
    assert background_session._owner_is(4, "OTHERDOMAIN", "trainer") is False
    assert background_session._owner_is(4, "HOSTNAME", "somebody-else") is False


def test_owner_checks_fail_closed_when_the_owner_cannot_be_read(monkeypatch) -> None:
    _owned_by(monkeypatch, {})

    assert background_session._owner_matches(4, "trainer") is False
    assert background_session._owner_is(4, "HOSTNAME", "trainer") is False


def test_start_refuses_while_an_engine_runs_on_this_desktop(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    monkeypatch.setattr(background_session, "find_engine_processes", lambda: [EngineProcess(42, 1)])
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.start_background_session(tmp_path, "127.0.0.2", "trainer")

    assert result.ok is False
    assert "running on this desktop" in result.message
    launch.assert_not_called()


def test_start_refuses_when_an_engines_session_cannot_be_determined(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    monkeypatch.setattr(background_session, "find_engine_processes", lambda: [EngineProcess(42, None)])
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.start_background_session(tmp_path, "127.0.0.2", "trainer")

    assert result.ok is False
    launch.assert_not_called()


def test_start_refuses_when_this_processs_own_session_cannot_be_determined(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(background_session, "current_session_id", lambda: None)
    monkeypatch.setattr(background_session, "find_engine_processes", lambda: [EngineProcess(42, 3)])
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.start_background_session(tmp_path, "127.0.0.2", "trainer")

    assert result.ok is False
    launch.assert_not_called()


def test_start_allows_an_engine_that_belongs_to_another_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    monkeypatch.setattr(background_session, "find_engine_processes", lambda: [EngineProcess(42, 3)])
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.DISCONNECTED)],
    )
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock(poll=lambda: 0)))
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None
    )

    assert result.ok is True
    assert result.session_id == 3
    disconnect.assert_called_once_with(3)


def test_start_reports_a_missing_credential_before_the_engine_interlock(monkeypatch, tmp_path: Path) -> None:
    find_engines = MagicMock(return_value=[EngineProcess(42, 1)])
    own_session = MagicMock(return_value=1)
    monkeypatch.setattr(background_session, "find_engine_processes", find_engines)
    monkeypatch.setattr(background_session, "current_session_id", own_session)
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    monkeypatch.setattr(background_session, "credential_exists", lambda _: False)
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.start_background_session(tmp_path, "127.0.0.2", "trainer")

    assert result.ok is False
    assert "Save Credential" in result.message
    find_engines.assert_not_called()
    own_session.assert_not_called()
    launch.assert_not_called()


def test_start_disconnects_the_new_session_and_records_it(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        # The session exists but has not finished logging on yet, so it must not be claimed here.
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.CONNECTED)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)],
    )
    process = MagicMock(poll=lambda: 0)
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=process))
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None
    )

    assert result.ok is True
    assert result.session_id == 4
    disconnect.assert_called_once_with(4)
    marker = json.loads((tmp_path / background_session.STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert marker["session_id"] == 4
    assert marker["address"] == "127.0.0.2"
    # The OWNER Windows reported, not the bare name the user typed, so Stop can compare the pair.
    assert marker["domain"] == "HOSTNAME"
    assert marker["username"] == "trainer"


def test_start_never_claims_a_new_session_owned_by_somebody_else(monkeypatch, tmp_path: Path) -> None:
    """A colleague signing in over RDP at exactly this moment must not be disconnected."""
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer", 5: "somebody-else"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(5, SessionState.ACTIVE)],
    )
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock(poll=lambda: 0)))
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)
    monkeypatch.setattr(background_session, "_terminate_process", MagicMock())
    clock = iter([0.0, 0.0, 100.0, 100.0])

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    disconnect.assert_not_called()
    assert not (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_start_timeout_tracks_a_late_owner_matching_session(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.CONNECTED)],
    )
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock(poll=lambda: 0)))
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)
    monkeypatch.setattr(background_session, "_terminate_process", MagicMock())
    clock = iter([0.0, 100.0])

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert result.session_id == 4
    assert "now tracked" in result.message
    disconnect.assert_called_once_with(4)
    marker = json.loads((tmp_path / background_session.STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert marker["session_id"] == 4
    assert marker["domain"] == "HOSTNAME"
    assert marker["username"] == "trainer"
    assert background_session.is_background_session_active(tmp_path) is True


def test_start_timeout_keeps_its_message_when_no_new_session_exists(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock(poll=lambda: 0)))
    monkeypatch.setattr(background_session, "_terminate_process", MagicMock())
    clock = iter([0.0, 100.0])

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert result.message == (
        "Timed out waiting for the background session to become active. Confirm RDP Wrapper "
        "is installed and working (see the setup wizard) and that the saved credential is "
        "still correct."
    )
    assert not (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_start_timeout_keeps_its_message_for_a_nonmatching_new_session(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer", 5: "somebody-else"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(5, SessionState.CONNECTED)],
    )
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock(poll=lambda: 0)))
    monkeypatch.setattr(background_session, "_terminate_process", MagicMock())
    clock = iter([0.0, 100.0])

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert result.message == (
        "Timed out waiting for the background session to become active. Confirm RDP Wrapper "
        "is installed and working (see the setup wizard) and that the saved credential is "
        "still correct."
    )
    assert not (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_start_timeout_keeps_its_message_for_multiple_matching_new_sessions(
    monkeypatch, tmp_path: Path
) -> None:
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer", 5: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE)],
        [
            SessionInfo(1, SessionState.ACTIVE),
            SessionInfo(4, SessionState.CONNECTED),
            SessionInfo(5, SessionState.CONNECTED),
        ],
    )
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock(poll=lambda: 0)))
    monkeypatch.setattr(background_session, "_terminate_process", MagicMock())
    clock = iter([0.0, 100.0])

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert result.message == (
        "Timed out waiting for the background session to become active. Confirm RDP Wrapper "
        "is installed and working (see the setup wizard) and that the saved credential is "
        "still correct."
    )
    assert not (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_start_reports_a_disconnect_that_never_took_effect(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    # The session stays ACTIVE forever, so the confirmation loop must run out rather than lie.
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)],
    )
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock(poll=lambda: 0)))
    monkeypatch.setattr(background_session, "disconnect_session", MagicMock(return_value=True))
    monkeypatch.setattr(background_session, "_terminate_process", MagicMock())
    clock = iter([0.0, 0.0, 0.0, 100.0, 100.0])

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert "could not be disconnected" in result.message
    # The marker is still written: the session DOES exist, so Stop has to be able to reach it.
    assert (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_start_deletes_the_rdp_file_even_when_the_session_never_appears(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: True)
    _owned_by(monkeypatch, {1: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    rdp_path = tmp_path / "session.rdp"
    monkeypatch.setattr(background_session, "_new_temp_rdp_path", lambda: rdp_path)
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock(poll=lambda: 0)))
    clock = iter([0.0, 0.0, 100.0, 100.0])
    monkeypatch.setattr(background_session, "_terminate_process", MagicMock())

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert "Timed out" in result.message
    assert not rdp_path.exists()
    assert not (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_start_refuses_while_a_background_session_is_already_recorded(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)])
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.start_background_session(tmp_path, "127.0.0.2", "trainer")

    assert result.ok is False
    assert "already running" in result.message
    launch.assert_not_called()


def test_a_marker_for_a_vanished_session_is_cleared_rather_than_blocking_start(
    monkeypatch, tmp_path: Path
) -> None:
    state_file = _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])

    assert background_session.is_background_session_active(tmp_path) is False
    assert not state_file.exists()


def test_a_reused_session_id_still_counts_as_active_but_is_not_cleared(
    monkeypatch, tmp_path: Path
) -> None:
    """Blocking Start is the safe reading of "something is there that might be ours"."""
    state_file = _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "somebody-else"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)])

    assert background_session.is_background_session_active(tmp_path) is True
    assert state_file.exists()


def test_show_reports_when_no_session_is_running(monkeypatch, tmp_path: Path) -> None:
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.show_background_session(tmp_path, "trainer")

    assert result.ok is False
    assert "No background session" in result.message
    launch.assert_not_called()


def test_show_launches_mstsc_visibly_for_the_recorded_session(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)])
    launch = MagicMock(return_value=MagicMock(pid=4321))
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.show_background_session(tmp_path, "trainer")

    assert result.ok is True
    assert result.client_pid == 4321
    assert launch.call_args.kwargs["hidden"] is False


def test_show_still_works_for_a_session_whose_owner_cannot_be_confirmed(
    monkeypatch, tmp_path: Path
) -> None:
    """Reconnecting is not destructive, so unlike Stop it does not have to fail closed."""
    _write_marker(tmp_path)
    _owned_by(monkeypatch, {})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)])
    monkeypatch.setattr(background_session, "_launch_mstsc", MagicMock(return_value=MagicMock()))

    assert background_session.show_background_session(tmp_path, "trainer").ok is True


def test_stop_reports_success_only_after_the_session_disappears(monkeypatch, tmp_path: Path) -> None:
    state_file = _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)],
        [SessionInfo(1, SessionState.ACTIVE)],
    )
    logoff = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "logoff_session", logoff)
    clock = iter([0.0, 0.0, 0.0])

    result = background_session.stop_background_session(
        tmp_path, sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is True
    logoff.assert_called_once_with(4)
    assert not state_file.exists()


def test_stop_never_logs_off_a_session_that_is_no_longer_ours(monkeypatch, tmp_path: Path) -> None:
    """Windows reuses session ids, so the recorded id alone is not proof of ownership."""
    state_file = _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "somebody-else"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)])
    logoff = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "logoff_session", logoff)

    result = background_session.stop_background_session(tmp_path)

    assert result.ok is False
    assert "no longer signed in" in result.message
    logoff.assert_not_called()
    assert state_file.exists()


def test_a_failed_logoff_keeps_the_marker_so_start_cannot_make_a_second_session(
    monkeypatch, tmp_path: Path
) -> None:
    state_file = _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)])
    monkeypatch.setattr(background_session, "logoff_session", MagicMock(return_value=False))

    result = background_session.stop_background_session(tmp_path)

    assert result.ok is False
    assert "may still be running" in result.message
    assert state_file.exists()
    assert background_session.is_background_session_active(tmp_path) is True


def test_stop_keeps_the_marker_when_the_session_persists_after_logoff(monkeypatch, tmp_path: Path) -> None:
    state_file = _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)])
    monkeypatch.setattr(background_session, "logoff_session", MagicMock(return_value=True))
    clock = iter([0.0, 0.0, 100.0])

    result = background_session.stop_background_session(
        tmp_path, sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert "could not be confirmed" in result.message
    assert state_file.exists()


def test_stale_rdp_files_are_swept_but_recent_ones_are_left_alone(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(background_session.tempfile, "gettempdir", lambda: str(tmp_path))
    stale = tmp_path / f"{background_session.RDP_FILE_PREFIX}old.rdp"
    recent = tmp_path / f"{background_session.RDP_FILE_PREFIX}new.rdp"
    unrelated = tmp_path / "somebody-elses.rdp"
    for path in (stale, recent, unrelated):
        path.write_text("full address:s:127.0.0.2", encoding="utf-8")
    old_time = time.time() - background_session.STALE_RDP_FILE_AGE_SECONDS - 60
    os.utime(stale, (old_time, old_time))
    os.utime(unrelated, (old_time, old_time))

    background_session._new_temp_rdp_path()

    assert not stale.exists()
    assert recent.exists()
    assert unrelated.exists()
