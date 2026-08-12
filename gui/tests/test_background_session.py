from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import background_session
from app.background_session import SessionInfo, SessionState
from app.engine_process import EngineProcess


# Captured before the autouse fixture below stands in for it, so the one test that is ABOUT this
# function can still reach the real implementation.
_REAL_CREDENTIAL_EXISTS = background_session.credential_exists


@pytest.fixture(autouse=True)
def _windows_already_remembers_the_sign_in(monkeypatch):
    """Never let the developer's own credential store decide how a Start behaves here.

    A headless Start hides its Remote Desktop client only when Windows can sign in without asking
    (see start_background_session), so this one read would otherwise make that test's outcome depend
    on the machine running it. The tests about a missing credential set their own value on top.
    """
    monkeypatch.setattr(background_session, "credential_exists", lambda *_args, **_kwargs: True)


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
    assert "dynamic resolution:i:0" in content
    # No alternate shell unless one was asked for: that is background-session-minimal-shell's job.
    assert "alternate shell" not in content


def test_rdp_file_uses_the_resolved_primary_display_size(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(background_session, "primary_display_size", lambda: (2560, 1440))
    path = tmp_path / "session.rdp"

    background_session.write_rdp_file(path, "127.0.0.2", "trainer")

    content = path.read_text(encoding="utf-8")
    assert "desktopwidth:i:2560" in content
    assert "desktopheight:i:1440" in content
    assert "smart sizing:i:1" in content
    assert "dynamic resolution:i:0" in content


def test_rdp_file_falls_back_to_full_hd_when_display_size_is_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(background_session, "_user32", lambda: None)
    path = tmp_path / "session.rdp"

    background_session.write_rdp_file(path, "127.0.0.2", "trainer")

    content = path.read_text(encoding="utf-8")
    assert "desktopwidth:i:1920" in content
    assert "desktopheight:i:1080" in content
    assert "smart sizing:i:1" in content
    assert "dynamic resolution:i:0" in content


def test_rdp_file_allows_tests_to_pin_desktop_size(tmp_path: Path) -> None:
    path = tmp_path / "session.rdp"

    background_session.write_rdp_file(
        path, "127.0.0.2", "trainer", desktop_width=1280, desktop_height=720
    )

    content = path.read_text(encoding="utf-8")
    assert "desktopwidth:i:1280" in content
    assert "desktopheight:i:720" in content


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
    # The whole reason no password ever has to reach this app: mstsc stores its own credential under
    # this exact name when the user ticks "Remember me", and reading it is all that is needed here.
    assert background_session.credential_target("127.0.0.2") == "TERMSRV/127.0.0.2"


def test_no_password_is_ever_written_or_deleted_by_this_module() -> None:
    """Read only, by construction: the write side was removed with the sign-in fields."""
    assert not hasattr(background_session, "store_credential")
    assert not hasattr(background_session, "delete_credential")
    assert not hasattr(background_session, "forget_credential")


def test_reading_the_credential_is_false_when_the_api_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(background_session, "_advapi32", lambda: None)

    assert _REAL_CREDENTIAL_EXISTS("127.0.0.2") is False


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
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.start_background_session(tmp_path, "127.0.0.2", "trainer")

    assert result.ok is False
    launch.assert_not_called()


def test_start_allows_an_engine_that_belongs_to_another_accounts_session(
    monkeypatch, tmp_path: Path
) -> None:
    # An engine somewhere else on the machine is only this app's business when it is running as the
    # account this app would start a session as. Another user's macro session is theirs, must not be
    # adopted, and must not stand in the way of starting one here.
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    monkeypatch.setattr(background_session, "find_engine_processes", lambda: [EngineProcess(42, 3)])
    _owned_by(monkeypatch, {1: "trainer", 3: "someone-else", 4: "trainer"})
    others = [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)]
    _sessions(
        monkeypatch,
        others,
        others,
        [*others, SessionInfo(4, SessionState.ACTIVE)],
        [*others, SessionInfo(4, SessionState.DISCONNECTED)],
    )
    launch = MagicMock(return_value=MagicMock(poll=lambda: 0))
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", disconnect_after_start=True, sleep=lambda _: None
    )

    assert result.ok is True
    assert result.session_id == 4
    assert launch.call_args.kwargs["hidden"] is True
    disconnect.assert_called_once_with(4)


def test_start_without_a_saved_credential_launches_the_client_that_can_ask_for_one(
    monkeypatch, tmp_path: Path
) -> None:
    """A missing credential used to refuse the Start outright, which was a dead end.

    Nothing in this app can create one (the write side is gone with the sign-in fields), and Show
    only ever reconnects to a session that is already running, so refusing here left a first-time
    user with no way to reach mstsc's own prompt at all. Start therefore launches the client, which
    asks for the password in its own visible window and remembers it from there.
    """
    _no_engines(monkeypatch)
    reads_credential = MagicMock(return_value=False)
    monkeypatch.setattr(background_session, "credential_exists", reads_credential)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)],
    )
    launch = MagicMock(return_value=MagicMock(poll=lambda: None))
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None
    )

    assert result.ok is True
    assert result.session_id == 4
    # Visible, so a credentials prompt is answerable rather than hidden behind a window nobody sees.
    assert launch.call_args.kwargs["hidden"] is False
    # Not consulted at all on this path. Whether a note about the prompt is worth showing is the
    # caller's decision (background_session_tab._credential_note), and a visible Start needs no
    # answer from the credential store: it can afford to let mstsc ask.
    reads_credential.assert_not_called()


def test_a_headless_start_stays_visible_while_windows_still_has_to_ask(
    monkeypatch, tmp_path: Path
) -> None:
    """A prompt in a hidden window cannot be answered by anyone.

    Hiding it would leave the Start waiting out its whole timeout behind an invisible dialog and then
    reporting a timeout that names none of that, which is worse than a window the user did not ask
    for. So the headless request is honored only once Windows can sign in on its own.
    """
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "credential_exists", lambda _: False)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)],
    )
    launch = MagicMock(return_value=MagicMock(poll=lambda: 0))
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)
    monkeypatch.setattr(background_session, "disconnect_session", MagicMock(return_value=True))
    monkeypatch.setattr(background_session, "_terminate_process", MagicMock())

    background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", disconnect_after_start=True, sleep=lambda _: None
    )

    assert launch.call_args.kwargs["hidden"] is False


def test_start_leaves_the_new_session_connected_and_records_it(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE)],
        # The session exists but has not finished logging on yet, so it must not be claimed here.
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.CONNECTED)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)],
    )
    process = MagicMock(poll=lambda: 0)
    launch = MagicMock(return_value=process)
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)
    terminate = MagicMock()
    monkeypatch.setattr(background_session, "_terminate_process", terminate)

    result = background_session.start_background_session(
        tmp_path, "127.0.0.2", "trainer", sleep=lambda _: None
    )

    assert result.ok is True
    assert result.session_id == 4
    assert result.message == "Background session started and remains connected."
    assert launch.call_args.kwargs["hidden"] is False
    disconnect.assert_not_called()
    terminate.assert_not_called()
    marker = json.loads((tmp_path / background_session.STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert marker["session_id"] == 4
    assert marker["address"] == "127.0.0.2"
    # The OWNER Windows reported, not the bare name the user typed, so Stop can compare the pair.
    assert marker["domain"] == "HOSTNAME"
    assert marker["username"] == "trainer"


def test_start_never_claims_a_new_session_owned_by_somebody_else(monkeypatch, tmp_path: Path) -> None:
    """A colleague signing in over RDP at exactly this moment must not be disconnected."""
    _no_engines(monkeypatch)
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
        tmp_path,
        "127.0.0.2",
        "trainer",
        disconnect_after_start=True,
        sleep=lambda _: None,
        now=lambda: next(clock),
    )

    assert result.ok is False
    assert "could not be disconnected" in result.message
    # The marker is still written: the session DOES exist, so Stop has to be able to reach it.
    assert (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_start_deletes_the_rdp_file_even_when_the_session_never_appears(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
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
    disconnect = MagicMock()
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)

    result = background_session.show_background_session(tmp_path, "trainer")

    assert result.ok is True
    assert result.client_pid == 4321
    assert launch.call_args.kwargs["hidden"] is False
    disconnect.assert_not_called()


def test_show_releases_an_active_session_before_launching_a_client(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.DISCONNECTED)],
    )
    launch = MagicMock(return_value=MagicMock(pid=4321))
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)

    result = background_session.show_background_session(
        tmp_path, "trainer", sleep=lambda _: None, now=lambda: 0.0
    )

    assert result.ok is True
    assert result.session_id == 4
    disconnect.assert_called_once_with(4)
    assert launch.call_args.kwargs["hidden"] is False


def test_show_does_not_launch_when_an_active_session_cannot_be_released(
    monkeypatch, tmp_path: Path
) -> None:
    _write_marker(tmp_path)
    _owned_by(monkeypatch, {1: "trainer", 4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)])
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)
    clock = iter([0.0, 0.0, 10.0])

    result = background_session.show_background_session(
        tmp_path, "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert result.session_id == 4
    assert "could not be released" in result.message
    assert "Show again" in result.message
    disconnect.assert_called_once_with(4)
    launch.assert_not_called()


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


# ---------------------------------------------------------------------------------------------
# Resolving a live background session the marker can no longer name, and disconnecting it
# ---------------------------------------------------------------------------------------------


def _engines_in(monkeypatch, *session_ids: int | None, own: int | None = 1) -> None:
    monkeypatch.setattr(background_session, "current_session_id", lambda: own)
    monkeypatch.setattr(
        background_session,
        "find_engine_processes",
        lambda: [EngineProcess(100 + index, session_id) for index, session_id in enumerate(session_ids)],
    )


def test_a_live_session_running_an_engine_is_adopted_when_the_marker_is_stale(
    monkeypatch, tmp_path: Path
) -> None:
    # The reported failure: a reboot renumbers sessions, so the recorded id names nothing and every
    # action reported "not running" at a machine where the background session was plainly working.
    _write_marker(tmp_path, session_id=6)
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])

    marker, status = background_session.resolve_background_session(tmp_path, "trainer")

    assert status == "adopted"
    assert marker is not None and marker.session_id == 3
    # Rewritten, so the next call is a plain marker hit and Stop's owner re-check has a pair to
    # compare against rather than a shortcut around it.
    written = json.loads((tmp_path / background_session.STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert written["session_id"] == 3
    assert written["username"] == "trainer"


def test_a_resolvable_marker_is_never_second_guessed_by_adoption(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path, session_id=4)
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer", 4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE), SessionInfo(4, SessionState.ACTIVE)],
    )

    marker, status = background_session.resolve_background_session(tmp_path, "trainer")

    assert status == "ok"
    assert marker is not None and marker.session_id == 4


def test_two_sessions_running_an_engine_are_reported_as_ambiguous(monkeypatch, tmp_path: Path) -> None:
    # Picking one would mean disconnecting or signing out a session on a guess.
    _engines_in(monkeypatch, 3, 5)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer", 5: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE), SessionInfo(5, SessionState.ACTIVE)],
    )

    marker, status = background_session.resolve_background_session(tmp_path, "trainer")

    assert status == "ambiguous"
    assert marker is None
    assert not (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_this_session_is_never_adopted_as_the_background_session(monkeypatch, tmp_path: Path) -> None:
    _engines_in(monkeypatch, 1, own=1)
    _owned_by(monkeypatch, {1: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])

    assert background_session.resolve_background_session(tmp_path, "trainer")[1] == "none"


def test_a_session_owned_by_another_account_is_not_adopted(monkeypatch, tmp_path: Path) -> None:
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer", 3: "someone-else"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])

    assert background_session.resolve_background_session(tmp_path, "trainer")[1] == "none"


def test_a_session_with_an_unreadable_owner_is_not_adopted(monkeypatch, tmp_path: Path) -> None:
    # Fails closed, the same rule _owner_matches already applies: an owner nobody can read is not
    # an owner that matched.
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])

    assert background_session.resolve_background_session(tmp_path, "trainer")[1] == "none"


def test_an_engine_session_that_no_longer_exists_is_not_adopted(monkeypatch, tmp_path: Path) -> None:
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])

    assert background_session.resolve_background_session(tmp_path, "trainer")[1] == "none"


def test_resolving_touches_no_windows_session_call_when_no_engine_runs_elsewhere(
    monkeypatch, tmp_path: Path
) -> None:
    _no_engines(monkeypatch)
    enumerate_sessions = MagicMock(return_value=[])
    monkeypatch.setattr(background_session, "list_sessions", enumerate_sessions)

    assert background_session.resolve_background_session(tmp_path, "trainer")[1] == "none"
    assert enumerate_sessions.call_count == 0


def test_start_refuses_when_a_running_engine_reveals_an_unrecorded_background_session(
    monkeypatch, tmp_path: Path
) -> None:
    # Without adoption this was the second half of the same bug: after a reboot Start saw "not
    # running" and would create a SECOND session against the engine still running in the first.
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])
    launch = MagicMock()
    monkeypatch.setattr(background_session, "_launch_mstsc", launch)

    result = background_session.start_background_session(tmp_path, "127.0.0.2", "trainer")

    assert result.ok is False
    assert "already running" in result.message
    assert launch.call_count == 0


def test_disconnect_drops_the_client_and_confirms_the_session_let_go(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path, session_id=4)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(4, SessionState.ACTIVE)],
        [SessionInfo(4, SessionState.ACTIVE)],
        [SessionInfo(4, SessionState.DISCONNECTED)],
    )
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)
    logoff = MagicMock()
    monkeypatch.setattr(background_session, "logoff_session", logoff)

    result = background_session.disconnect_background_session(tmp_path, "trainer", sleep=lambda _: None)

    assert result.ok is True
    assert "keeps running" in result.message
    assert disconnect.call_args[0][0] == 4
    # The whole point of the button: the session survives it.
    assert logoff.call_count == 0
    assert (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_disconnecting_an_already_disconnected_session_reports_success(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path, session_id=4)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.DISCONNECTED)])
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)

    result = background_session.disconnect_background_session(tmp_path, "trainer", sleep=lambda _: None)

    assert result.ok is True
    assert "already disconnected" in result.message
    assert disconnect.call_count == 0


def test_disconnect_reports_a_session_that_never_let_go(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path, session_id=4)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.ACTIVE)])
    monkeypatch.setattr(background_session, "disconnect_session", MagicMock(return_value=True))
    clock = iter([0.0, 100.0])

    result = background_session.disconnect_background_session(
        tmp_path, "trainer", sleep=lambda _: None, now=lambda: next(clock)
    )

    assert result.ok is False
    assert "may still be connected" in result.message


def test_disconnect_reports_nothing_to_do_when_no_session_is_running(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    monkeypatch.setattr(background_session, "list_sessions", lambda: [])

    result = background_session.disconnect_background_session(tmp_path, "trainer")

    assert result.ok is False
    assert result.message == "No background session is currently running."


def test_disconnect_refuses_while_two_sessions_run_an_engine(monkeypatch, tmp_path: Path) -> None:
    _engines_in(monkeypatch, 3, 5)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer", 5: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE), SessionInfo(5, SessionState.ACTIVE)],
    )
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)

    result = background_session.disconnect_background_session(tmp_path, "trainer")

    assert result.ok is False
    assert "more than one" in result.message.lower()
    assert disconnect.call_count == 0


def test_stop_signs_out_a_session_it_adopted(monkeypatch, tmp_path: Path) -> None:
    # Adoption already proved more than an "ok" marker does (our own engine, in a session that is
    # not ours, owned by a readable matching account), so Stop must not refuse it.
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)],
        [SessionInfo(1, SessionState.ACTIVE)],
    )
    logoff = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "logoff_session", logoff)

    result = background_session.stop_background_session(tmp_path, "trainer", sleep=lambda _: None)

    assert result.ok is True
    assert logoff.call_args[0][0] == 3
    assert not (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_no_session_is_adopted_when_this_processs_own_session_is_unknown(
    monkeypatch, tmp_path: Path
) -> None:
    # Fails closed: without knowing which session this process is in, "not this one" cannot be
    # established, and Stop could sign the user out of the desktop they are sitting at.
    _engines_in(monkeypatch, 3, own=None)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])

    assert background_session.resolve_background_session(tmp_path, "trainer")[1] == "none"


def test_no_session_is_adopted_when_this_processs_own_owner_cannot_be_read(
    monkeypatch, tmp_path: Path
) -> None:
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {3: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])

    assert background_session.resolve_background_session(tmp_path, "trainer")[1] == "none"


def test_a_blank_username_still_will_not_adopt_another_accounts_session(
    monkeypatch, tmp_path: Path
) -> None:
    # Merely opening the tab resolves the status, and the username field can be empty. If that
    # dropped the owner comparison, another user's macro session would be recorded as ours and a
    # later Stop would log them out.
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer", 3: "someone-else"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])

    marker, status = background_session.resolve_background_session(tmp_path, None)

    assert status == "none"
    assert marker is None
    assert not (tmp_path / background_session.STATE_FILE_NAME).exists()


def test_a_username_naming_a_different_account_than_this_process_is_not_adopted(
    monkeypatch, tmp_path: Path
) -> None:
    _engines_in(monkeypatch, 3)
    _owned_by(monkeypatch, {1: "trainer", 3: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])

    assert background_session.resolve_background_session(tmp_path, "someone-else")[1] == "none"


def test_the_same_account_name_in_another_domain_is_not_adopted(monkeypatch, tmp_path: Path) -> None:
    # A bare name is not an identity: DOMAIN-A\trainer must not adopt DOMAIN-B\trainer.
    _engines_in(monkeypatch, 3)
    domains = {1: "DOMAIN-A", 3: "DOMAIN-B"}
    monkeypatch.setattr(
        background_session,
        "session_owner",
        lambda session_id: (domains[session_id], "trainer") if session_id in domains else None,
    )
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE), SessionInfo(3, SessionState.ACTIVE)])

    assert background_session.resolve_background_session(tmp_path, "trainer")[1] == "none"


def test_disconnect_does_not_call_a_still_connected_session_already_disconnected(
    monkeypatch, tmp_path: Path
) -> None:
    # Only DISCONNECTED is the requested end state. CONNECTED still has a client on the session.
    _write_marker(tmp_path, session_id=4)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(
        monkeypatch,
        [SessionInfo(4, SessionState.CONNECTED)],
        [SessionInfo(4, SessionState.CONNECTED)],
        [SessionInfo(4, SessionState.DISCONNECTED)],
    )
    disconnect = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "disconnect_session", disconnect)

    result = background_session.disconnect_background_session(tmp_path, "trainer", sleep=lambda _: None)

    assert result.ok is True
    assert "already disconnected" not in result.message
    assert disconnect.call_args[0][0] == 4


def test_a_marker_naming_this_processs_own_session_is_never_acted_on(monkeypatch, tmp_path: Path) -> None:
    # Session ids are reused across reboots, so a stale marker can end up naming the console session
    # the user is sitting at, with a matching owner. Acting on it would disconnect or sign out the
    # desktop this app is running on.
    _write_marker(tmp_path, session_id=1)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    monkeypatch.setattr(background_session, "find_engine_processes", lambda: [])
    _owned_by(monkeypatch, {1: "trainer"})
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])
    logoff = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "logoff_session", logoff)

    marker, status = background_session.resolve_background_session(tmp_path, "trainer")

    assert (marker, status) == (None, "none")
    assert background_session.stop_background_session(tmp_path, "trainer").ok is False
    assert logoff.call_count == 0


# ---------------------------------------------------------------------------------------------
# Bringing the session's own client window to the front (the capture route)
# ---------------------------------------------------------------------------------------------


def _client_windows(monkeypatch, titles: dict[int, str], *, pids: list[int] | None = None) -> None:
    """Present a set of Remote Desktop client windows, keyed by handle, with their titles."""
    handles = list(titles)
    monkeypatch.setattr(background_session, "_client_process_ids", lambda: pids or [100])
    monkeypatch.setattr(background_session, "top_level_windows_for_process", lambda _pid: handles)
    monkeypatch.setattr(background_session, "_user32", lambda: object())
    monkeypatch.setattr(
        background_session, "_window_title", lambda _library, hwnd: titles.get(hwnd, "")
    )


def test_the_branded_window_wins_over_an_unrelated_remote_desktop_connection(monkeypatch) -> None:
    # The user may well have other Remote Desktop windows open. Pulling one of those to the front
    # would send the capture click to a desktop where the coordinate means nothing.
    _client_windows(
        monkeypatch,
        {
            11: "10.0.0.9 - Remote Desktop Connection",
            12: background_session.CLIENT_WINDOW_TITLE,
        },
    )

    assert background_session.find_client_window("127.0.0.2") == 12


def test_an_unbranded_window_is_matched_on_the_session_address(monkeypatch) -> None:
    # Start leaves its client window unbranded, so the loopback address the background session
    # lives on is the next best evidence.
    _client_windows(
        monkeypatch,
        {11: "10.0.0.9 - Remote Desktop Connection", 12: "127.0.0.2 - Remote Desktop Connection"},
    )

    assert background_session.find_client_window("127.0.0.2") == 12


def test_a_lone_unrelated_connection_is_never_taken_for_the_background_session(monkeypatch) -> None:
    # The dangerous case: one Remote Desktop window open, and it is somebody else's machine. Taking
    # it because it is the only one would focus that desktop and report the capture as ready there.
    _client_windows(monkeypatch, {11: "10.0.0.9 - Remote Desktop Connection"})

    assert background_session.find_client_window("127.0.0.2") is None


def test_several_indistinguishable_windows_are_left_alone(monkeypatch) -> None:
    _client_windows(monkeypatch, {11: "Connecting...", 12: "Also connecting..."})

    assert background_session.find_client_window("127.0.0.2") is None


def test_no_client_process_means_no_window(monkeypatch) -> None:
    monkeypatch.setattr(background_session, "_client_process_ids", lambda: [])
    monkeypatch.setattr(background_session, "_user32", lambda: object())

    assert background_session.find_client_window("127.0.0.2") is None


def test_an_existing_window_is_focused_without_touching_the_connection(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.ACTIVE)])
    monkeypatch.setattr(background_session, "find_client_window", lambda _address: 42)
    focused: list[int] = []
    monkeypatch.setattr(
        background_session, "focus_client_window", lambda hwnd: focused.append(hwnd) or True
    )
    show = MagicMock()
    monkeypatch.setattr(background_session, "show_background_session", show)

    result = background_session.ensure_background_session_visible(tmp_path, "trainer")

    assert result.ok is True
    assert focused == [42]
    # Reconnecting would have dropped and re-made a connection that was already fine.
    assert show.call_count == 0


def test_a_session_with_no_window_here_is_reconnected_and_then_focused(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.DISCONNECTED)])
    windows = iter([None, None, 42])
    monkeypatch.setattr(background_session, "find_client_window", lambda _address: next(windows))
    focused: list[int] = []
    monkeypatch.setattr(
        background_session, "focus_client_window", lambda hwnd: focused.append(hwnd) or True
    )
    monkeypatch.setattr(
        background_session,
        "show_background_session",
        lambda *args, **kwargs: background_session.BackgroundSessionResult(True, "Reconnecting.", 4),
    )

    result = background_session.ensure_background_session_visible(
        tmp_path, "trainer", sleep=lambda _seconds: None
    )

    assert result.ok is True
    assert focused == [42]


def test_a_window_that_never_comes_up_is_reported_rather_than_waited_on_forever(
    monkeypatch, tmp_path: Path
) -> None:
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.DISCONNECTED)])
    monkeypatch.setattr(background_session, "find_client_window", lambda _address: None)
    monkeypatch.setattr(
        background_session,
        "show_background_session",
        lambda *args, **kwargs: background_session.BackgroundSessionResult(True, "Reconnecting.", 4),
    )
    clock = iter([0.0, 0.0, 1.0, 2.0, 99.0])

    result = background_session.ensure_background_session_visible(
        tmp_path, "trainer", sleep=lambda _seconds: None, now=lambda: next(clock),
        window_wait_seconds=5.0,
    )

    assert result.ok is False
    assert "did not come up" in result.message


class _FakeUser32:
    def __init__(self, *, iconic: bool, activates: bool) -> None:
        self.iconic = iconic
        self.activates = activates
        self.restored: list[int] = []

    def IsIconic(self, hwnd):  # noqa: N802 - user32's own spelling
        return self.iconic

    def ShowWindow(self, hwnd, command):  # noqa: N802
        self.restored.append(command)
        return True

    def SetForegroundWindow(self, hwnd):  # noqa: N802
        return self.activates


def test_a_restored_window_that_windows_refuses_to_activate_is_not_called_in_front(
    monkeypatch,
) -> None:
    # Restoring succeeds and activating does not, which is the ordinary outcome while another
    # process holds the foreground lock. Reporting that as success would announce a window as being
    # in front while it sits un-minimized behind everything else.
    library = _FakeUser32(iconic=True, activates=False)
    monkeypatch.setattr(background_session, "_user32", lambda: library)

    assert background_session.focus_client_window(42) is False
    assert library.restored == [9]


def test_an_activated_window_reports_success(monkeypatch) -> None:
    library = _FakeUser32(iconic=False, activates=True)
    monkeypatch.setattr(background_session, "_user32", lambda: library)

    assert background_session.focus_client_window(42) is True
    # Not minimized, so nothing had to be restored.
    assert library.restored == []


def test_a_refused_activation_is_said_out_loud_rather_than_reported_as_in_front(
    monkeypatch, tmp_path: Path
) -> None:
    # Windows refuses SetForegroundWindow whenever another process holds the foreground lock. The
    # window is still restored and clickable, so the capture goes ahead, but the result must not
    # claim a window is in front when it is not.
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.ACTIVE)])
    monkeypatch.setattr(background_session, "find_client_window", lambda _address: 42)
    monkeypatch.setattr(background_session, "focus_client_window", lambda _hwnd: False)

    result = background_session.ensure_background_session_visible(tmp_path, "trainer")

    assert result.ok is True
    assert "could not be pulled to the front" in result.message


def test_no_background_session_is_reported_instead_of_opening_something(monkeypatch, tmp_path: Path) -> None:
    _no_engines(monkeypatch)
    _sessions(monkeypatch, [SessionInfo(1, SessionState.ACTIVE)])

    result = background_session.ensure_background_session_visible(tmp_path, "trainer")

    assert result.ok is False
    assert "No background session" in result.message


# ---------------------------------------------------------------------------------------------
# Hide: the window out of the way, the session's screen still running
# ---------------------------------------------------------------------------------------------


def test_hiding_minimizes_the_window_that_is_already_there(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.ACTIVE)])
    monkeypatch.setattr(background_session, "find_client_window", lambda _address: 42)
    minimized: list[int] = []
    monkeypatch.setattr(
        background_session, "minimize_client_window", lambda hwnd: minimized.append(hwnd) or True
    )
    show = MagicMock()
    monkeypatch.setattr(background_session, "show_background_session", show)

    result = background_session.hide_background_session_window(
        tmp_path, "trainer", screen_keeps_running=True
    )

    assert result.ok is True
    assert minimized == [42]
    assert result.client_window == 42
    # Nothing about the connection itself is touched: that is the whole difference from Disconnect.
    assert show.call_count == 0


def test_hiding_after_the_setting_was_just_written_reconnects_first(monkeypatch, tmp_path: Path) -> None:
    # A Remote Desktop client reads the "keep rendering while minimized" setting when it CONNECTS.
    # Minimizing a client that was already running when the setting was written would pause the
    # session's screen exactly as before, while the app claimed the opposite.
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.ACTIVE)])
    forced: list[bool] = []

    def visible(*_args, force_reconnect=False, **_kwargs):
        forced.append(force_reconnect)
        return background_session.BackgroundSessionResult(True, "Reconnected.", 4, client_window=77)

    monkeypatch.setattr(background_session, "ensure_background_session_visible", visible)
    minimized: list[int] = []
    monkeypatch.setattr(
        background_session, "minimize_client_window", lambda hwnd: minimized.append(hwnd) or True
    )

    result = background_session.hide_background_session_window(
        tmp_path, "trainer", reconnect_first=True, screen_keeps_running=True
    )

    assert result.ok is True
    assert minimized == [77]
    assert "reconnected" in result.message
    # Without this the helper would have focused the window that is already there, which is the
    # pre-setting client: the reconnect would never happen and the promise would be false.
    assert forced == [True]


def test_an_existing_window_is_replaced_rather_than_focused_when_a_reconnect_is_forced(
    monkeypatch, tmp_path: Path
) -> None:
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.ACTIVE)])
    # A window IS there. Focusing it is exactly what must not happen here.
    monkeypatch.setattr(background_session, "find_client_window", lambda _address: 42)
    focus = MagicMock(return_value=True)
    monkeypatch.setattr(background_session, "focus_client_window", focus)
    monkeypatch.setattr(background_session, "_first_window_for_pid", lambda _pid: 77)
    show = MagicMock(
        return_value=background_session.BackgroundSessionResult(True, "Reconnecting.", 4, 999)
    )
    monkeypatch.setattr(background_session, "show_background_session", show)

    result = background_session.ensure_background_session_visible(
        tmp_path, "trainer", force_reconnect=True, sleep=lambda _seconds: None
    )

    assert show.call_count == 1
    assert result.client_window == 77
    assert focus.call_args[0][0] == 77


def test_hiding_with_the_setting_off_says_detection_stops(monkeypatch, tmp_path: Path) -> None:
    # Unticking the option asks for Windows' default back. Hiding is still allowed, but the result
    # must not repeat the "screen keeps running" line the ticked case earns.
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.ACTIVE)])
    monkeypatch.setattr(background_session, "find_client_window", lambda _address: 42)
    monkeypatch.setattr(background_session, "minimize_client_window", lambda _hwnd: True)

    result = background_session.hide_background_session_window(
        tmp_path, "trainer", screen_keeps_running=False
    )

    assert result.ok is True
    assert "detection stops until you show it again" in result.message
    assert "keeps running" not in result.message


def test_hiding_a_session_with_no_window_here_leaves_it_alone(monkeypatch, tmp_path: Path) -> None:
    _write_marker(tmp_path)
    monkeypatch.setattr(background_session, "current_session_id", lambda: 1)
    _owned_by(monkeypatch, {4: "trainer"})
    _sessions(monkeypatch, [SessionInfo(4, SessionState.ACTIVE)])
    monkeypatch.setattr(background_session, "find_client_window", lambda _address: None)
    show = MagicMock()
    monkeypatch.setattr(background_session, "show_background_session", show)

    result = background_session.hide_background_session_window(
        tmp_path, "trainer", screen_keeps_running=True
    )

    assert result.ok is True
    assert "nothing to hide" in result.message
    # Reconnecting a window only to minimize it again would undo what the user already achieved.
    assert show.call_count == 0


def test_a_failed_reconnect_is_reported_instead_of_minimizing_nothing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        background_session,
        "ensure_background_session_visible",
        lambda *_a, **_k: background_session.BackgroundSessionResult(False, "No session."),
    )
    minimize = MagicMock()
    monkeypatch.setattr(background_session, "minimize_client_window", minimize)

    result = background_session.hide_background_session_window(
        tmp_path, "trainer", reconnect_first=True, screen_keeps_running=True
    )

    assert result.ok is False
    assert minimize.call_count == 0


def test_minimizing_is_judged_by_the_window_state_not_by_show_windows_return(monkeypatch) -> None:
    # ShowWindow returns the window's PREVIOUS visibility, so a window that was visible returns
    # true and one that was already minimized returns false: neither answers "is it minimized now".
    class _Library:
        def __init__(self, iconic_after: bool) -> None:
            self.iconic_after = iconic_after
            self.commands: list[int] = []

        def ShowWindow(self, hwnd, command):  # noqa: N802 - user32's own spelling
            self.commands.append(command)
            return False

        def IsIconic(self, hwnd):  # noqa: N802
            return self.iconic_after

    library = _Library(iconic_after=True)
    monkeypatch.setattr(background_session, "_user32", lambda: library)
    assert background_session.minimize_client_window(42) is True
    assert library.commands == [6]

    monkeypatch.setattr(background_session, "_user32", lambda: _Library(iconic_after=False))
    assert background_session.minimize_client_window(42) is False
