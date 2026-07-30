"""Best-effort per-user installation for the frozen GUI executable."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from app.launcher_paths import APP_NAME, GUI_EXE_NAME, install_dir, is_frozen


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)


def installed_gui_path(directory: Path | None = None) -> Path:
    """Return the canonical path of the installed GUI executable."""
    return (directory or install_dir()) / GUI_EXE_NAME


def _same_windows_path(left: Path, right: Path) -> bool:
    """Compare paths with Windows' case-insensitive path semantics."""
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _powershell_string(value: str | Path) -> str:
    """Quote a value as a PowerShell single-quoted string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def ensure_start_menu_shortcut(directory: Path | None = None) -> bool:
    """Create or refresh the per-user Start Menu shortcut without surfacing errors."""
    if not is_frozen():
        return False

    try:
        target_directory = directory or install_dir()
        start_menu_directory = (
            Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
        start_menu_directory.mkdir(parents=True, exist_ok=True)
        link_path = start_menu_directory / f"{APP_NAME}.lnk"
        target_path = installed_gui_path(target_directory)
        script = "; ".join(
            (
                "$shell = New-Object -ComObject WScript.Shell",
                f"$shortcut = $shell.CreateShortcut({_powershell_string(link_path)})",
                f"$shortcut.TargetPath = {_powershell_string(target_path)}",
                f"$shortcut.WorkingDirectory = {_powershell_string(target_directory)}",
                "$shortcut.Save()",
            )
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        return completed.returncode == 0
    except Exception as error:
        print(f"Warning: could not create the Start Menu shortcut: {error}", file=sys.stderr)
        return False


def ensure_self_installed(relaunch_args: Sequence[str] | None = None) -> bool:
    """Install and relaunch the frozen GUI, returning true only after relaunching.

    A failure intentionally leaves the caller running from its original location.  That is
    preferable to turning a transient locked-file or permission problem into an unusable app.
    """
    if not is_frozen():
        return False

    try:
        directory = install_dir()
        target_path = installed_gui_path(directory)
        source_path = Path(sys.executable)
        if _same_windows_path(source_path, target_path):
            return False

        staged_path = target_path.with_name(f"{target_path.name}.installing")
        directory.mkdir(parents=True, exist_ok=True)
        try:
            staged_path.unlink(missing_ok=True)
        except OSError:
            # copy2 below will report a useful error if a stale staging path is still locked.
            pass
        shutil.copy2(source_path, staged_path)
        os.replace(staged_path, target_path)
    except Exception as error:
        print(
            f"Warning: could not install {APP_NAME}; continuing from the current location: {error}",
            file=sys.stderr,
        )
        return False

    ensure_start_menu_shortcut(directory)
    command = [str(target_path), *(sys.argv[1:] if relaunch_args is None else relaunch_args)]
    try:
        subprocess.Popen(command, creationflags=DETACHED_PROCESS)
    except Exception as error:
        print(
            f"Warning: {APP_NAME} was installed but could not be relaunched; continuing here: {error}",
            file=sys.stderr,
        )
        return False
    return True
