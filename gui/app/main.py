"""Launch the PySide6 presentation process for the local macro bridge."""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main_window import MainWindow
from app.engine_process import (
    find_engine_executable,
    is_engine_running,
    launch_engine_hidden,
    stop_engine,
    wait_for_engine_ready,
)
from app.launcher_paths import APP_NAME, APP_USER_MODEL_ID, app_icon_path, default_data_dir, install_dir, is_frozen
from app.self_install import ensure_self_installed, ensure_start_menu_shortcut
from app.update_check import check_for_update, read_current_version


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="animeexpedition-gui",
        description="PySide6 GUI for Kimberlite's Anime Expedition Macro.",
    )
    parser.add_argument(
        "--dir",
        help="Directory containing config.ini and the local bridge files.",
    )
    return parser


def _resolve_data_dir(directory: str | None) -> Path:
    """Resolve an explicit data directory or the engine-compatible default."""
    return Path(directory).resolve() if directory else default_data_dir().resolve()


def _schedule_update_notice(window: MainWindow) -> None:
    """Fetch update metadata off the Qt thread and show a status-bar notice if needed."""
    current_version = read_current_version(Path(__file__))
    if current_version is None:
        return

    result: dict[str, str | bool | None] = {"done": False, "version": None}

    def fetch_update() -> None:
        try:
            result["version"] = check_for_update(current_version)
        except Exception:
            # The checker is best-effort.  Keep the Qt-side polling callback finite even if a
            # future edit accidentally lets an unexpected exception escape the network helper.
            result["version"] = None
        finally:
            result["done"] = True

    thread = threading.Thread(target=fetch_update, daemon=True, name="animeexpedition-update-check")
    try:
        thread.start()
    except RuntimeError:
        # The update check is explicitly best-effort - a thread the OS refuses to start (resource
        # exhaustion) must not take down startup over something this unimportant.
        return

    def show_notice_when_ready() -> None:
        if not result["done"]:
            QTimer.singleShot(100, show_notice_when_ready)
            return
        version = result["version"]
        if isinstance(version, str):
            window._show_message(f"Update available: v{version} (current v{current_version}).")

    QTimer.singleShot(100, show_notice_when_ready)


def main(argv: list[str] | None = None) -> int:
    """Run the GUI, managing installation and the engine only for default launches.

    An explicit ``--dir`` is a controlled development/test mode: it uses that directory's
    existing bridge files without self-installing, launching an engine, or owning its shutdown.
    """
    args = _build_arg_parser().parse_args(argv)
    data_dir = _resolve_data_dir(args.dir)

    frozen = is_frozen()
    # Falsy, not just "is None": _resolve_data_dir() above already treats an empty --dir the same
    # as an omitted one (falls back to the default directory) - this must agree, or "--dir """
    # would manage the engine against the DEFAULT directory while claiming to be in --dir mode.
    manage_engine = not args.dir
    engine_install_dir: Path | None = None
    if frozen and manage_engine:
        engine_install_dir = install_dir()
        relaunch_args = sys.argv[1:] if argv is None else argv
        if ensure_self_installed(relaunch_args):
            return 0
        ensure_start_menu_shortcut(engine_install_dir)

    if sys.platform == "win32":
        try:
            import ctypes

            # Must run before the taskbar button is created, or Windows keeps grouping this
            # process under python.exe's own icon/name (only visible during an unfrozen dev
            # run - a frozen gui.exe already gets an implicit AppUserModelID from its own exe
            # path, but setting one explicitly costs nothing and is the documented fix either
            # way).
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    try:
        icon_file = app_icon_path(Path(__file__))
        if icon_file is not None:
            app.setWindowIcon(QIcon(str(icon_file)))
    except Exception:
        # Best-effort: a missing/unreadable icon must not block the GUI from starting.
        pass
    stylesheet_path = Path(__file__).with_name("style.qss")
    app.setStyleSheet(stylesheet_path.read_text(encoding="utf-8"))

    # Only a default launch manages the engine.  ``--dir`` deliberately leaves the supplied
    # directory alone so standalone fixtures and release smoke tests remain process-local.
    # PyInstaller's onefile extraction directory is temporary, so refresh the stable engine
    # payload on every managed frozen launch, even if an earlier engine is already running.
    prepared_engine_argv = (
        find_engine_executable(engine_install_dir) if manage_engine and frozen else None
    )
    spawned_engine = None
    if manage_engine and not is_engine_running():
        engine_argv = prepared_engine_argv or find_engine_executable(engine_install_dir)
        if engine_argv is None:
            print("Warning: AutoHotkey engine executable was not found; starting GUI offline.", file=sys.stderr)
        else:
            spawned_engine = launch_engine_hidden(engine_argv, data_dir)
            if spawned_engine is None:
                print("Warning: AutoHotkey engine could not be started; starting GUI offline.", file=sys.stderr)
            elif not wait_for_engine_ready(data_dir, pump=app.processEvents):
                print("Warning: AutoHotkey engine did not become ready within 15 seconds.", file=sys.stderr)

    window = MainWindow(data_dir)
    if spawned_engine is not None:
        app.aboutToQuit.connect(lambda: stop_engine(spawned_engine))
    window.show()
    _schedule_update_notice(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
