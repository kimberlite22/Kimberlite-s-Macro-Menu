from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from app import self_install
from app.launcher_paths import APP_NAME


def _frozen_install_environment(monkeypatch, tmp_path: Path) -> Path:
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.setattr(self_install, "is_frozen", lambda: True)
    return local_app_data / "Programs" / APP_NAME


def test_ensure_self_installed_copies_relaunches_and_preserves_arguments(monkeypatch, tmp_path: Path) -> None:
    installation_directory = _frozen_install_environment(monkeypatch, tmp_path)
    source_executable = tmp_path / "Downloads" / "gui.exe"
    source_executable.parent.mkdir()
    source_executable.write_bytes(b"new gui")
    monkeypatch.setattr(sys, "executable", str(source_executable))
    shortcut = MagicMock(return_value=True)
    popen = MagicMock()
    monkeypatch.setattr(self_install, "ensure_start_menu_shortcut", shortcut)
    monkeypatch.setattr(self_install.subprocess, "Popen", popen)

    assert self_install.ensure_self_installed(["--dir", "custom-data"]) is True

    installed = installation_directory / "gui.exe"
    assert installed.read_bytes() == b"new gui"
    shortcut.assert_called_once_with(installation_directory)
    popen.assert_called_once_with(
        [str(installed), "--dir", "custom-data"],
        creationflags=self_install.DETACHED_PROCESS,
    )


def test_ensure_self_installed_is_a_noop_when_already_installed(monkeypatch, tmp_path: Path) -> None:
    installation_directory = _frozen_install_environment(monkeypatch, tmp_path)
    installed = installation_directory / "gui.exe"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"gui")
    monkeypatch.setattr(sys, "executable", str(installed))
    popen = MagicMock()
    monkeypatch.setattr(self_install.subprocess, "Popen", popen)

    assert self_install.ensure_self_installed() is False
    popen.assert_not_called()


def test_failed_self_install_keeps_original_process_running(monkeypatch, tmp_path: Path, capsys) -> None:
    _frozen_install_environment(monkeypatch, tmp_path)
    source_executable = tmp_path / "gui.exe"
    source_executable.write_bytes(b"gui")
    monkeypatch.setattr(sys, "executable", str(source_executable))
    monkeypatch.setattr(self_install.shutil, "copy2", MagicMock(side_effect=OSError("disk full")))
    popen = MagicMock()
    monkeypatch.setattr(self_install.subprocess, "Popen", popen)

    assert self_install.ensure_self_installed() is False
    assert "continuing from the current location" in capsys.readouterr().err
    popen.assert_not_called()


def test_start_menu_shortcut_uses_escaped_powershell_paths(monkeypatch, tmp_path: Path) -> None:
    installation_directory = _frozen_install_environment(monkeypatch, tmp_path)
    completed = MagicMock(returncode=0)
    run = MagicMock(return_value=completed)
    monkeypatch.setattr(self_install.subprocess, "run", run)

    assert self_install.ensure_start_menu_shortcut(installation_directory) is True

    command = run.call_args.args[0]
    script = command[-1]
    assert command[:3] == ["powershell.exe", "-NoProfile", "-Command"]
    assert "Kimberlite''s Anime Expedition Macro.lnk" in script
    assert "$shortcut.TargetPath" in script
    assert "$shortcut.WorkingDirectory" in script
    assert run.call_args.kwargs["creationflags"] == self_install.CREATE_NO_WINDOW
    assert (tmp_path / "AppData" / "Microsoft" / "Windows" / "Start Menu" / "Programs").is_dir()


def test_powershell_single_quote_escaping() -> None:
    assert self_install._powershell_string("C:\\Users\\O'Neil\\gui.exe") == "'C:\\Users\\O''Neil\\gui.exe'"


def test_start_menu_shortcut_honors_aem_test_root(monkeypatch, tmp_path: Path) -> None:
    # A test run must never touch the REAL Windows Start Menu just because every other path was
    # correctly redirected under the test root - see launcher_paths.start_menu_dir().
    installation_directory = _frozen_install_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("AEM_TEST_ROOT", str(tmp_path / "test-root"))
    completed = MagicMock(returncode=0)
    run = MagicMock(return_value=completed)
    monkeypatch.setattr(self_install.subprocess, "run", run)

    assert self_install.ensure_start_menu_shortcut(installation_directory) is True

    script = run.call_args.args[0][-1]
    expected_link = tmp_path / "test-root" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"
    assert self_install._powershell_string(expected_link) in script
    assert (tmp_path / "test-root" / "Start Menu" / "Programs").is_dir()
    assert not (tmp_path / "AppData" / "Microsoft").exists()
