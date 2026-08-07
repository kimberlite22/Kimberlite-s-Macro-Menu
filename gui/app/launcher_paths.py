"""Shared Windows paths for the GUI launcher and its headless engine."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Kimberlite's Macro Menu"
# The project's previous name, kept only so cleanup_legacy_installation() (self_install.py) can
# find and retire a per-user install/shortcut left behind by this rename, mirroring LegacyAppName
# in macro/tower_defense_macro_gui.ahk. Update this to the current APP_NAME (moving it one hop
# forward) the next time the project is renamed again, the same way this value itself replaced the
# even-older "Anime Expedition Macro" (no "Kimberlite's" prefix) name from before that.
LEGACY_APP_NAME = "Kimberlite's Anime Expedition Macro"
# Not user-visible (Windows uses it only for taskbar/pinning identity, e.g. grouping and jump
# lists), so it does not need to match APP_NAME and must stay stable across releases.
APP_USER_MODEL_ID = "Kimberlite.AnimeExpeditionMacro.GUI"
GUI_EXE_NAME = "gui.exe"
# The RDP alternate-shell value becomes CreateProcess's application name, not a command line, so
# this distinct executable name is how main.py identifies the background-session mode. Keep it
# short for the same deep-profile-path MAX_PATH constraint as the installed engine executable.
SESSION_SHELL_EXE_NAME = "AEMSessionShell.exe"
# Deliberately short: the extracted/running copy lives directly under install_dir(), itself under
# the user's own (length-uncontrollable) profile - see the comment in engine_process.find_engine_
# executable() for the MAX_PATH failure this is avoiding. The release-uploaded exe is still branded
# "Kimberlites-Macro-Menu.exe" (see .github/workflows/release.yml); only this internal,
# post-extraction filename is short. Must stay distinctive (not a generic name like "engine.exe")
# so find_engine_processes()'s tasklist filter can't false-positive on an unrelated process.
ENGINE_EXE_NAME = "AEMEngine.exe"
RELEASE_MARKER_NAME = "RELEASE_BUILD"


def is_frozen() -> bool:
    """Return whether this process is running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def is_release_build(entry_file: Path) -> bool:
    """Return whether entry_file's bundle carries the official-release marker.

    Only .github/workflows/release.yml writes RELEASE_MARKER_NAME next to the bundled VERSION
    file (see release.yml's "Build GUI EXE" step). A local/manual PyInstaller build (gui/BUILD.md,
    tools/build-local-exe.ps1) never performs that step, so the marker is simply absent there -
    meaningful only when the caller already knows the process is frozen at all.
    """
    return entry_file.with_name(RELEASE_MARKER_NAME).is_file()


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


def session_shell_exe_path(directory: Path | None = None) -> Path:
    """Return the installed executable path used exclusively by the RDP session shell."""
    return (directory or install_dir()) / SESSION_SHELL_EXE_NAME


def legacy_install_dir() -> Path:
    """Return the per-user installation directory used before the LEGACY_APP_NAME rename.

    Exists only for self_install.cleanup_legacy_installation(): mirrors install_dir() exactly
    except for the app name segment, including the AEM_TEST_ROOT override, so a test run never
    touches a real legacy installation either.
    """
    test_root = _test_root()
    if test_root is not None:
        return Path(test_root) / "Programs" / LEGACY_APP_NAME
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / LEGACY_APP_NAME


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


def app_icon_path(entry_file: Path) -> Path | None:
    """Return the bundled or dev-tree path to the Windows application icon, if present.

    Mirrors update_check.read_current_version's two-candidate resolution: the release build
    bundles assets/app.ico at the frozen bundle root (see gui/BUILD.md on why a frozen entry
    script's own __file__ resolves there), so that candidate is checked first; a source/dev run
    instead reads the real asset straight out of the repository's top-level assets/ folder.
    """
    candidates = (entry_file.with_name("app.ico"), entry_file.resolve().parents[2] / "assets" / "app.ico")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
