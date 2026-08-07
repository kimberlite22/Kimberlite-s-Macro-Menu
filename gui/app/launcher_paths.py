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
# The marker content a normal production release carries; anything else in the file is a build
# label shown in the window title (see read_build_marker).
RELEASE_MARKER_RELEASE = "release"
# What a marker that exists but cannot be read is labeled. Deliberately NOT the production label:
# only an intact, readable "release" may present itself as production (see read_build_marker).
UNKNOWN_BUILD_LABEL = "unknown build"
BUILD_MARKER_LABEL_MAX_LENGTH = 40


def is_frozen() -> bool:
    """Return whether this process is running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def read_build_marker(entry_file: Path) -> str | None:
    """Return the build marker's own label, or None when the bundle carries no marker.

    Only the release workflows write RELEASE_MARKER_NAME next to the bundled VERSION file (see
    each workflow's "Build GUI EXE" step). A local/manual PyInstaller build (gui/BUILD.md,
    tools/build-local-exe.ps1) never performs that step, so the marker is simply absent there -
    meaningful only when the caller already knows the process is frozen at all.

    The marker's CONTENT distinguishes the two CI build kinds, because a bare "does the file
    exist" check cannot: .github/workflows/release.yml writes RELEASE_MARKER_RELEASE for a normal
    production release, while .github/workflows/release-experimental.yml writes the experimental
    tag it is publishing (for example "experimental v0.4.16-dev3"), so a test build says on its
    own title bar which build it is instead of passing itself off as a production one. Only the
    first line is used and it is length-capped, since this value goes straight into a window title
    and the file is written by a workflow, not validated anywhere else. A marker that exists but
    is blank or unreadable becomes UNKNOWN_BUILD_LABEL rather than the production label: the
    production label is the one that renders no suffix at all, so degrading into it would let a
    corrupted experimental bundle pass itself off as production - exactly the ambiguity this
    marker exists to remove. Unreadable provenance has to stay visible.
    """
    marker = entry_file.with_name(RELEASE_MARKER_NAME)
    try:
        # utf-8-sig, not utf-8: the workflows write this file with PowerShell's -Encoding utf8,
        # which is BOM-less under pwsh but BOM-prefixed under Windows PowerShell 5.1. Decoding a
        # BOM as content would turn the production label into "﻿release", which no longer
        # compares equal to RELEASE_MARKER_RELEASE, and every production build would suddenly
        # carry a suffix in its title bar. utf-8-sig reads a BOM-less file identically.
        content = marker.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return UNKNOWN_BUILD_LABEL if marker.is_file() else None
    label = content.splitlines()[0].strip() if content.strip() else ""
    return label[:BUILD_MARKER_LABEL_MAX_LENGTH] or UNKNOWN_BUILD_LABEL


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
