"""Shared Windows paths for the GUI launcher and its headless engine."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Kimberlite's Anime Expedition Macro"
GUI_EXE_NAME = "gui.exe"
ENGINE_EXE_NAME = "Kimberlites-Anime-Expedition-Macro.exe"


def is_frozen() -> bool:
    """Return whether this process is running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def source_repo_root() -> Path:
    """Return the repository root when this module is run from source."""
    return Path(__file__).resolve().parents[2]


def _test_root() -> str | None:
    """Return AEM_TEST_ROOT if set and non-blank, mirroring the AHK engine's own check.

    The compiled AHK engine (tower_defense_macro_gui.ahk) redirects InstallDir/DataDir under this
    env var when set, so its own installer/update integration tests never touch a real user's
    LOCALAPPDATA. The GUI must honor the same override, or a test run that sets it would still spawn
    an engine using (and poll status/config from) the real LOCALAPPDATA paths instead of the isolated
    test root the engine itself switched to.
    """
    value = os.environ.get("AEM_TEST_ROOT", "").strip()
    return value or None


def install_dir() -> Path:
    """Return the per-user GUI installation directory used by the AHK engine."""
    test_root = _test_root()
    if test_root is not None:
        return Path(test_root) / "Programs" / APP_NAME
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME


def data_dir() -> Path:
    """Return the mutable data directory used by the compiled AHK engine."""
    test_root = _test_root()
    if test_root is not None:
        return Path(test_root) / "AppData" / APP_NAME
    return Path(os.environ["LOCALAPPDATA"]) / APP_NAME


def start_menu_dir() -> Path:
    """Return the per-user Start Menu Programs folder the AHK engine also targets.

    Also honors AEM_TEST_ROOT (InstallTestRoot "\\Start Menu\\Programs" in the AHK source) - without
    this, a test run would still create/refresh a shortcut in the REAL Windows Start Menu even while
    every other path was safely redirected under the test root.
    """
    test_root = _test_root()
    if test_root is not None:
        return Path(test_root) / "Start Menu" / "Programs"
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def default_data_dir() -> Path:
    """Return the engine-compatible default data directory for this launch mode."""
    if is_frozen():
        return data_dir()
    return source_repo_root() / "macro"
