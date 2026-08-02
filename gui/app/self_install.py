"""Best-effort per-user installation for the frozen GUI executable."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from app.launcher_paths import (
    APP_NAME,
    GUI_EXE_NAME,
    LEGACY_APP_NAME,
    install_dir,
    is_frozen,
    legacy_install_dir,
    start_menu_dir,
)


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
        start_menu_directory = start_menu_dir()
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


def cleanup_legacy_installation(directory: Path | None = None) -> None:
    """Best-effort retirement of a per-user install left behind by the project's previous name.

    Mirrors CleanupLegacyInstallation in tower_defense_macro_gui.ahk. ensure_self_installed()
    always installs into whatever install_dir() (i.e. APP_NAME) currently resolves to - including
    for an existing user who is self-updating in place, since the very next launch of the updated
    build no longer matches its own new install_dir() and re-installs itself there - so an old
    install is never orphaned in the sense of losing data. What is left behind without this
    function is cosmetic but permanent: the old Programs-folder copy (gui.exe plus the extracted
    engine/OCR helper) and the old Start Menu shortcut, since nothing else ever removes either one.
    Safe to call on every launch: both checks are no-ops once the legacy paths are already gone.
    Never raises; a failure here must never block startup, exactly like ensure_start_menu_shortcut().
    """
    if not is_frozen():
        return
    try:
        current_directory = directory or install_dir()
        legacy_directory = legacy_install_dir()
        if not _same_windows_path(legacy_directory, current_directory) and legacy_directory.is_dir():
            shutil.rmtree(legacy_directory, ignore_errors=True)

        legacy_shortcut = start_menu_dir() / f"{LEGACY_APP_NAME}.lnk"
        current_shortcut = start_menu_dir() / f"{APP_NAME}.lnk"
        if not _same_windows_path(legacy_shortcut, current_shortcut) and legacy_shortcut.is_file():
            legacy_shortcut.unlink(missing_ok=True)
    except Exception as error:
        print(
            f"Warning: could not remove the previous {LEGACY_APP_NAME} installation: {error}",
            file=sys.stderr,
        )


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
