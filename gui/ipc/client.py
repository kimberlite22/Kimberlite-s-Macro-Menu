"""Synchronous client for the local AHK file bridge."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .config_writer import (
    create_game,
    create_map_profile,
    create_preset,
    delete_game,
    delete_map_profile,
    delete_preset,
    export_preset,
    import_preset,
    rename_game,
    rename_map_profile,
    rename_preset,
    save_config,
    set_active_game,
    set_option_max,
    set_option_used_count,
)
from .protocol import (
    CaptureResult,
    GameProcessCandidate,
    LocalStatus,
    dumps_payload,
    parse_ack_line,
    parse_game_process_candidates,
)


COMMAND_FILENAME = "local_cmd.txt"
ACK_FILENAME = "local_ack.txt"
STATUS_FILENAME = "local_status.json"
CAPTURE_RESULT_FILENAME = "local_capture_result.txt"
GAME_PROCESSES_FILENAME = "local_game_processes.json"
CONFIG_FILENAME = "config.ini"

# LocalBridgeProcessCommand() (macro/local_bridge.ahk) deletes local_cmd.txt BEFORE dispatching
# its handler, so a file's age on disk measures how long it has sat UNCONSUMED, never how long a
# handler has been running - by the time a handler (even a slow one like PAIR_REMOTE_AGENT) is
# executing, the file is already gone. So a pending file's staleness is decided by whether the
# engine's own tick is still alive to pick it up at all, not by guessing how long a handler might
# legitimately run.
#
# LocalBridgeTick() (the SAME SetTimer callback that would consume this file) republishes
# local_status.json's "timestamp" field about every 125ms while the engine's main thread is alive
# and pumping messages. A heartbeat older than ENGINE_HEARTBEAT_STALE_SECONDS therefore means the
# engine cannot be about to consume the pending command, regardless of WHY (crashed, never
# started, or its message loop is stuck on something else) - unlike a fixed age guess on the
# command file alone, this stays correct no matter which of those actually happened, and reacts in
# a couple of seconds instead of a long fixed wait.
MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS = 1.0
ENGINE_HEARTBEAT_STALE_SECONDS = 3.0
STATUS_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class IpcTimeoutError(TimeoutError):
    """Raised when the AHK bridge did not acknowledge a command in time.

    A timeout does NOT mean the command was retracted: local_cmd.txt is a single
    slot with no cancellation mechanism, so AHK may still consume and execute it
    (and publish an ack nobody is waiting for) after this exception is raised.
    Callers should treat a timeout as "unknown outcome," not "definitely failed,"
    and should disable the triggering control until either an ack or a fresh
    status snapshot confirms the effect, rather than blindly resending.
    """


class IpcBusyError(RuntimeError):
    """Raised when a previous command is still unconsumed in local_cmd.txt.

    Only one command can be in flight at a time (single-slot file protocol,
    mirroring macro/remote_bridge.ahk) - sending a second one before AHK
    consumes the first would silently overwrite or race with it.
    """


@dataclass(frozen=True)
class CommandAck:
    token: str
    ok: bool
    message: str
    data: dict[str, Any]


def atomic_write(path: Path, text: str) -> None:
    """Publish UTF-8 text by replacing the target after writing its sibling .tmp file."""
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


class LocalIpcClient:
    """Blocking local-bridge client intended for a future timer or worker thread."""

    def __init__(self, data_dir: str | Path, poll_interval: float = 0.075) -> None:
        self.data_dir = Path(data_dir)
        self.poll_interval = poll_interval
        # Guards against a SECOND send_command call from this same client instance while a first
        # one is still awaiting its own acknowledgement - not covered by the command_path.exists()
        # check below, since AHK deletes local_cmd.txt almost immediately (well before a slow
        # handler like TEST_OCR returns), so a second call could otherwise write a fresh command
        # and race the first one's still-pending ack on the single shared local_ack.txt file.
        self._awaiting_ack = False

    @property
    def command_path(self) -> Path:
        return self.data_dir / COMMAND_FILENAME

    @property
    def ack_path(self) -> Path:
        return self.data_dir / ACK_FILENAME

    @property
    def status_path(self) -> Path:
        return self.data_dir / STATUS_FILENAME

    @property
    def capture_result_path(self) -> Path:
        return self.data_dir / CAPTURE_RESULT_FILENAME

    @property
    def game_processes_path(self) -> Path:
        return self.data_dir / GAME_PROCESSES_FILENAME

    @property
    def config_path(self) -> Path:
        return self.data_dir / CONFIG_FILENAME

    def save_config(self, **payloads: Any) -> str:
        """Persist config.ini here instead of asking the engine to do it.

        Deliberately NOT a command: config.ini is this process's file to write (see
        ipc/config_writer.py). Routing it through the client keeps every window that already holds
        one from needing a second injected dependency, and keeps the fakes in the tests in one place.
        """
        return save_config(self.config_path, **payloads)

    def create_preset(self, name: str, *, game: str) -> str:
        return create_preset(self.config_path, name, game=game)

    def rename_preset(self, old_name: str, new_name: str, *, game: str) -> str:
        status = self.read_status()
        return rename_preset(
            self.config_path, old_name, new_name, game=game,
            running=bool(status and status.running),
            running_preset=status.running_preset if status else "",
        )

    def delete_preset(self, name: str, *, game: str) -> str:
        status = self.read_status()
        return delete_preset(
            self.config_path, name, game=game,
            running=bool(status and status.running),
            running_preset=status.running_preset if status else "",
        )

    def export_preset(self, name: str, file_path: str, *, game: str) -> str:
        return export_preset(self.config_path, name, file_path, game=game)

    def import_preset(self, file_path: str, new_name: str, *, game: str) -> str:
        return import_preset(self.config_path, file_path, new_name, game=game)

    def create_map_profile(self, name: str, *, game: str) -> str:
        return create_map_profile(self.config_path, name, game=game)

    def rename_map_profile(self, old_name: str, new_name: str, *, game: str) -> str:
        status = self.read_status()
        return rename_map_profile(self.config_path, old_name, new_name, game=game, running=bool(status and status.running))

    def delete_map_profile(self, name: str, *, game: str) -> str:
        status = self.read_status()
        return delete_map_profile(self.config_path, name, game=game, running=bool(status and status.running))

    def set_option_used_count(self, preset_name: str, option_index: int, count: int, *, game: str) -> str:
        return set_option_used_count(self.config_path, preset_name, option_index, count, game=game)

    def set_option_max(self, preset_name: str, option_index: int, maximum: int, *, game: str) -> str:
        return set_option_max(self.config_path, preset_name, option_index, maximum, game=game)

    def create_game(self, name: str) -> str:
        return create_game(self.config_path, name)

    def rename_game(self, old_name: str, new_name: str) -> str:
        status = self.read_status()
        return rename_game(self.config_path, old_name, new_name, running=bool(status and status.running))

    def delete_game(self, name: str) -> str:
        status = self.read_status()
        return delete_game(self.config_path, name, running=bool(status and status.running))

    def set_active_game(self, name: str) -> str:
        status = self.read_status()
        return set_active_game(self.config_path, name, running=bool(status and status.running))

    def send_command(
        self, verb: str, payload: Mapping[str, Any], timeout: float = 5.0,
        pump: Callable[[], None] | None = None,
    ) -> CommandAck:
        """Send one command and wait for its matching acknowledgement.

        Stale acknowledgements stay untouched because they may belong to another
        client.  They are ignored until this command's token appears.

        Raises IpcBusyError instead of overwriting a still-unconsumed prior
        command (see that class's docstring) - callers should keep the
        triggering UI control disabled until this returns rather than firing
        commands back-to-back.

        `pump`, if given, is called once per poll iteration - pass Qt's
        `QApplication.processEvents` for a call whose timeout is long enough that
        blocking the whole GUI thread solid would be noticeable (e.g. a verb like
        PAIR_REMOTE_AGENT that legitimately needs tens of seconds); most callers
        with the short default timeout can leave this unset.
        """
        if self._awaiting_ack:
            raise IpcBusyError(
                "this client is still awaiting a previous command's acknowledgement - "
                "wait for it to return before sending another"
            )
        self._clear_abandoned_command_files()
        if self.command_path.exists() or self.command_path.with_name(
            self.command_path.name + ".tmp"
        ).exists():
            raise IpcBusyError(
                f"a previous command is still pending in {self.command_path} - "
                "wait for it to be consumed before sending another"
            )
        token = uuid.uuid4().hex
        json_payload = dumps_payload(payload)  # raises TypeError for non-JSON data
        self._awaiting_ack = True
        try:
            atomic_write(self.command_path, f"{token}|{verb}|{json_payload}\n")

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if pump is not None:
                    pump()
                ack = self._read_matching_ack(token)
                if ack is not None:
                    return ack
                time.sleep(self.poll_interval)
            raise IpcTimeoutError(f"timed out after {timeout:g}s waiting for {verb} acknowledgement")
        finally:
            self._awaiting_ack = False

    def _clear_abandoned_command_files(self) -> None:
        """Delete command_path/.tmp when the engine can no longer be about to consume it.

        A file younger than MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS is left alone
        unconditionally - the engine's own next tick (about every 125ms) may simply not have run
        yet. Past that, the decision is handed to _engine_heartbeat_is_stale() rather than a
        second fixed age guess: a fresh heartbeat means a real engine tick is still running (a
        handler may be about to consume this file), a stale/missing one means it cannot be,
        cleared immediately so a crashed, never-started, or stuck engine cannot block every future
        send_command() call.
        """
        candidates = (self.command_path, self.command_path.with_name(self.command_path.name + ".tmp"))
        existing = [path for path in candidates if path.exists()]
        if not existing:
            return

        # Gate on the YOUNGEST candidate, not the oldest: a concurrent client's own in-progress
        # atomic_write (a fresh .tmp about to replace command_path) must never be judged abandoned
        # just because an unrelated, genuinely old final file also happens to be sitting there.
        youngest_age = None
        for path in existing:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                continue  # consumed/removed between exists() and stat() - no longer in our way
            youngest_age = age if youngest_age is None else min(youngest_age, age)
        if youngest_age is None:
            return
        if youngest_age < MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS:
            return

        if not self._engine_heartbeat_is_stale():
            return  # a real engine tick is still running; leave its pending command alone

        for path in existing:
            try:
                path.unlink()
            except OSError:
                pass

    def _engine_heartbeat_is_stale(self) -> bool:
        """True when local_status.json's heartbeat is missing, unreadable, or too old to trust.

        The timestamp has one-second resolution and no UTC offset, so during the repeated local
        hour at a DST fall-back it is briefly ambiguous (could read as either occurrence, up to
        ~1h apart) - accepted here: a false "stale" verdict in that narrow, twice-a-year window
        only costs one extra retry (the client re-sends and the engine, if actually alive, picks
        the new command up normally), never a hang, which is the failure mode this replaces.
        """
        try:
            raw = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return True
        timestamp = raw.get("timestamp") if isinstance(raw, dict) else None
        if not isinstance(timestamp, str) or not timestamp:
            return True
        try:
            heartbeat = time.mktime(time.strptime(timestamp, STATUS_TIMESTAMP_FORMAT))
        except ValueError:
            return True
        return (time.time() - heartbeat) > ENGINE_HEARTBEAT_STALE_SECONDS

    def read_status(self) -> LocalStatus | None:
        """Return the latest status, or None when it is absent or transiently unreadable."""
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return LocalStatus.from_json_dict(data)

    def read_capture_result(self, consume: bool = False) -> CaptureResult | None:
        """Read the latest capture result, optionally consuming it after a valid read."""
        try:
            data = json.loads(self.capture_result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        result = CaptureResult.from_json_dict(data)
        if consume:
            try:
                self.capture_result_path.unlink()
            except OSError:
                pass
        return result

    def read_game_processes(self) -> list[GameProcessCandidate]:
        """Return the latest game-process candidate list, or [] when absent/unreadable."""
        try:
            data = json.loads(self.game_processes_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return []
        return parse_game_process_candidates(data)

    def _read_matching_ack(self, expected_token: str) -> CommandAck | None:
        try:
            token, data = parse_ack_line(self.ack_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return None
        if token != expected_token:
            return None
        return CommandAck(
            token=token,
            ok=bool(data.get("ok", False)),
            message=str(data.get("message", "")),
            data=data,
        )


class ConfigChangeTracker:
    """Detect config changes from either the bridge counter or config.ini mtime.

    A config_version bump is trusted immediately: LocalBridgeBumpConfigVersion() (macro/
    local_bridge.ahk) only runs AFTER a SAVE_*/NEW_*/RENAME_*/DELETE_* command has finished every
    one of its IniWrite calls, so by the time it is visible here the write is already done.

    A bare mtime change is not trustworthy the same way: AHK writes a save through many discrete
    IniWrite/IniDelete calls, and the file's mtime already moves on the very first one - and some
    writers (a startup migration, a hand edit, a differently-versioned bridge) never touch
    config_version at all, so mtime is still the only signal for those. Require the mtime to read
    the SAME value on two consecutive polls before treating it as a real, settled change, instead
    of reading (and racing) on the very first sign of movement. This adds at most one poll
    interval of latency to noticing an external change, but scales to any write-burst length
    automatically instead of needing a fixed retry budget guessed to outlast the largest save.
    """

    def __init__(self) -> None:
        self._config_version: int | None = None
        self._mtime_ns: int | None = None
        self._pending_mtime_ns: int | None = None

    def adopt(self, config_path: str | Path) -> None:
        """Accept config.ini's current mtime as already known, without reporting a change.

        Called right after this process writes the file itself. The write is complete and its
        content is already in hand, so re-reading it would only cost a poll and risk overwriting
        widgets the user has touched since. An external write still moves the mtime again and is
        picked up normally.
        """
        try:
            self._mtime_ns = Path(config_path).stat().st_mtime_ns
        except OSError:
            self._mtime_ns = None
        self._pending_mtime_ns = None

    def changed(self, status: LocalStatus | None, config_path: str | Path) -> bool:
        try:
            mtime_ns = Path(config_path).stat().st_mtime_ns
        except OSError:
            mtime_ns = None

        version = status.config_version if status is not None else None
        version_changed = version != self._config_version
        self._config_version = version

        mtime_changed = False
        if mtime_ns == self._mtime_ns:
            self._pending_mtime_ns = None
        elif mtime_ns == self._pending_mtime_ns:
            mtime_changed = True
            self._mtime_ns = mtime_ns
            self._pending_mtime_ns = None
        else:
            self._pending_mtime_ns = mtime_ns

        return version_changed or mtime_changed
