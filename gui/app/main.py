"""Launch the PySide6 presentation process for the local macro bridge."""

from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path
from typing import NoReturn

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main_window import MainWindow
from app.engine_process import (
    find_engine_executable,
    get_engine_pid,
    is_engine_running,
    launch_engine_hidden,
    stop_engine,
    stop_engine_by_pid,
    wait_for_local_command_slot,
    wait_for_engine_ready,
)
from app.launcher_paths import APP_NAME, APP_USER_MODEL_ID, app_icon_path, default_data_dir, install_dir, is_frozen
from app.self_install import cleanup_legacy_installation, ensure_self_installed, ensure_start_menu_shortcut
from app.update_check import (
    AvailableUpdate,
    UpdateError,
    check_available_update,
    download_update,
    install_update,
    read_current_version,
    self_update_target,
    staged_update_path,
)
from app.widgets import CheckmarkProxyStyle


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="animeexpedition-gui",
        description="PySide6 GUI for Kimberlite's Macro Menu.",
    )
    parser.add_argument(
        "--dir",
        help="Directory containing config.ini and the local bridge files.",
    )
    return parser


def _resolve_data_dir(directory: str | None) -> Path:
    """Resolve an explicit data directory or the engine-compatible default."""
    return Path(directory).resolve() if directory else default_data_dir().resolve()


_MEGABYTE = 1024 * 1024


def _megabytes(value: int) -> str:
    """Format a byte count the way the update progress dialog reports it."""
    return f"{value / _MEGABYTE:.1f} MB"


def _schedule_update_check(window: MainWindow, data_dir: Path, *, allow_install: bool) -> None:
    """Fetch update metadata off the Qt thread, then offer or announce a newer release.

    Only a real installed launch may install: a development or ``--dir`` run has no release
    executable of its own to replace, so it keeps the status-bar notice it always had.
    """
    current_version = read_current_version(Path(__file__))
    if current_version is None:
        return

    target = self_update_target() if allow_install else None
    result: dict[str, object] = {"done": False, "update": None}

    def fetch_update() -> None:
        try:
            result["update"] = check_available_update(current_version)
        except Exception:
            # The checker is best-effort.  Keep the Qt-side polling callback finite even if a
            # future edit accidentally lets an unexpected exception escape the network helper.
            result["update"] = None
        finally:
            result["done"] = True

    thread = threading.Thread(target=fetch_update, daemon=True, name="animeexpedition-update-check")
    try:
        thread.start()
    except RuntimeError:
        # The update check is explicitly best-effort - a thread the OS refuses to start (resource
        # exhaustion) must not take down startup over something this unimportant.
        return

    def act_when_ready() -> None:
        if not result["done"]:
            QTimer.singleShot(100, act_when_ready)
            return
        update = result["update"]
        if not isinstance(update, AvailableUpdate):
            return
        notice = f"Update available: v{update.version} (current v{current_version})."
        if target is None:
            window._show_message(notice)
            return
        answer = QMessageBox.question(
            window,
            f"{APP_NAME} Update",
            f"A new version is available: v{update.version} (you have v{current_version}).\n\n"
            "Do you want to update now?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            # Declining is not an error, and the next start asks again - leave the notice behind so
            # the user can still see that a newer version exists.
            window._show_message(notice)
            return
        _install_update(window, update, target, data_dir)

    QTimer.singleShot(100, act_when_ready)


def _install_update(window: MainWindow, update: AvailableUpdate, target: Path, data_dir: Path) -> None:
    """Download the release into the data directory, then hand the swap to the update helper."""
    destination = staged_update_path(data_dir)
    progress = QProgressDialog("Downloading update...", "", 0, 100, window)
    progress.setWindowTitle(f"{APP_NAME} Update")
    # Deliberately non-cancellable, like the AHK updater this replaces: the download is the only
    # long step, and a half-applied update is worse than waiting for it.
    progress.setCancelButton(None)
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    progress.show()

    state: dict[str, object] = {"done": False, "error": None, "received": 0, "total": None}

    def report(received: int, total: int | None) -> None:
        # Runs on the worker thread and only assigns plain values; the Qt side reads them from its
        # own timer below, so no widget is ever touched off the GUI thread.
        state["received"] = received
        state["total"] = total

    def download() -> None:
        try:
            download_update(update, destination, progress=report)
        except UpdateError as error:
            state["error"] = str(error)
        except Exception as error:
            state["error"] = f"The update could not be downloaded ({error})."
        finally:
            state["done"] = True

    thread = threading.Thread(target=download, daemon=True, name="animeexpedition-update-download")
    try:
        thread.start()
    except RuntimeError as error:
        progress.close()
        _report_update_failure(window, f"The update could not be started ({error}).")
        return

    def finish_when_ready() -> None:
        received = state["received"]
        total = state["total"]
        if isinstance(received, int) and isinstance(total, int):
            progress.setLabelText(f"Downloading update... {_megabytes(received)} / {_megabytes(total)}")
            progress.setValue(min(100, received * 100 // total))
        elif isinstance(received, int) and received > 0:
            progress.setLabelText(f"Downloading update... {_megabytes(received)}")
        if not state["done"]:
            QTimer.singleShot(100, finish_when_ready)
            return

        error = state["error"]
        if isinstance(error, str):
            progress.close()
            _report_update_failure(window, error)
            return

        progress.setLabelText("Installing update...")
        progress.setValue(100)
        try:
            install_update(destination, target, sha256=update.sha256)
        except UpdateError as install_error:
            progress.close()
            _report_update_failure(window, str(install_error))
            return
        progress.close()
        # The helper waits for this process to exit before replacing the executable, so quitting is
        # part of installing, not just cleanup.  aboutToQuit also stops the engine this launch owns,
        # which is what frees the files the relaunched build extracts again.
        QApplication.quit()

    QTimer.singleShot(100, finish_when_ready)


def _report_update_failure(window: MainWindow, message: str) -> None:
    """Tell the user an update they asked for did not happen, and keep the app running."""
    QMessageBox.warning(
        window,
        f"{APP_NAME} Update",
        f"The automatic update could not be completed.\n\n{message}",
    )
    window._show_message("The automatic update could not be completed.")


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
        cleanup_legacy_installation(engine_install_dir)

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
    app.setStyle(CheckmarkProxyStyle("Fusion"))
    app.setStyleSheet(stylesheet_path.read_text(encoding="utf-8"))

    # Only a default launch manages the engine.  ``--dir`` deliberately leaves the supplied
    # directory alone so standalone fixtures and release smoke tests remain process-local.
    # PyInstaller's onefile extraction directory is temporary, so refresh the stable engine
    # payload on every managed frozen launch, even if an earlier engine is already running.
    prepared_engine_argv = (
        find_engine_executable(engine_install_dir) if manage_engine and frozen else None
    )
    spawned_engine = None
    attached_engine_pid = None
    engine_running = manage_engine and is_engine_running()
    if manage_engine and engine_running:
        # This launch did not spawn the engine (a crash, a forced close, or a second GUI instance
        # left it running), so there is no Popen handle to take shutdown ownership of it later.
        # The PID captured here is that ownership's only handle.
        attached_engine_pid = get_engine_pid()
    if manage_engine and not engine_running:
        engine_argv = prepared_engine_argv or find_engine_executable(engine_install_dir)
        if engine_argv is None:
            print("Warning: AutoHotkey engine executable was not found; starting GUI offline.", file=sys.stderr)
        else:
            spawned_engine = launch_engine_hidden(engine_argv, data_dir)
            if spawned_engine is None:
                print("Warning: AutoHotkey engine could not be started; starting GUI offline.", file=sys.stderr)

    # A live engine process is not necessarily ready to accept bridge commands yet. In
    # particular, engine_ready.txt persists for a reused engine, while its one-slot command file
    # can still hold a mutation left by an offline/crashed GUI. Do not remove or resend that
    # command here: its outcome is unknown until the engine consumes and acknowledges it.
    auto_refresh_game_processes = True
    if manage_engine and (engine_running or spawned_engine is not None):
        if not wait_for_engine_ready(data_dir, pump=app.processEvents):
            print("Warning: AutoHotkey engine did not become ready within 15 seconds.", file=sys.stderr)
        if not wait_for_local_command_slot(data_dir, pump=app.processEvents):
            print(
                "Warning: AutoHotkey engine still has a pending command; "
                "skipping the automatic game-process refresh.",
                file=sys.stderr,
            )
            auto_refresh_game_processes = False

    # Keep MainWindow's default constructor behavior for normal, offline, and explicit --dir
    # launches. The one exceptional path must suppress only its deferred automatic LIST request.
    window = (
        MainWindow(data_dir)
        if auto_refresh_game_processes
        else MainWindow(data_dir, auto_refresh_game_processes=False)
    )
    if spawned_engine is not None or attached_engine_pid is not None:
        def stop_owned_engine() -> None:
            """Stop the process this GUI launch owns when Qt begins shutting down."""
            if spawned_engine is not None:
                stop_engine(spawned_engine)
            elif attached_engine_pid is not None:
                stop_engine_by_pid(attached_engine_pid)

        app.aboutToQuit.connect(stop_owned_engine)
    window.show()
    # Only a frozen launch that also manages its own installation may replace its executable; an
    # explicit --dir run stays a pure development/test mode here too.
    _schedule_update_check(window, data_dir, allow_install=frozen and manage_engine)
    return app.exec()


def run(argv: list[str] | None = None) -> None:
    """Run the GUI, then end this process with its Qt event-loop return code."""
    _terminate_process(main(argv))


def _terminate_process(code: int) -> NoReturn:
    """Flush standard streams when present, then finish the GUI process immediately."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.flush()
        except Exception:
            pass

    # This is the third fix in the same shutdown chain, and it closes the last step of it. The two
    # earlier fixes each repaired a step further up the sequence (closing every top-level widget,
    # then calling quit() outright instead of trusting quitOnLastWindowClosed), and the process
    # still outlived its window, because ending Qt's event loop is not the same as ending the
    # process. By the time main() returns, that loop is over AND aboutToQuit has already stopped
    # the engine, so everything this application actually wanted to happen has happened. What is
    # left is CPython's interpreter finalization plus PyInstaller's own teardown, and neither is
    # under this application's control.
    #
    # The specific hazard there is the best-effort update check: a daemon thread parked in
    # urllib.request.urlopen(). Being a daemon does not, by itself, delay shutdown - CPython joins
    # only non-daemon threads. What it does mean is that the thread is never joined and never
    # cancelled, so finalization terminates it at whatever arbitrary point it had reached, and a
    # thread cut short inside a socket or SSL call is a well-known way for a Python process to
    # linger instead of exiting. Nothing here joins, cancels, or even observes it, and adding that
    # bookkeeping would only make the last step of shutdown depend on more machinery rather than
    # less. Closing the main window is an unconditional "end this process", so state that directly.
    #
    # Exiting outright is safe because this process holds no unflushed state: config.ini belongs to
    # the AHK engine, and everything the bridge client writes goes through an atomic .tmp plus
    # os.replace and is closed before it returns. The one thread that does write a file of its own,
    # the update download in _install_update, cannot be in flight here: its progress dialog is
    # application-modal, so the main window cannot be closed while that download runs.
    os._exit(code)


if __name__ == "__main__":
    run()
