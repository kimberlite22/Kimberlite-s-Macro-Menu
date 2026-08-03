from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

from app import engine_process
from app.launcher_paths import ENGINE_EXE_NAME


def test_find_frozen_engine_copies_bundle_to_stable_install_path(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundled_engine = bundle / "engine" / ENGINE_EXE_NAME
    bundled_engine.parent.mkdir(parents=True)
    bundled_engine.write_bytes(b"bundled engine")
    installation_directory = tmp_path / "install"
    # Directly in install_directory, no "engine" subfolder - keeps the extracted path as short as
    # possible under the user's own (length-uncontrollable) profile. See engine_process.py's comment.
    stable_engine = installation_directory / ENGINE_EXE_NAME
    stable_engine.parent.mkdir(parents=True)
    stable_engine.write_bytes(b"old engine")
    monkeypatch.setattr(engine_process, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    assert engine_process.find_engine_executable(installation_directory) == [str(stable_engine)]
    assert stable_engine.read_bytes() == b"bundled engine"
    assert not stable_engine.with_suffix(".exe.staging").exists()


def test_find_frozen_engine_keeps_existing_payload_if_staged_copy_fails(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundled_engine = bundle / "engine" / ENGINE_EXE_NAME
    bundled_engine.parent.mkdir(parents=True)
    bundled_engine.write_bytes(b"bundled engine")
    installation_directory = tmp_path / "install"
    stable_engine = installation_directory / ENGINE_EXE_NAME
    stable_engine.parent.mkdir(parents=True)
    stable_engine.write_bytes(b"working engine")
    staging_engine = stable_engine.with_suffix(".exe.staging")
    monkeypatch.setattr(engine_process, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    def partial_copy(_: Path, destination: Path) -> None:
        Path(destination).write_bytes(b"partial engine")
        raise OSError("disk full")

    monkeypatch.setattr(engine_process.shutil, "copy2", partial_copy)

    assert engine_process.find_engine_executable(installation_directory) is None
    assert stable_engine.read_bytes() == b"working engine"
    assert not staging_engine.exists()


def test_find_source_engine_ignores_compiled_dev_copy(monkeypatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    compiled_engine = repository / "macro" / "dist" / ENGINE_EXE_NAME
    compiled_engine.parent.mkdir(parents=True)
    compiled_engine.write_bytes(b"engine")
    monkeypatch.setattr(engine_process, "is_frozen", lambda: False)
    monkeypatch.setattr(engine_process, "source_repo_root", lambda: repository)

    assert engine_process.find_engine_executable(None) is None


def test_find_source_engine_falls_back_to_autohotkey(monkeypatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    script = repository / "macro" / "tower_defense_macro_gui.ahk"
    script.parent.mkdir(parents=True)
    script.write_text("#Requires AutoHotkey v2.0", encoding="utf-8")
    monkeypatch.setattr(engine_process, "is_frozen", lambda: False)
    monkeypatch.setattr(engine_process, "source_repo_root", lambda: repository)
    monkeypatch.setattr(engine_process.shutil, "which", lambda _: "C:/AutoHotkey/AutoHotkey64.exe")

    assert engine_process.find_engine_executable(None) == [
        "C:/AutoHotkey/AutoHotkey64.exe",
        str(script),
        "--headless",
    ]


def test_engine_running_matches_only_exact_image_name(monkeypatch) -> None:
    run = MagicMock(return_value=MagicMock(stdout=f'"{ENGINE_EXE_NAME}",1234,"Console"'))
    monkeypatch.setattr(engine_process.subprocess, "run", run)

    assert engine_process.is_engine_running() is True
    command = run.call_args.args[0]
    assert command == [
        "tasklist.exe", "/FI", f"IMAGENAME eq {ENGINE_EXE_NAME}", "/FO", "CSV", "/NH",
    ]
    assert run.call_args.kwargs["creationflags"] == engine_process.CREATE_NO_WINDOW


def test_engine_running_ignores_localized_no_match_message(monkeypatch) -> None:
    monkeypatch.setattr(
        engine_process.subprocess,
        "run",
        MagicMock(return_value=MagicMock(stdout="INFO: Keine Tasks entsprechen den angegebenen Kriterien.")),
    )

    assert engine_process.is_engine_running() is False


def test_launch_engine_adds_headless_and_removes_stale_ready_marker(monkeypatch, tmp_path: Path) -> None:
    marker = tmp_path / "engine_ready.txt"
    marker.write_text("stale", encoding="utf-8")
    process = MagicMock()
    popen = MagicMock(return_value=process)
    monkeypatch.setattr(engine_process.subprocess, "Popen", popen)

    assert engine_process.launch_engine_hidden([str(tmp_path / ENGINE_EXE_NAME)], tmp_path) is process

    assert not marker.exists()
    popen.assert_called_once_with(
        [str(tmp_path / ENGINE_EXE_NAME), "--headless"],
        creationflags=engine_process.CREATE_NO_WINDOW,
    )


def test_launch_engine_keeps_autohotkey_fallback_arguments_intact(monkeypatch, tmp_path: Path) -> None:
    popen = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(engine_process.subprocess, "Popen", popen)
    fallback = ["AutoHotkey64.exe", "macro.ahk", "--headless"]

    engine_process.launch_engine_hidden(fallback, tmp_path)

    popen.assert_called_once_with(fallback, creationflags=engine_process.CREATE_NO_WINDOW)


def test_wait_for_engine_ready_handles_immediate_marker_and_timeout(tmp_path: Path) -> None:
    (tmp_path / "engine_ready.txt").write_text("ready", encoding="utf-8")
    assert engine_process.wait_for_engine_ready(tmp_path, timeout_seconds=0) is True

    (tmp_path / "engine_ready.txt").unlink()
    assert engine_process.wait_for_engine_ready(tmp_path, timeout_seconds=0) is False


def test_wait_for_local_command_slot_waits_for_real_command_and_staging_files(tmp_path: Path) -> None:
    command = tmp_path / "local_cmd.txt"
    staging = tmp_path / "local_cmd.txt.tmp"
    command.write_text("token|SAVE_GENERAL|{}\n", encoding="utf-8")
    staging.write_text("incomplete replacement", encoding="utf-8")

    # A persisted ready marker is unrelated to whether the single command slot is usable.
    (tmp_path / "engine_ready.txt").write_text("ready", encoding="utf-8")
    assert engine_process.wait_for_engine_ready(tmp_path, timeout_seconds=0) is True
    assert engine_process.wait_for_local_command_slot(tmp_path, timeout_seconds=0) is False

    def consume_pending_command() -> None:
        command.unlink()
        staging.unlink()

    assert engine_process.wait_for_local_command_slot(
        tmp_path, timeout_seconds=1, pump=consume_pending_command,
    ) is True
    assert not command.exists()
    assert not staging.exists()


def test_stop_engine_uses_graceful_taskkill_when_the_engine_exits(monkeypatch) -> None:
    process = MagicMock()
    process.pid = 1234
    process.poll.return_value = None
    process.wait.return_value = 0
    run = MagicMock()
    monkeypatch.setattr(engine_process.subprocess, "run", run)

    engine_process.stop_engine(process)

    run.assert_called_once_with(
        ["taskkill.exe", "/PID", "1234"],
        check=False,
        creationflags=engine_process.CREATE_NO_WINDOW,
        timeout=engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS,
    )
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_stop_engine_escalates_to_a_tree_kill_before_touching_popen_terminate(monkeypatch) -> None:
    # Regression test: Popen.terminate()/kill() are single-process kills, so escalating through
    # them orphans the ocr_server.exe bootloader/child pair the engine spawned. taskkill /T takes
    # the whole tree, so it has to come first; the owned handle stays a last resort for the case
    # where taskkill.exe itself could not be launched or did not take.
    process = MagicMock()
    process.pid = 1234
    process.poll.return_value = None
    process.wait.side_effect = [
        subprocess.TimeoutExpired("engine", engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS),
        subprocess.TimeoutExpired("engine", engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS),
        0,
    ]
    run = MagicMock()
    monkeypatch.setattr(engine_process.subprocess, "run", run)

    engine_process.stop_engine(process)

    assert [call_args.args[0] for call_args in run.call_args_list] == [
        ["taskkill.exe", "/PID", "1234"],
        ["taskkill.exe", "/PID", "1234", "/T", "/F"],
    ]
    process.terminate.assert_called_once_with()
    process.kill.assert_not_called()


def test_stop_engine_waits_use_the_short_shared_shutdown_budget(monkeypatch) -> None:
    # Regression test: both waits used to be five seconds each, plus a third after Popen.kill(),
    # all of it synchronous on the Qt main thread inside aboutToQuit. That is the "closing takes
    # at least a second" half of this bug.
    process = MagicMock()
    process.pid = 1234
    process.poll.return_value = None
    process.wait.side_effect = [
        subprocess.TimeoutExpired("engine", engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS),
        0,
    ]
    run = MagicMock()
    monkeypatch.setattr(engine_process.subprocess, "run", run)

    engine_process.stop_engine(process)

    assert engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS <= 1
    assert process.wait.call_args_list == [
        call(timeout=engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS),
        call(timeout=engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS),
    ]
    # taskkill.exe itself is bounded too, or the shutdown budget would still depend on an external
    # process choosing to return.
    for call_args in run.call_args_list:
        assert call_args.kwargs["timeout"] == engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS


def test_stop_engine_leaves_unowned_or_exited_process_alone() -> None:
    process = MagicMock()
    process.poll.return_value = 0

    engine_process.stop_engine(None)
    engine_process.stop_engine(process)

    process.terminate.assert_not_called()


def test_get_engine_pid_parses_the_matching_row(monkeypatch) -> None:
    run = MagicMock(return_value=MagicMock(stdout=f'"{ENGINE_EXE_NAME}",4321,"Console"'))
    monkeypatch.setattr(engine_process.subprocess, "run", run)

    assert engine_process.get_engine_pid() == 4321


def test_get_engine_pid_returns_none_when_not_running(monkeypatch) -> None:
    monkeypatch.setattr(
        engine_process.subprocess,
        "run",
        MagicMock(return_value=MagicMock(stdout="INFO: Keine Tasks entsprechen den angegebenen Kriterien.")),
    )

    assert engine_process.get_engine_pid() is None


def test_stop_engine_by_pid_uses_graceful_taskkill_when_handle_reports_exit(monkeypatch) -> None:
    run = MagicMock()
    get_engine_pid = MagicMock()
    monkeypatch.setattr(engine_process.subprocess, "run", run)
    monkeypatch.setattr(engine_process, "get_engine_pid", get_engine_pid)
    monkeypatch.setattr(engine_process, "_open_process_handle", MagicMock(return_value=99))
    monkeypatch.setattr(engine_process, "_close_process_handle", MagicMock())
    monkeypatch.setattr(engine_process, "_wait_for_process_exit", MagicMock(return_value=True))

    engine_process.stop_engine_by_pid(4321)

    run.assert_called_once_with(
        ["taskkill.exe", "/PID", "4321"],
        check=False,
        creationflags=engine_process.CREATE_NO_WINDOW,
        timeout=engine_process.ENGINE_SHUTDOWN_TIMEOUT_SECONDS,
    )
    # The whole point of waiting on the handle: the old code inferred liveness by spawning
    # tasklist.exe once per poll, and that spawn cost more than the sleep between polls.
    get_engine_pid.assert_not_called()


def test_stop_engine_by_pid_force_kills_after_polling_fallback_timeout(monkeypatch) -> None:
    run = MagicMock()
    monkeypatch.setattr(engine_process.subprocess, "run", run)
    # Still present on every poll (never reaches None or a different PID), so the graceful wait
    # times out and the force-kill fallback fires.
    monkeypatch.setattr(engine_process, "get_engine_pid", MagicMock(return_value=4321))
    monkeypatch.setattr(engine_process, "_open_process_handle", MagicMock(return_value=None))
    monkeypatch.setattr(engine_process, "_wait_for_process_exit", MagicMock(return_value=None))
    monkeypatch.setattr(engine_process.time, "sleep", MagicMock())

    engine_process.stop_engine_by_pid(4321, timeout_seconds=0)

    assert [call_args.args[0] for call_args in run.call_args_list] == [
        ["taskkill.exe", "/PID", "4321"],
        ["taskkill.exe", "/PID", "4321", "/T", "/F"],
    ]


def test_stop_engine_by_pid_does_not_force_kill_a_replacement_process(monkeypatch) -> None:
    run = MagicMock()
    monkeypatch.setattr(engine_process.subprocess, "run", run)
    # A different PID now holds the image name - the original process is gone, and the new one
    # must not be touched by a stale PID's shutdown.
    monkeypatch.setattr(engine_process, "get_engine_pid", MagicMock(return_value=9999))
    monkeypatch.setattr(engine_process, "_open_process_handle", MagicMock(return_value=None))
    monkeypatch.setattr(engine_process, "_wait_for_process_exit", MagicMock(return_value=None))

    engine_process.stop_engine_by_pid(4321, timeout_seconds=0)

    run.assert_called_once_with(
        ["taskkill.exe", "/PID", "4321"],
        check=False,
        creationflags=engine_process.CREATE_NO_WINDOW,
        timeout=0,
    )


def test_stop_engine_by_pid_rechecks_the_image_name_before_force_killing(monkeypatch) -> None:
    # Regression test: the process handle pins the PID only from the moment it is opened, which is
    # at shutdown. The PID itself was captured back when this launch attached to an already-running
    # engine, so the process behind it may since have exited and Windows may have handed that PID
    # to something unrelated. Wait-says-still-running is therefore not on its own a licence to
    # "/T /F" that PID.
    run = MagicMock()
    monkeypatch.setattr(engine_process.subprocess, "run", run)
    monkeypatch.setattr(engine_process, "get_engine_pid", MagicMock(return_value=9999))
    monkeypatch.setattr(engine_process, "_open_process_handle", MagicMock(return_value=99))
    monkeypatch.setattr(engine_process, "_close_process_handle", MagicMock())
    monkeypatch.setattr(engine_process, "_wait_for_process_exit", MagicMock(return_value=False))

    engine_process.stop_engine_by_pid(4321)

    assert [call_args.args[0] for call_args in run.call_args_list] == [
        ["taskkill.exe", "/PID", "4321"],
    ]


def test_stop_engine_by_pid_force_kills_when_handle_reports_still_running(monkeypatch) -> None:
    run = MagicMock()
    monkeypatch.setattr(engine_process.subprocess, "run", run)
    monkeypatch.setattr(engine_process, "get_engine_pid", MagicMock(return_value=4321))
    monkeypatch.setattr(engine_process, "_open_process_handle", MagicMock(return_value=99))
    monkeypatch.setattr(engine_process, "_close_process_handle", MagicMock())
    monkeypatch.setattr(engine_process, "_wait_for_process_exit", MagicMock(return_value=False))

    engine_process.stop_engine_by_pid(4321)

    assert [call_args.args[0] for call_args in run.call_args_list] == [
        ["taskkill.exe", "/PID", "4321"],
        ["taskkill.exe", "/PID", "4321", "/T", "/F"],
    ]


def test_stop_engine_by_pid_pins_the_pid_across_the_whole_shutdown(monkeypatch) -> None:
    # Regression test: the handle must be opened BEFORE the graceful taskkill and released only
    # after the force-kill. Opening it just around the wait leaves two windows (before the wait,
    # and between the wait and the escalation) in which the process can exit and Windows can hand
    # its PID to an unrelated one, which "/T /F" would then kill instead.
    order: list[str] = []
    monkeypatch.setattr(
        engine_process,
        "_open_process_handle",
        lambda _: (order.append("open"), 99)[1],
    )
    monkeypatch.setattr(
        engine_process,
        "_close_process_handle",
        lambda handle: order.append(f"close:{handle}"),
    )
    monkeypatch.setattr(
        engine_process,
        "_wait_for_process_exit",
        lambda handle, _: (order.append(f"wait:{handle}"), False)[1],
    )
    monkeypatch.setattr(engine_process, "get_engine_pid", lambda: 4321)
    monkeypatch.setattr(
        engine_process.subprocess,
        "run",
        lambda command, **_: order.append(" ".join(command[1:])),
    )

    engine_process.stop_engine_by_pid(4321)

    assert order == [
        "open",
        "/PID 4321",
        "wait:99",
        "/PID 4321 /T /F",
        "close:99",
    ]


def test_process_handle_helpers_report_unavailable_outside_windows(monkeypatch) -> None:
    monkeypatch.setattr(engine_process.sys, "platform", "linux")

    assert engine_process._open_process_handle(4321) is None
    assert engine_process._wait_for_process_exit(99, 1.0) is None
    # Must stay a no-op rather than raise, so the finally in stop_engine_by_pid is always safe.
    assert engine_process._close_process_handle(99) is None
