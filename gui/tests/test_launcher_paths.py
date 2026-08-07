from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import launcher_paths
from app import main
from app.engine_process import EngineProcess
from app.main import _build_arg_parser, _resolve_data_dir


class _FakeApplication:
    def __init__(self, _: list[str]) -> None:
        self.aboutToQuit = MagicMock()

    def setStyle(self, _: str) -> None:
        pass

    def setStyleSheet(self, _: str) -> None:
        pass

    def setApplicationName(self, _: str) -> None:
        pass

    def setApplicationDisplayName(self, _: str) -> None:
        pass

    def setWindowIcon(self, _: object) -> None:
        pass

    def processEvents(self) -> None:
        pass

    def exec(self) -> int:
        return 0


class _ProcessExit(Exception):
    pass


def test_default_data_dir_uses_localappdata_for_frozen_launch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local App Data"))
    monkeypatch.delenv("AEM_TEST_ROOT", raising=False)
    monkeypatch.setattr(launcher_paths, "is_frozen", lambda: True)

    assert launcher_paths.default_data_dir() == (
        tmp_path / "Local App Data" / "Kimberlite's Macro Menu"
    )


def test_install_and_data_dir_honor_aem_test_root(monkeypatch, tmp_path: Path) -> None:
    # Mirrors tower_defense_macro_gui.ahk's own InstallTestRoot check, so an integration test that
    # sets this env var to isolate the compiled AHK engine from a real LOCALAPPDATA isolates the
    # GUI's self-install/engine paths the same way, instead of the GUI still touching the real one.
    monkeypatch.setenv("AEM_TEST_ROOT", str(tmp_path / "test-root"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local App Data"))

    assert launcher_paths.install_dir() == tmp_path / "test-root" / "Programs" / launcher_paths.APP_NAME
    assert launcher_paths.data_dir() == tmp_path / "test-root" / "AppData" / launcher_paths.APP_NAME


def test_install_and_data_dir_ignore_blank_aem_test_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AEM_TEST_ROOT", "   ")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local App Data"))

    assert launcher_paths.install_dir() == tmp_path / "Local App Data" / "Programs" / launcher_paths.APP_NAME
    assert launcher_paths.data_dir() == tmp_path / "Local App Data" / launcher_paths.APP_NAME


def test_legacy_install_dir_mirrors_install_dir_for_the_previous_app_name(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.delenv("AEM_TEST_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local App Data"))

    assert launcher_paths.legacy_install_dir() == (
        tmp_path / "Local App Data" / "Programs" / launcher_paths.LEGACY_APP_NAME
    )


def test_legacy_install_dir_honors_aem_test_root(monkeypatch, tmp_path: Path) -> None:
    # Same isolation guarantee as install_dir(): a test run must never resolve a REAL legacy
    # LOCALAPPDATA path just because AEM_TEST_ROOT redirected every other path.
    monkeypatch.setenv("AEM_TEST_ROOT", str(tmp_path / "test-root"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local App Data"))

    assert launcher_paths.legacy_install_dir() == (
        tmp_path / "test-root" / "Programs" / launcher_paths.LEGACY_APP_NAME
    )


def test_default_data_dir_uses_source_macro_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(launcher_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(launcher_paths, "source_repo_root", lambda: tmp_path / "repo")

    assert launcher_paths.default_data_dir() == tmp_path / "repo" / "macro"


def test_app_icon_path_prefers_bundle_adjacent_file(tmp_path: Path) -> None:
    entry_file = tmp_path / "bundle" / "main.py"
    entry_file.parent.mkdir()
    entry_file.write_text("", encoding="utf-8")
    entry_file.with_name("app.ico").write_bytes(b"icon")

    assert launcher_paths.app_icon_path(entry_file) == entry_file.with_name("app.ico")


def test_app_icon_path_falls_back_to_repository_assets(tmp_path: Path) -> None:
    entry_file = tmp_path / "repository" / "gui" / "app" / "main.py"
    entry_file.parent.mkdir(parents=True)
    entry_file.write_text("", encoding="utf-8")
    assets_dir = tmp_path / "repository" / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.ico").write_bytes(b"icon")

    assert launcher_paths.app_icon_path(entry_file) == assets_dir / "app.ico"


def test_app_icon_path_returns_none_when_missing(tmp_path: Path) -> None:
    entry_file = tmp_path / "repository" / "gui" / "app" / "main.py"
    entry_file.parent.mkdir(parents=True)
    entry_file.write_text("", encoding="utf-8")

    assert launcher_paths.app_icon_path(entry_file) is None


def test_explicit_dir_overrides_launcher_default(monkeypatch, tmp_path: Path) -> None:
    explicit_directory = tmp_path / "explicit"
    monkeypatch.setattr("app.main.default_data_dir", lambda: tmp_path / "default")

    assert _resolve_data_dir(str(explicit_directory)) == explicit_directory.resolve()


def test_dir_option_is_optional() -> None:
    assert _build_arg_parser().parse_args([]).dir is None


def test_explicit_dir_frozen_launch_skips_self_install_and_engine_management(monkeypatch, tmp_path: Path) -> None:
    explicit_directory = tmp_path / "fixture"
    window = MagicMock()
    monkeypatch.setattr(main, "is_frozen", lambda: True)
    monkeypatch.setattr(main, "QApplication", _FakeApplication)
    monkeypatch.setattr(main, "MainWindow", window)
    monkeypatch.setattr(main, "_schedule_update_check", lambda *_, **__: None)
    self_install = MagicMock(return_value=False)
    monkeypatch.setattr(main, "ensure_self_installed", self_install)
    monkeypatch.setattr(main, "ensure_start_menu_shortcut", MagicMock())
    monkeypatch.setattr(main, "find_engine_processes", MagicMock())
    monkeypatch.setattr(main, "find_engine_executable", MagicMock())
    monkeypatch.setattr(main, "launch_engine_hidden", MagicMock())

    assert main.main(["--dir", str(explicit_directory)]) == 0

    self_install.assert_not_called()
    main.ensure_start_menu_shortcut.assert_not_called()
    main.find_engine_processes.assert_not_called()
    main.find_engine_executable.assert_not_called()
    main.launch_engine_hidden.assert_not_called()
    window.assert_called_once_with(
        explicit_directory.resolve(),
        auto_refresh_game_processes=True,
        engine_in_background_session=False,
        entry_file=Path(main.__file__),
    )


def test_default_frozen_launch_self_installs_and_manages_engine(monkeypatch, tmp_path: Path) -> None:
    installation_directory = tmp_path / "install"
    data_directory = tmp_path / "data"
    process = MagicMock()
    window = MagicMock()
    monkeypatch.setattr(main, "is_frozen", lambda: True)
    monkeypatch.setattr(main, "install_dir", lambda: installation_directory)
    monkeypatch.setattr(main, "default_data_dir", lambda: data_directory)
    monkeypatch.setattr(main, "QApplication", _FakeApplication)
    monkeypatch.setattr(main, "MainWindow", window)
    monkeypatch.setattr(main, "_schedule_update_check", lambda *_, **__: None)
    self_install = MagicMock(return_value=False)
    find_engine = MagicMock(return_value=["engine.exe"])
    launch_engine = MagicMock(return_value=process)
    monkeypatch.setattr(main, "ensure_self_installed", self_install)
    monkeypatch.setattr(main, "ensure_start_menu_shortcut", MagicMock())
    monkeypatch.setattr(main, "cleanup_legacy_installation", MagicMock())
    monkeypatch.setattr(main, "find_engine_processes", MagicMock(return_value=[]))
    monkeypatch.setattr(main, "find_engine_executable", find_engine)
    monkeypatch.setattr(main, "launch_engine_hidden", launch_engine)
    monkeypatch.setattr(main, "wait_for_engine_ready", MagicMock(return_value=True))

    assert main.main([]) == 0

    self_install.assert_called_once_with([])
    main.ensure_start_menu_shortcut.assert_called_once_with(installation_directory)
    main.cleanup_legacy_installation.assert_called_once_with(installation_directory)
    find_engine.assert_called_once_with(installation_directory)
    launch_engine.assert_called_once_with(["engine.exe"], data_directory)
    window.assert_called_once_with(
        data_directory,
        auto_refresh_game_processes=True,
        engine_in_background_session=False,
        entry_file=Path(main.__file__),
    )


def test_default_frozen_launch_waits_for_an_existing_engine_to_drain_pending_command(
    monkeypatch, tmp_path: Path,
) -> None:
    """A process match alone is not proof that its bridge can accept another command."""
    installation_directory = tmp_path / "install"
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    pending_command = data_directory / "local_cmd.txt"
    pending_staging_file = data_directory / "local_cmd.txt.tmp"
    pending_command.write_text("token|SAVE_GENERAL|{}\n", encoding="utf-8")
    pending_staging_file.write_text("incomplete replacement", encoding="utf-8")
    # A reused engine's marker persists, which is why the launch must also inspect the command
    # slot instead of treating this file as sufficient readiness proof.
    (data_directory / "engine_ready.txt").write_text("ready", encoding="utf-8")
    window = MagicMock()
    monkeypatch.setattr(main, "is_frozen", lambda: True)
    monkeypatch.setattr(main, "install_dir", lambda: installation_directory)
    monkeypatch.setattr(main, "default_data_dir", lambda: data_directory)
    monkeypatch.setattr(main, "QApplication", _FakeApplication)
    monkeypatch.setattr(main, "MainWindow", window)
    monkeypatch.setattr(main, "_schedule_update_check", lambda *_, **__: None)
    monkeypatch.setattr(main, "ensure_self_installed", MagicMock(return_value=False))
    monkeypatch.setattr(main, "ensure_start_menu_shortcut", MagicMock())
    monkeypatch.setattr(
        main, "find_engine_processes", MagicMock(return_value=[EngineProcess(4321, 1)])
    )
    monkeypatch.setattr(main, "shutdown_owned_engine_pid", MagicMock(return_value=4321))
    monkeypatch.setattr(main, "find_engine_executable", MagicMock(return_value=["engine.exe"]))
    launch_engine = MagicMock()
    monkeypatch.setattr(main, "launch_engine_hidden", launch_engine)

    def process_events(self: _FakeApplication) -> None:
        # The real waiting helper sees these files on disk. The event pump represents the existing
        # engine getting CPU time to consume its unknown-outcome command; the launcher never edits
        # or republishes it itself.
        assert pending_command.exists()
        assert pending_staging_file.exists()
        assert not window.called
        pending_command.unlink()
        pending_staging_file.unlink()

    monkeypatch.setattr(_FakeApplication, "processEvents", process_events)

    assert main.main([]) == 0

    launch_engine.assert_not_called()
    window.assert_called_once_with(
        data_directory,
        auto_refresh_game_processes=True,
        engine_in_background_session=False,
        entry_file=Path(main.__file__),
    )
    assert not pending_command.exists()
    assert not pending_staging_file.exists()


def test_attaching_launch_takes_ownership_of_the_engine_it_finds_running(
    monkeypatch, tmp_path: Path,
) -> None:
    """A launch that attaches to an already-running engine (not one it spawned) must still stop
    it on quit, or that engine survives every close indefinitely."""
    installation_directory = tmp_path / "install"
    data_directory = tmp_path / "data"
    window = MagicMock()
    app = _FakeApplication([])
    monkeypatch.setattr(main, "is_frozen", lambda: True)
    monkeypatch.setattr(main, "install_dir", lambda: installation_directory)
    monkeypatch.setattr(main, "default_data_dir", lambda: data_directory)
    monkeypatch.setattr(main, "QApplication", lambda _: app)
    monkeypatch.setattr(main, "MainWindow", window)
    monkeypatch.setattr(main, "_schedule_update_check", lambda *_, **__: None)
    monkeypatch.setattr(main, "ensure_self_installed", MagicMock(return_value=False))
    monkeypatch.setattr(main, "ensure_start_menu_shortcut", MagicMock())
    monkeypatch.setattr(
        main, "find_engine_processes", MagicMock(return_value=[EngineProcess(4321, 1)])
    )
    monkeypatch.setattr(main, "shutdown_owned_engine_pid", MagicMock(return_value=4321))
    monkeypatch.setattr(main, "find_engine_executable", MagicMock(return_value=["engine.exe"]))
    launch_engine = MagicMock()
    monkeypatch.setattr(main, "launch_engine_hidden", launch_engine)
    monkeypatch.setattr(main, "wait_for_engine_ready", MagicMock(return_value=True))
    stop_engine_by_pid = MagicMock()
    monkeypatch.setattr(main, "stop_engine_by_pid", stop_engine_by_pid)

    assert main.main([]) == 0

    launch_engine.assert_not_called()
    app.aboutToQuit.connect.assert_called_once()
    app.aboutToQuit.connect.call_args.args[0]()
    stop_engine_by_pid.assert_called_once_with(4321)


def test_attaching_launch_leaves_a_background_session_engine_running(
    monkeypatch, tmp_path: Path,
) -> None:
    """The mirror image of the test above: an engine in ANOTHER Windows session belongs to a
    background RDP session holding the game, so closing this GUI must not stop it. Without this,
    the shared user profile that makes the local bridge reach across sessions also makes every
    close of the window kill the macro running in the background."""
    installation_directory = tmp_path / "install"
    data_directory = tmp_path / "data"
    window = MagicMock()
    app = _FakeApplication([])
    monkeypatch.setattr(main, "is_frozen", lambda: True)
    monkeypatch.setattr(main, "install_dir", lambda: installation_directory)
    monkeypatch.setattr(main, "default_data_dir", lambda: data_directory)
    monkeypatch.setattr(main, "QApplication", lambda _: app)
    monkeypatch.setattr(main, "MainWindow", window)
    monkeypatch.setattr(main, "_schedule_update_check", lambda *_, **__: None)
    monkeypatch.setattr(main, "ensure_self_installed", MagicMock(return_value=False))
    monkeypatch.setattr(main, "ensure_start_menu_shortcut", MagicMock())
    monkeypatch.setattr(
        main, "find_engine_processes", MagicMock(return_value=[EngineProcess(4321, 2)])
    )
    monkeypatch.setattr(main, "shutdown_owned_engine_pid", MagicMock(return_value=None))
    monkeypatch.setattr(main, "find_engine_executable", MagicMock(return_value=["engine.exe"]))
    launch_engine = MagicMock()
    monkeypatch.setattr(main, "launch_engine_hidden", launch_engine)
    monkeypatch.setattr(main, "wait_for_engine_ready", MagicMock(return_value=True))
    stop_engine_by_pid = MagicMock()
    monkeypatch.setattr(main, "stop_engine_by_pid", stop_engine_by_pid)

    assert main.main([]) == 0

    # Still attached, so no second engine is spawned on top of the running one...
    launch_engine.assert_not_called()
    # ...but nothing is wired into shutdown, so quitting cannot reach that engine at all.
    app.aboutToQuit.connect.assert_not_called()
    stop_engine_by_pid.assert_not_called()
    window.assert_called_once_with(
        data_directory,
        auto_refresh_game_processes=True,
        engine_in_background_session=True,
        entry_file=Path(main.__file__),
    )


def test_empty_dir_argument_is_treated_the_same_as_omitted(monkeypatch, tmp_path: Path) -> None:
    # _resolve_data_dir() already falls back to the default directory for an empty string (same as
    # None) - engine management must agree, or "--dir """ would manage the engine against the
    # DEFAULT directory while claiming to be in explicit --dir (hands-off) mode.
    installation_directory = tmp_path / "install"
    data_directory = tmp_path / "data"
    window = MagicMock()
    monkeypatch.setattr(main, "is_frozen", lambda: True)
    monkeypatch.setattr(main, "install_dir", lambda: installation_directory)
    monkeypatch.setattr(main, "default_data_dir", lambda: data_directory)
    monkeypatch.setattr(main, "QApplication", _FakeApplication)
    monkeypatch.setattr(main, "MainWindow", window)
    monkeypatch.setattr(main, "_schedule_update_check", lambda *_, **__: None)
    self_install = MagicMock(return_value=False)
    monkeypatch.setattr(main, "ensure_self_installed", self_install)
    monkeypatch.setattr(main, "ensure_start_menu_shortcut", MagicMock())
    monkeypatch.setattr(main, "find_engine_processes", MagicMock(return_value=[]))
    monkeypatch.setattr(main, "find_engine_executable", MagicMock(return_value=None))
    monkeypatch.setattr(main, "launch_engine_hidden", MagicMock())

    assert main.main(["--dir", ""]) == 0

    self_install.assert_called_once_with(["--dir", ""])
    main.find_engine_processes.assert_called_once()
    window.assert_called_once_with(
        data_directory,
        auto_refresh_game_processes=True,
        engine_in_background_session=False,
        entry_file=Path(main.__file__),
    )


def test_run_terminates_the_process_with_mains_return_code(monkeypatch) -> None:
    # The executable entrypoint must pass Qt's exit code into the deterministic process exit.
    exit_codes: list[int] = []
    monkeypatch.setattr(main, "main", lambda _: 37)

    def exit_process(code: int) -> None:
        exit_codes.append(code)
        raise _ProcessExit

    monkeypatch.setattr(main.os, "_exit", exit_process)

    with pytest.raises(_ProcessExit):
        main.run(["--dir", "fixture"])

    assert exit_codes == [37]


def test_run_reaches_process_exit_while_a_daemon_thread_is_still_alive(monkeypatch) -> None:
    # A daemon update-check thread blocked in urlopen must not keep gui.exe alive after Qt exits.
    release_thread = threading.Event()
    thread_started = threading.Event()

    def block_update_check() -> None:
        thread_started.set()
        release_thread.wait()

    thread = threading.Thread(target=block_update_check, daemon=True)
    thread.start()
    assert thread_started.wait(timeout=1)
    monkeypatch.setattr(main, "main", lambda _: 0)

    def exit_process(_: int) -> None:
        assert thread.is_alive()
        raise _ProcessExit

    monkeypatch.setattr(main.os, "_exit", exit_process)
    try:
        with pytest.raises(_ProcessExit):
            main.run()
    finally:
        release_thread.set()
        thread.join(timeout=1)

    assert not thread.is_alive()


def test_terminate_process_handles_windowed_builds_without_standard_streams(monkeypatch) -> None:
    # PyInstaller windowed builds can set both standard streams to None during shutdown.
    exit_codes: list[int] = []
    monkeypatch.setattr(main.sys, "stdout", None)
    monkeypatch.setattr(main.sys, "stderr", None)

    def exit_process(code: int) -> None:
        exit_codes.append(code)
        raise _ProcessExit

    monkeypatch.setattr(main.os, "_exit", exit_process)

    with pytest.raises(_ProcessExit):
        main._terminate_process(19)

    assert exit_codes == [19]
