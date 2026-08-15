from __future__ import annotations

from pathlib import Path

from app import session_commands


# The Windows session a command is aimed at. Every test names one explicitly, because "which session
# is this for" is half of what decides whether a command may be acted on at all.
TARGET_SESSION = 4


def test_a_command_round_trips_and_is_consumed(tmp_path: Path) -> None:
    token = session_commands.write_command(
        tmp_path, session_commands.START_EXPLORER, TARGET_SESSION
    )

    assert token is not None
    assert session_commands.take_command(tmp_path, TARGET_SESSION) == (
        token,
        session_commands.START_EXPLORER,
    )
    assert session_commands.take_command(tmp_path, TARGET_SESSION) is None


def test_an_unknown_command_is_not_written(tmp_path: Path) -> None:
    assert session_commands.write_command(tmp_path, "RUN_ANYTHING", TARGET_SESSION) is None
    assert not (tmp_path / session_commands.SESSION_CMD_FILE_NAME).exists()


def test_an_unknown_payload_is_dropped_without_being_returned(tmp_path: Path) -> None:
    """The whitelist is checked on the READING side too, not only where the file is written."""
    (tmp_path / session_commands.SESSION_CMD_FILE_NAME).write_text(
        f"token|2000.0|{TARGET_SESSION}|RUN_ANYTHING", encoding="utf-8"
    )

    assert session_commands.take_command(tmp_path, TARGET_SESSION, now=2000.0) is None
    assert not (tmp_path / session_commands.SESSION_CMD_FILE_NAME).exists()


def test_a_malformed_payload_is_dropped_without_being_returned(tmp_path: Path) -> None:
    (tmp_path / session_commands.SESSION_CMD_FILE_NAME).write_text(
        "not-a-command-file", encoding="utf-8"
    )

    assert session_commands.take_command(tmp_path, TARGET_SESSION) is None
    assert not (tmp_path / session_commands.SESSION_CMD_FILE_NAME).exists()


def test_a_command_for_another_session_is_never_acted_on(tmp_path: Path) -> None:
    """Stop then Start puts a NEW session behind the same channel, well inside the expiry window."""
    session_commands.write_command(tmp_path, session_commands.START_EXPLORER, TARGET_SESSION)

    assert session_commands.take_command(tmp_path, TARGET_SESSION + 1) is None


def test_a_reader_that_cannot_name_its_own_session_refuses_the_command(tmp_path: Path) -> None:
    """It cannot tell whether the command was meant for it, so it fails closed."""
    session_commands.write_command(tmp_path, session_commands.START_ROBLOX, TARGET_SESSION)

    assert session_commands.take_command(tmp_path, None) is None


def test_a_command_older_than_its_window_is_dropped_rather_than_acted_on(tmp_path: Path) -> None:
    """A file nothing claimed must not be picked up by the NEXT background session that starts."""
    token = session_commands.write_command(
        tmp_path, session_commands.START_ROBLOX, TARGET_SESSION, now=1000.0
    )

    assert token is not None
    assert (
        session_commands.take_command(
            tmp_path, TARGET_SESSION, now=1000.0 + session_commands.COMMAND_WINDOW_SECONDS + 1.0
        )
        is None
    )
    # Consumed even though it was refused, or a stale file would be re-offered on every poll.
    assert not (tmp_path / session_commands.SESSION_CMD_FILE_NAME).exists()


def test_a_command_stamped_in_the_future_is_refused_like_an_expired_one(tmp_path: Path) -> None:
    """The clock can genuinely move between the two sessions' reads, in either direction."""
    session_commands.write_command(
        tmp_path, session_commands.START_EXPLORER, TARGET_SESSION, now=5000.0
    )

    assert (
        session_commands.take_command(
            tmp_path, TARGET_SESSION, now=5000.0 - session_commands.COMMAND_WINDOW_SECONDS - 1.0
        )
        is None
    )


def test_a_command_inside_its_window_is_still_served(tmp_path: Path) -> None:
    token = session_commands.write_command(
        tmp_path, session_commands.START_EXPLORER, TARGET_SESSION, now=2000.0
    )

    assert session_commands.take_command(tmp_path, TARGET_SESSION, now=2005.0) == (
        token,
        session_commands.START_EXPLORER,
    )


def test_withdrawing_a_command_removes_the_caller_s_own_request(tmp_path: Path) -> None:
    token = session_commands.write_command(
        tmp_path, session_commands.START_EXPLORER, TARGET_SESSION
    )

    assert token is not None
    session_commands.discard_command(tmp_path, token)

    assert not (tmp_path / session_commands.SESSION_CMD_FILE_NAME).exists()
    assert session_commands.take_command(tmp_path, TARGET_SESSION) is None


def test_withdrawing_leaves_a_command_belonging_to_another_wait_untouched(tmp_path: Path) -> None:
    """Giving up on one wait may never swallow the request that replaced it."""
    token = session_commands.write_command(tmp_path, session_commands.START_ROBLOX, TARGET_SESSION)
    before = (tmp_path / session_commands.SESSION_CMD_FILE_NAME).read_text(encoding="utf-8")

    session_commands.discard_command(tmp_path, "an-older-token")

    # Not rewritten, not even identically: a withdrawal that writes this file at all is one that can
    # land on top of a command written in the meantime.
    assert (tmp_path / session_commands.SESSION_CMD_FILE_NAME).read_text(encoding="utf-8") == before
    assert session_commands.take_command(tmp_path, TARGET_SESSION) == (
        token,
        session_commands.START_ROBLOX,
    )


def test_withdrawing_when_there_is_nothing_to_withdraw_is_harmless(tmp_path: Path) -> None:
    session_commands.discard_command(tmp_path, "token")

    assert session_commands.take_command(tmp_path, TARGET_SESSION) is None


def test_an_acknowledgement_round_trips_and_is_consumed(tmp_path: Path) -> None:
    session_commands.write_ack(tmp_path, "token", True, "Started|cleanly\nnow")

    assert session_commands.read_ack(tmp_path, "token") == (True, "Started cleanly now")
    assert not (tmp_path / session_commands.SESSION_ACK_FILE_NAME).exists()


def test_an_acknowledgement_for_another_token_is_left_for_its_waiter(tmp_path: Path) -> None:
    session_commands.write_ack(tmp_path, "other-token", False, "Could not start.")

    assert session_commands.read_ack(tmp_path, "this-token") is None
    assert (tmp_path / session_commands.SESSION_ACK_FILE_NAME).exists()


def test_a_missing_directory_or_unreadable_file_returns_none(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "directory"

    assert session_commands.take_command(missing, TARGET_SESSION) is None
    assert session_commands.read_ack(missing, "token") is None

    command_path = tmp_path / session_commands.SESSION_CMD_FILE_NAME
    command_path.write_text(f"token|2000.0|{TARGET_SESSION}|START_EXPLORER", encoding="utf-8")

    def unreadable(*_args, **_kwargs):
        raise OSError("denied")

    monkeypatch.setattr(Path, "read_text", unreadable)

    assert session_commands.take_command(tmp_path, TARGET_SESSION) is None
