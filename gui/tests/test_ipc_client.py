from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from ipc.client import (
    ENGINE_HEARTBEAT_STALE_SECONDS,
    MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS,
    STATUS_TIMESTAMP_FORMAT,
    ConfigChangeTracker,
    IpcBusyError,
    IpcTimeoutError,
    LocalIpcClient,
    atomic_write,
)
from ipc.config_writer import IniDocument, MutationError
from ipc.protocol import LocalStatus


def _command_token(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("|", 1)[0]


def _write_heartbeat(client: LocalIpcClient, age_seconds: float) -> None:
    """Publish a local_status.json whose "timestamp" is `age_seconds` in the past."""
    timestamp = time.strftime(STATUS_TIMESTAMP_FORMAT, time.localtime(time.time() - age_seconds))
    atomic_write(client.status_path, f'{{"timestamp":"{timestamp}"}}')


def test_send_command_writes_utf8_without_bom_and_matches_ack(tmp_path: Path) -> None:
    client = LocalIpcClient(tmp_path, poll_interval=0.01)

    def acknowledge() -> None:
        while not client.command_path.exists():
            time.sleep(0.002)
        atomic_write(client.ack_path, _command_token(client.command_path) + '|{"ok":true,"message":"done"}\n')

    thread = threading.Thread(target=acknowledge)
    thread.start()
    ack = client.send_command("START", {"text": "x | y"}, timeout=1)
    thread.join()
    command = client.command_path.read_bytes()
    assert not command.startswith(b"\xef\xbb\xbf")
    assert ack.ok is True and ack.message == "done"


def test_send_command_ignores_stale_ack_until_correct_token(tmp_path: Path) -> None:
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.ack_path, 'old-token|{"ok":true,"message":"old"}\n')

    def acknowledge() -> None:
        while not client.command_path.exists():
            time.sleep(0.002)
        time.sleep(0.03)
        atomic_write(client.ack_path, _command_token(client.command_path) + '|{"ok":false,"message":"new"}\n')

    thread = threading.Thread(target=acknowledge)
    thread.start()
    ack = client.send_command("SAVE_GENERAL", {}, timeout=1)
    thread.join()
    assert ack.ok is False and ack.message == "new"


def test_send_command_times_out_when_no_ack_arrives(tmp_path: Path) -> None:
    with pytest.raises(IpcTimeoutError, match="START"):
        LocalIpcClient(tmp_path, poll_interval=0.01).send_command("START", {}, timeout=0.05)


def test_send_command_refuses_while_a_prior_command_is_unconsumed(tmp_path: Path) -> None:
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.command_path, "stale-token|START|{}\n")

    with pytest.raises(IpcBusyError):
        client.send_command("START", {}, timeout=0.05)

    # The stale command file must be left untouched, not clobbered by the refused send.
    assert _command_token(client.command_path) == "stale-token"


def test_send_command_clears_an_abandoned_command_file_when_engine_heartbeat_is_stale(
    tmp_path: Path,
) -> None:
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.command_path, "abandoned-token|START|{}\n")
    old_time = time.time() - MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS - 1
    os.utime(client.command_path, (old_time, old_time))
    _write_heartbeat(client, ENGINE_HEARTBEAT_STALE_SECONDS + 1)

    def acknowledge() -> None:
        # Wait for the REAL new command, not the pre-existing abandoned one: a bare
        # `command_path.exists()` check would fire immediately on the still-present stale file,
        # racing this thread's read against send_command's own unlink of that same file.
        token = "abandoned-token"
        while token == "abandoned-token":
            time.sleep(0.002)
            try:
                token = _command_token(client.command_path)
            except FileNotFoundError:
                token = "abandoned-token"
        atomic_write(client.ack_path, token + '|{"ok":true,"message":"done"}\n')

    thread = threading.Thread(target=acknowledge)
    thread.start()
    ack = client.send_command("START", {}, timeout=1)
    thread.join()

    assert ack.ok is True
    assert _command_token(client.command_path) != "abandoned-token"


def test_send_command_clears_an_abandoned_command_file_when_heartbeat_file_is_missing(
    tmp_path: Path,
) -> None:
    # No local_status.json at all (engine never started, or crashed before writing one) must be
    # treated the same as a stale heartbeat, not as "still alive" - this was the case that used to
    # stay stuck for the full STALE_COMMAND_AGE_SECONDS wait before it was cleared at all.
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.command_path, "abandoned-token|START|{}\n")
    old_time = time.time() - MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS - 1
    os.utime(client.command_path, (old_time, old_time))

    with pytest.raises(IpcTimeoutError):
        client.send_command("START", {}, timeout=0.2)

    assert _command_token(client.command_path) != "abandoned-token"


def test_send_command_stays_busy_while_engine_heartbeat_is_fresh(tmp_path: Path) -> None:
    # A pending command older than the minimum liveness-check age must NOT be cleared out from
    # under a genuinely alive engine just because it has not been consumed on this exact tick -
    # a fresh heartbeat means a real engine tick is still running and may pick it up next.
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.command_path, "in-flight-token|START|{}\n")
    old_time = time.time() - MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS - 1
    os.utime(client.command_path, (old_time, old_time))
    _write_heartbeat(client, 0.0)

    with pytest.raises(IpcBusyError):
        client.send_command("START", {}, timeout=0.05)

    assert _command_token(client.command_path) == "in-flight-token"


def test_send_command_never_clears_a_command_file_younger_than_the_minimum_check_age(
    tmp_path: Path,
) -> None:
    # Even with no heartbeat at all, a command file written moments ago must be left alone - the
    # engine's own next tick (about every 125ms) may simply not have run yet.
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.command_path, "brand-new-token|START|{}\n")

    with pytest.raises(IpcBusyError):
        client.send_command("START", {}, timeout=0.05)

    assert _command_token(client.command_path) == "brand-new-token"


def test_send_command_leaves_a_fresh_tmp_write_alone_even_if_the_final_file_is_stale(
    tmp_path: Path,
) -> None:
    # Regression test: staleness must be judged on the YOUNGEST candidate, not the oldest - a
    # concurrent client's own in-progress atomic_write (a fresh .tmp about to replace
    # command_path) must never be wiped out just because an unrelated, genuinely old final file
    # also happens to be sitting there. No heartbeat is published at all, so if the youngest-file
    # rule were broken (gating on the old final file's age instead), this alone would be enough
    # to clear both files.
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.command_path, "abandoned-token|START|{}\n")
    old_time = time.time() - MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS - 1
    os.utime(client.command_path, (old_time, old_time))
    tmp_path_file = client.command_path.with_name(client.command_path.name + ".tmp")
    tmp_path_file.write_text("in-progress-token|START|{}\n", encoding="utf-8")

    with pytest.raises(IpcBusyError):
        client.send_command("START", {}, timeout=0.05)

    assert tmp_path_file.exists()
    assert _command_token(client.command_path) == "abandoned-token"


def test_engine_heartbeat_treated_as_stale_when_timestamp_is_malformed(tmp_path: Path) -> None:
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.command_path, "abandoned-token|START|{}\n")
    old_time = time.time() - MIN_COMMAND_AGE_BEFORE_LIVENESS_CHECK_SECONDS - 1
    os.utime(client.command_path, (old_time, old_time))
    atomic_write(client.status_path, '{"timestamp":"not-a-real-timestamp"}')

    with pytest.raises(IpcTimeoutError):
        client.send_command("START", {}, timeout=0.2)

    assert _command_token(client.command_path) != "abandoned-token"


def test_read_status_returns_none_for_missing_or_invalid_snapshot(tmp_path: Path) -> None:
    client = LocalIpcClient(tmp_path)
    assert client.read_status() is None
    client.status_path.write_text("{", encoding="utf-8")
    assert client.read_status() is None
    client.status_path.write_text('{"running":true,"configVersion":4}', encoding="utf-8")
    assert client.read_status() is not None
    assert client.read_status().config_version == 4


def test_read_capture_result_parses_and_optionally_consumes_valid_result(tmp_path: Path) -> None:
    client = LocalIpcClient(tmp_path)
    assert client.read_capture_result() is None
    client.capture_result_path.write_text('{"mode":"point","fieldId":"id","x":12.5,"y":25}', encoding="utf-8")

    result = client.read_capture_result(consume=True)

    assert result is not None and result.field_id == "id"
    assert (result.x, result.y) == (12.5, 25.0)
    assert not client.capture_result_path.exists()


def test_read_game_processes_returns_empty_for_missing_or_invalid_data(tmp_path: Path) -> None:
    client = LocalIpcClient(tmp_path)
    assert client.read_game_processes() == []

    client.game_processes_path.write_text(
        '{"processes":[{"title":"Roblox","process":"RobloxPlayerBeta.exe"}]}',
        encoding="utf-8",
    )
    assert client.read_game_processes()[0].process == "RobloxPlayerBeta.exe"
    assert client.game_processes_path.exists()

    client.game_processes_path.write_text("{", encoding="utf-8")
    assert client.read_game_processes() == []


def test_config_change_tracker_defers_a_bare_mtime_change_until_it_settles(tmp_path: Path) -> None:
    # Regression test: AHK writes a save through many discrete IniWrite calls, and the file's
    # mtime already moves on the very first one - reporting "changed" on the first sign of
    # movement used to make main_window.py re-read config.ini mid-burst, occasionally losing the
    # sharing-violation race even past config_reader's own short retry and showing "config.ini
    # could not be read" to the user.
    config_path = tmp_path / "config.ini"
    config_path.write_text("x", encoding="utf-8")
    tracker = ConfigChangeTracker()
    assert tracker.changed(None, config_path) is False  # establishes the baseline

    os.utime(config_path, (time.time(), time.time() + 1))
    assert tracker.changed(None, config_path) is False  # first sign of movement - still pending
    os.utime(config_path, (time.time(), time.time() + 2))
    assert tracker.changed(None, config_path) is False  # moved again - burst still in progress

    # No further write: the same mtime is now observed on two consecutive polls - settled.
    assert tracker.changed(None, config_path) is True
    assert tracker.changed(None, config_path) is False  # already accounted for


def test_config_change_tracker_trusts_a_config_version_bump_immediately(tmp_path: Path) -> None:
    # A config_version bump is safe to trust right away - LocalBridgeBumpConfigVersion() only
    # runs after a save command's IniWrite calls have all finished - so it must not be held back
    # by the mtime debounce above, which exists only because mtime itself is not that reliable.
    config_path = tmp_path / "config.ini"
    config_path.write_text("x", encoding="utf-8")
    tracker = ConfigChangeTracker()
    tracker.changed(LocalStatus(config_version=1), config_path)  # establish the baseline

    assert tracker.changed(LocalStatus(config_version=2), config_path) is True
    assert tracker.changed(LocalStatus(config_version=2), config_path) is False


def test_rename_and_delete_preset_consult_live_status_for_the_running_guard(tmp_path: Path) -> None:
    # config_writer.rename_preset()/delete_preset() only reject a running preset when told it is
    # one - this is the client-layer glue that actually reads local_status.json and passes
    # running/running_preset through, the one piece of real logic client.py adds over a bare
    # pass-through to config_writer.
    client = LocalIpcClient(tmp_path)
    document = IniDocument()
    document.set("Game_Anime Expedition_Presets", "List", "Alpha,Beta")
    document.write_atomic(client.config_path)
    client.status_path.write_text('{"running":true,"runningPreset":"Alpha"}', encoding="utf-8")

    with pytest.raises(MutationError, match="currently running"):
        client.rename_preset("Alpha", "Gamma", game="Anime Expedition")
    with pytest.raises(MutationError, match="currently running"):
        client.delete_preset("Alpha", game="Anime Expedition")

    # A different, non-running preset is unaffected by the same live status.
    client.rename_preset("Beta", "Gamma", game="Anime Expedition")
    assert IniDocument.load(client.config_path).get("Game_Anime Expedition_Presets", "List") == "Alpha,Gamma"
