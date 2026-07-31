from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from ipc.client import STALE_COMMAND_AGE_SECONDS, IpcBusyError, IpcTimeoutError, LocalIpcClient, atomic_write


def _command_token(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("|", 1)[0]


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


def test_send_command_clears_an_abandoned_command_file_older_than_the_stale_threshold(
    tmp_path: Path,
) -> None:
    client = LocalIpcClient(tmp_path, poll_interval=0.01)
    atomic_write(client.command_path, "abandoned-token|START|{}\n")
    old_time = time.time() - STALE_COMMAND_AGE_SECONDS - 1
    os.utime(client.command_path, (old_time, old_time))

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
