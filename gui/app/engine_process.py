"""Discovery and lifecycle helpers for the hidden AutoHotkey engine process."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.launcher_paths import ENGINE_EXE_NAME, is_frozen, source_repo_root


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
READY_FILE_NAME = "engine_ready.txt"


def find_engine_executable(install_directory: Path | None) -> list[str] | None:
    """Return the command needed to run the bundled or development engine.

    A frozen onefile bundle extracts its engine to a temporary directory, so copy that
    payload to a stable location next to the installed GUI on every launch.
    """
    if is_frozen():
        try:
            bundle_directory = Path(getattr(sys, "_MEIPASS"))
            bundled_engine = bundle_directory / "engine" / ENGINE_EXE_NAME
            if not bundled_engine.is_file() or install_directory is None:
                return None
            stable_engine = install_directory / "engine" / ENGINE_EXE_NAME
            stable_engine.parent.mkdir(parents=True, exist_ok=True)
            staging_engine = stable_engine.with_suffix(f"{stable_engine.suffix}.staging")
            try:
                shutil.copy2(bundled_engine, staging_engine)
                os.replace(staging_engine, stable_engine)
            except Exception:
                try:
                    staging_engine.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            return [str(stable_engine)]
        except (AttributeError, OSError, TypeError):
            return None

    macro_directory = source_repo_root() / "macro"
    autohotkey_executable = shutil.which("AutoHotkey64.exe")
    source_script = macro_directory / "tower_defense_macro_gui.ahk"
    if autohotkey_executable and source_script.is_file():
        return [autohotkey_executable, str(source_script), "--headless"]
    return None


def is_engine_running() -> bool:
    """Check tasklist output for the exact engine image name, independent of locale."""
    try:
        completed = subprocess.run(
            [
                "tasklist.exe",
                "/FI",
                f"IMAGENAME eq {ENGINE_EXE_NAME}",
                "/FO",
                "CSV",
                "/NH",
            ],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError:
        return False
    return ENGINE_EXE_NAME in (completed.stdout or "")


def launch_engine_hidden(argv: Sequence[str], data_directory: Path) -> subprocess.Popen[Any] | None:
    """Start the engine without a visible console and return its process handle."""
    command = [str(argument) for argument in argv]
    if not command:
        return None
    if Path(command[0]).name.casefold() == ENGINE_EXE_NAME.casefold() and "--headless" not in command:
        command.append("--headless")

    # The engine deletes this itself while it initializes.  Removing it before process creation
    # also closes the tiny race where a stale marker from a crashed prior engine is observed first.
    try:
        (data_directory / READY_FILE_NAME).unlink(missing_ok=True)
    except OSError:
        pass

    try:
        return subprocess.Popen(command, creationflags=CREATE_NO_WINDOW)
    except OSError:
        return None


def wait_for_engine_ready(
    data_directory: Path,
    timeout_seconds: float = 15.0,
    *,
    pump: Callable[[], object] | None = None,
) -> bool:
    """Poll the engine readiness marker while optionally keeping Qt responsive."""
    marker_path = data_directory / READY_FILE_NAME
    deadline = time.monotonic() + timeout_seconds
    while True:
        if marker_path.exists():
            return True
        if time.monotonic() >= deadline:
            return False
        if pump is not None:
            pump()
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))


def stop_engine(process: subprocess.Popen[Any] | None) -> None:
    """Stop only an engine process that this GUI launch owns, gracefully when possible."""
    if process is None or process.poll() is not None:
        return

    try:
        subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid)],
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError:
        pass
    else:
        try:
            process.wait(timeout=5)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass

    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
    except OSError:
        pass
