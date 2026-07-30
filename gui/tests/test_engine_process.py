from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from app import engine_process
from app.launcher_paths import ENGINE_EXE_NAME


def test_find_frozen_engine_copies_bundle_to_stable_install_path(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundled_engine = bundle / "engine" / ENGINE_EXE_NAME
    bundled_engine.parent.mkdir(parents=True)
    bundled_engine.write_bytes(b"bundled engine")
    installation_directory = tmp_path / "install"
    stable_engine = installation_directory / "engine" / ENGINE_EXE_NAME
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
    stable_engine = installation_directory / "engine" / ENGINE_EXE_NAME
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
    )
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_stop_engine_kills_only_after_graceful_and_terminate_timeouts(monkeypatch) -> None:
    process = MagicMock()
    process.pid = 1234
    process.poll.return_value = None
    process.wait.side_effect = [
        subprocess.TimeoutExpired("engine", 5),
        subprocess.TimeoutExpired("engine", 5),
        None,
    ]
    monkeypatch.setattr(engine_process.subprocess, "run", MagicMock())

    engine_process.stop_engine(process)

    process.terminate.assert_called_once_with()
    process.kill.assert_called_once_with()
    assert process.wait.call_count == 3


def test_stop_engine_leaves_unowned_or_exited_process_alone() -> None:
    process = MagicMock()
    process.poll.return_value = 0

    engine_process.stop_engine(None)
    engine_process.stop_engine(process)

    process.terminate.assert_not_called()
