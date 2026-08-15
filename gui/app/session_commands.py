"""Deliver fixed commands from the physical desktop into the background Windows session.

The main window cannot start a process in another Windows session without administrator rights,
but the macro app already runs in that session. Both ends share this application's data directory,
so a small local file channel can hand that process the requested action. Unlike the remote bridge,
both ends are the same user on the same machine and its input is not untrusted. Commands still use a
fixed whitelist, so a malformed or unexpected file can never become a process launch instruction.

A command is a permission for ONE named session to act NOW, not a message waiting to be delivered,
which is why it carries both the Windows session it was aimed at and the moment it was written (see
COMMAND_WINDOW_SECONDS). The reader may simply not be there: a session that never started the macro
app, or none running at all. Neither half is redundant. Without the expiry the file would sit until
some later session came up and acted on it; without the session id, a background session STOPPED and
started again inside that window is a different session wearing the same channel, and it would carry
out a command the user aimed at the one they just ended. Both cases end the same way, Explorer or
Roblox opening in a session nobody asked for them in, which is the whole failure this channel has to
be unable to produce.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path


SESSION_CMD_FILE_NAME = "session_cmd.txt"
SESSION_ACK_FILE_NAME = "session_ack.txt"
START_EXPLORER = "START_EXPLORER"
START_ROBLOX = "START_ROBLOX"
KNOWN_COMMANDS = (START_EXPLORER, START_ROBLOX)
# How long a written command may still be acted on. A command file outlives the click that wrote
# it whenever nothing was there to claim it (no macro app in the session, or none running at all),
# and a file left on disk would otherwise be picked up by the NEXT background session that starts,
# which would open Explorer or Roblox in a session nobody asked it for. The same reasoning, and the
# same both-directions clock check, as session_autostart's arm window: this is a permission to act
# that has to expire on its own, because the process that would clean it up is exactly the one that
# may never arrive. Generous next to the caller's own few-second wait, since the only cost of a
# longer window is a slower expiry.
COMMAND_WINDOW_SECONDS = 60.0


def _path(data_directory: Path, name: str) -> Path:
    return Path(data_directory) / name


def write_command(
    data_directory: Path, command: str, session_id: int, *, now: float | None = None
) -> str | None:
    """Atomically leave one whitelisted command for ONE named Windows session to claim."""
    try:
        if command not in KNOWN_COMMANDS:
            raise ValueError("Unknown session command")
        command_path = _path(data_directory, SESSION_CMD_FILE_NAME)
        ack_path = _path(data_directory, SESSION_ACK_FILE_NAME)
        token = uuid.uuid4().hex
        issued_at = time.time() if now is None else now
        command_path.parent.mkdir(parents=True, exist_ok=True)
        ack_path.unlink(missing_ok=True)
        staging = command_path.with_name(command_path.name + ".tmp")
        staging.write_text(
            f"{token}|{issued_at}|{int(session_id)}|{command}", encoding="utf-8"
        )
        os.replace(staging, command_path)
        return token
    except (OSError, ValueError, TypeError):
        return None


def _claim(data_directory: Path) -> tuple[Path, str] | None:
    """Take the command file away by RENAME, and return where it went plus what it held.

    Renaming rather than reading and then deleting, for the reason session_autostart.consume_arm
    spells out: a read-then-delete lets two readers both act on one command, while a rename either
    wins or finds nothing.
    """
    command_path = _path(data_directory, SESSION_CMD_FILE_NAME)
    claimed = command_path.with_name(f"{command_path.name}.claim-{os.getpid()}")
    try:
        os.replace(command_path, claimed)
    except OSError:
        # Includes "there was no command" and "another reader took it" alike: both mean this call
        # has nothing to act on.
        return None
    try:
        return claimed, claimed.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return claimed, ""


def _parse(raw: str) -> tuple[str, float, int, str] | None:
    """Split a claimed payload into its four fields, or None when it is not one."""
    try:
        token, issued_at, session_id, command = raw.split("|", 3)
        return token, float(issued_at), int(session_id), command
    except ValueError:
        return None


def take_command(
    data_directory: Path, own_session: int | None, *, now: float | None = None
) -> tuple[str, str] | None:
    """Claim and consume one command, and act on it only if it was aimed at THIS session and now.

    ``own_session`` is the caller's own Windows session id. Being unable to answer that question
    refuses the command, the same way ensure_engine_running above fails closed on it: a caller that
    cannot tell which session it is in cannot tell whether a command was meant for it, and acting
    anyway is how a command aimed at a session the user has already ended gets carried out in its
    replacement.
    """
    claim = _claim(data_directory)
    if claim is None:
        return None
    claimed, raw = claim
    try:
        claimed.unlink(missing_ok=True)
    except OSError:
        pass
    parsed = _parse(raw)
    if parsed is None:
        return None
    token, issued_at, session_id, command = parsed
    if not token or command not in KNOWN_COMMANDS:
        return None
    if own_session is None or session_id != own_session:
        # Consumed rather than put back, even though it names somebody else. Putting it back means
        # writing the file again, which can land on top of a command written in the meantime, and
        # that is the worse failure of the two: the writer aims at exactly one session, so a command
        # this session finds and is not the target of has already missed the session it was for.
        return None
    current = time.time() if now is None else now
    # Both bounds, like session_autostart.consume_arm: a command stamped in the future is as
    # untrustworthy as an expired one, and the clock can genuinely move between the two sessions'
    # reads. An out-of-window command stays consumed rather than being put back, so a stale file
    # cannot be re-offered on every single poll.
    if not -COMMAND_WINDOW_SECONDS <= current - issued_at <= COMMAND_WINDOW_SECONDS:
        return None
    return token, command


def discard_command(data_directory: Path, token: str) -> None:
    """Withdraw a command this caller wrote and gave up waiting for.

    The expiry is the backstop for a caller that never comes back at all (the GUI was closed, the
    machine rebooted). This is the ordinary path: the caller is still here, it knows nothing claimed
    its command, and leaving the file behind would let a session started within the window act on a
    request the user has already been told went unanswered.

    Read FIRST and claim only on a match, which is the opposite order from take_command and
    deliberately so. Taking the file away before deciding would mean putting it back when the token
    turns out to be somebody else's, and writing this file again is exactly how a withdrawal could
    land on top of a command written in the meantime and swallow it. Reading first never writes at
    all: a command that is not this caller's is left exactly where it was, untouched.
    """
    command_path = _path(data_directory, SESSION_CMD_FILE_NAME)
    try:
        raw = command_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return
    parsed = _parse(raw)
    if parsed is None or parsed[0] != token:
        return
    claim = _claim(data_directory)
    if claim is None:
        return
    claimed, _raw = claim
    try:
        claimed.unlink(missing_ok=True)
    except OSError:
        pass


def write_ack(data_directory: Path, token: str, ok: bool, message: str) -> None:
    """Atomically write this command's outcome without allowing its text to break the payload."""
    try:
        ack_path = _path(data_directory, SESSION_ACK_FILE_NAME)
        clean_message = re.sub(r"[\r\n|]+", " ", message)
        ack_path.parent.mkdir(parents=True, exist_ok=True)
        staging = ack_path.with_name(ack_path.name + ".tmp")
        staging.write_text(
            f"{token}|{'ok' if ok else 'error'}|{clean_message}", encoding="utf-8"
        )
        os.replace(staging, ack_path)
    except (OSError, ValueError):
        pass


def read_ack(data_directory: Path, token: str) -> tuple[bool, str] | None:
    """Return and consume this token's answer, preserving another waiter's answer untouched."""
    ack_path = _path(data_directory, SESSION_ACK_FILE_NAME)
    try:
        raw = ack_path.read_text(encoding="utf-8")
        ack_token, outcome, message = raw.split("|", 2)
    except (OSError, ValueError):
        return None
    if ack_token != token or outcome not in ("ok", "error"):
        return None
    try:
        ack_path.unlink(missing_ok=True)
    except OSError:
        pass
    return outcome == "ok", message
