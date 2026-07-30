from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QMessageBox, QWidget

from app import main
from app.update_check import AvailableUpdate, UpdateError


UPDATE = AvailableUpdate(version="9.9.9", sha256="a" * 64, download_url="https://example.invalid/release.exe")


def _window(qtbot) -> QWidget:
    """A real widget (message boxes need a live parent) with the window's status-bar helper."""
    window = QWidget()
    qtbot.addWidget(window)
    window._show_message = MagicMock()
    return window


def _answer(monkeypatch, button: QMessageBox.StandardButton) -> MagicMock:
    question = MagicMock(return_value=button)
    monkeypatch.setattr(main.QMessageBox, "question", question)
    return question


def _arrange(monkeypatch, *, update: AvailableUpdate | None, target: Path | None) -> None:
    monkeypatch.setattr(main, "read_current_version", lambda _: "1.0.0")
    monkeypatch.setattr(main, "check_available_update", lambda _: update)
    monkeypatch.setattr(main, "self_update_target", lambda: target)


def test_a_development_launch_only_announces_the_update(monkeypatch, qtbot, tmp_path: Path) -> None:
    # allow_install=False is the --dir / unfrozen case: there is no release executable to replace,
    # so the check must never prompt, let alone start an installation.
    _arrange(monkeypatch, update=UPDATE, target=None)
    question = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    install = MagicMock()
    monkeypatch.setattr(main, "_install_update", install)
    window = _window(qtbot)

    main._schedule_update_check(window, tmp_path, allow_install=False)

    qtbot.waitUntil(lambda: window._show_message.called, timeout=3000)
    window._show_message.assert_called_once_with("Update available: v9.9.9 (current v1.0.0).")
    question.assert_not_called()
    install.assert_not_called()


def test_declining_the_prompt_leaves_the_notice_and_installs_nothing(monkeypatch, qtbot, tmp_path: Path) -> None:
    _arrange(monkeypatch, update=UPDATE, target=tmp_path / "gui.exe")
    _answer(monkeypatch, QMessageBox.StandardButton.No)
    install = MagicMock()
    monkeypatch.setattr(main, "_install_update", install)
    window = _window(qtbot)

    main._schedule_update_check(window, tmp_path, allow_install=True)

    qtbot.waitUntil(lambda: window._show_message.called, timeout=3000)
    window._show_message.assert_called_once_with("Update available: v9.9.9 (current v1.0.0).")
    install.assert_not_called()


def test_accepting_the_prompt_installs_into_the_running_executable(monkeypatch, qtbot, tmp_path: Path) -> None:
    target = tmp_path / "gui.exe"
    _arrange(monkeypatch, update=UPDATE, target=target)
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    install = MagicMock()
    monkeypatch.setattr(main, "_install_update", install)
    window = _window(qtbot)

    main._schedule_update_check(window, tmp_path, allow_install=True)

    qtbot.waitUntil(lambda: install.called, timeout=3000)
    install.assert_called_once_with(window, UPDATE, target, tmp_path)


def test_no_update_available_stays_completely_silent(monkeypatch, qtbot, tmp_path: Path) -> None:
    _arrange(monkeypatch, update=None, target=tmp_path / "gui.exe")
    question = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window = _window(qtbot)

    main._schedule_update_check(window, tmp_path, allow_install=True)

    qtbot.wait(400)
    window._show_message.assert_not_called()
    question.assert_not_called()


def test_a_finished_download_hands_the_swap_to_the_helper_and_quits(monkeypatch, qtbot, tmp_path: Path) -> None:
    target = tmp_path / "gui.exe"
    download = MagicMock(side_effect=lambda update, destination, progress=None: progress(4, 4))
    install = MagicMock()
    application = MagicMock()
    monkeypatch.setattr(main, "download_update", download)
    monkeypatch.setattr(main, "install_update", install)
    monkeypatch.setattr(main, "QApplication", application)
    window = _window(qtbot)

    main._install_update(window, UPDATE, target, tmp_path)

    qtbot.waitUntil(lambda: application.quit.called, timeout=3000)
    staged = download.call_args.args[1]
    assert staged.parent == tmp_path and staged.suffix == ".update"
    install.assert_called_once_with(staged, target, sha256=UPDATE.sha256)


def test_a_failed_download_reports_the_reason_and_keeps_the_app_running(monkeypatch, qtbot, tmp_path: Path) -> None:
    monkeypatch.setattr(main, "download_update", MagicMock(side_effect=UpdateError("Checksum mismatch.")))
    install = MagicMock()
    application = MagicMock()
    warning = MagicMock()
    monkeypatch.setattr(main, "install_update", install)
    monkeypatch.setattr(main, "QApplication", application)
    monkeypatch.setattr(main.QMessageBox, "warning", warning)
    window = _window(qtbot)

    main._install_update(window, UPDATE, tmp_path / "gui.exe", tmp_path)

    qtbot.waitUntil(lambda: warning.called, timeout=3000)
    assert "Checksum mismatch." in warning.call_args.args[2]
    install.assert_not_called()
    application.quit.assert_not_called()


def test_a_failing_helper_is_reported_instead_of_quitting(monkeypatch, qtbot, tmp_path: Path) -> None:
    monkeypatch.setattr(main, "download_update", MagicMock(return_value=tmp_path / "release.update"))
    monkeypatch.setattr(main, "install_update", MagicMock(side_effect=UpdateError("no shell")))
    application = MagicMock()
    warning = MagicMock()
    monkeypatch.setattr(main, "QApplication", application)
    monkeypatch.setattr(main.QMessageBox, "warning", warning)
    window = _window(qtbot)

    main._install_update(window, UPDATE, tmp_path / "gui.exe", tmp_path)

    qtbot.waitUntil(lambda: warning.called, timeout=3000)
    application.quit.assert_not_called()
