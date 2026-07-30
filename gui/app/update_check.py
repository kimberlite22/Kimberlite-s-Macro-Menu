"""Release metadata check and self-update for the GUI launcher."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.launcher_paths import APP_NAME
from app.self_install import installed_gui_path


RELEASE_BASE_URL = "https://github.com/kimberlite22/Anime-Expedition-Macro-Menu/releases/latest/download/"
# The single executable asset every release publishes, and the name the update helper installs it
# under.  See ".github/workflows/release.yml" ("Finalize the single installer exe").
RELEASE_EXE_NAME = "Kimberlites-Anime-Expedition-Macro.exe"
UPDATE_METADATA_URL = RELEASE_BASE_URL + "update.ini"
UPDATE_EXE_URL = RELEASE_BASE_URL + RELEASE_EXE_NAME
DOWNLOAD_CHUNK_SIZE = 256 * 1024
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

# Waits for the GUI to exit, replaces its executable, relaunches it, then deletes itself.  A running
# executable cannot overwrite its own file on Windows, so the replace has to outlive this process -
# this mirrors StartSelfUpdate in macro/tower_defense_macro_gui.ahk, which is unreachable in the
# shipped app because the AHK engine now runs headless behind the Qt window.
#
# Two things this does that the AHK original did not, because a broken installed EXE leaves the user
# with no working application at all: it re-verifies the checksum right before the copy (the file has
# been sitting on disk since the download, and nothing else guards the window in between), and it
# keeps the previous EXE so a copy that dies half-written can be rolled back instead of leaving a
# truncated executable behind.  The backup is taken exactly once, BEFORE the first attempt: taking it
# inside the retry loop would let a truncated CurrentExe from a failed attempt overwrite the last
# good copy.  It is also only deleted once the new EXE is installed or the old one is back, so a
# rollback that itself fails still leaves the user something to restore by hand.  The common failure
# is a GUI that has not exited yet: Windows keeps a running EXE readable but not writable, so the
# backup succeeds while every copy attempt fails and the installed EXE is never touched at all -
# comparing it against the backup recognizes that case instead of reporting a scary, wrong "could
# not be restored" for a file that was never damaged.
_UPDATE_HELPER_SCRIPT = """param(
  [int]$ParentPid,
  [string]$CurrentExe,
  [string]$NewExe,
  [string]$Sha256,
  [string]$AppName
)
$ErrorActionPreference = 'Stop'
$failure = 'The update could not replace the current EXE. Move it to a writable folder and try again.'
$backup = $CurrentExe + '.previous'
$verified = $false
$backedUp = $false
$installed = $false
$previousInPlace = $false
try { Wait-Process -Id $ParentPid -Timeout 30 -ErrorAction SilentlyContinue } catch {}
try {
  $actual = (Get-FileHash -LiteralPath $NewExe -Algorithm SHA256).Hash
  $verified = ($actual.ToLowerInvariant() -ceq $Sha256.ToLowerInvariant())
} catch {}
if (-not $verified) {
  $failure = 'The downloaded update was discarded because its checksum did not match.'
}
if ($verified) {
  try {
    Copy-Item -LiteralPath $CurrentExe -Destination $backup -Force
    $backedUp = $true
  } catch {
    $failure = 'The update was not installed because the current EXE could not be backed up first.'
  }
}
if ($backedUp) {
  for ($attempt = 0; $attempt -lt 50; $attempt++) {
    try {
      [IO.File]::Copy($NewExe, $CurrentExe, $true)
      $installed = $true
      break
    } catch { Start-Sleep -Milliseconds 200 }
  }
}
if ($backedUp -and -not $installed) {
  try {
    $currentHash = (Get-FileHash -LiteralPath $CurrentExe -Algorithm SHA256).Hash
    $backupHash = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash
    $previousInPlace = ($currentHash -ceq $backupHash)
  } catch {}
  if (-not $previousInPlace) {
    try {
      [IO.File]::Copy($backup, $CurrentExe, $true)
      $previousInPlace = $true
    } catch {}
  }
}
Remove-Item -LiteralPath $NewExe -Force -ErrorAction SilentlyContinue
if ($installed -or $previousInPlace) {
  Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
}
if ($installed) {
  Start-Process -FilePath $CurrentExe
} else {
  if ($backedUp -and -not $previousInPlace) {
    $failure = 'The update failed and the previous EXE could not be restored. A copy of it is kept at: ' + $backup
  }
  Add-Type -AssemblyName PresentationFramework
  [System.Windows.MessageBox]::Show($failure, ($AppName + ' Update')) | Out-Null
}
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""


class UpdateError(RuntimeError):
    """A self-update step failed after the user asked for the update to be installed."""


@dataclass(frozen=True)
class AvailableUpdate:
    """A newer release together with everything needed to install it."""

    version: str
    sha256: str
    download_url: str = UPDATE_EXE_URL


def parse_update_metadata(metadata: str) -> dict[str, str]:
    """Parse comment-tolerant `key=value` update metadata into a lowercase-keyed map."""
    values: dict[str, str] = {}
    for raw_line in metadata.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # First occurrence wins, so a trailing duplicate key cannot silently change the meaning of
        # metadata whose first lines already validated.
        values.setdefault(key.strip().lower(), value.strip())
    return values


def parse_update_version(metadata: str) -> str | None:
    """Return the `version` value from simple comment-tolerant update metadata."""
    version = parse_update_metadata(metadata).get("version")
    if version is None:
        return None
    return version if _VERSION_PATTERN.fullmatch(version) else None


def parse_update_sha256(metadata: str) -> str | None:
    """Return the lowercase `sha256` value from update metadata, if it is well formed."""
    digest = parse_update_metadata(metadata).get("sha256")
    if digest is None:
        return None
    return digest.lower() if _SHA256_PATTERN.fullmatch(digest) else None


def parse_version(version: str) -> tuple[int, int, int] | None:
    """Turn a plain three-part semantic version into a comparable integer tuple."""
    match = _VERSION_PATTERN.fullmatch(version.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def read_current_version(entry_file: Path) -> str | None:
    """Read bundled VERSION first, then the repository-root development VERSION file."""
    candidates = (entry_file.with_name("VERSION"), entry_file.resolve().parents[2] / "VERSION")
    for candidate in candidates:
        try:
            version = candidate.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            continue
        if parse_version(version) is not None:
            return version
    return None


def fetch_update_metadata(url: str = UPDATE_METADATA_URL) -> str | None:
    """Download the release metadata, returning None for every network failure."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.read().decode("utf-8")
    except Exception:
        return None


def check_available_update(
    current_version: str,
    *,
    url: str = UPDATE_METADATA_URL,
    download_url: str = UPDATE_EXE_URL,
) -> AvailableUpdate | None:
    """Return a newer, installable release, or None when there is nothing safe to install.

    A missing or malformed checksum counts as "nothing to install" on purpose: an unverifiable
    download must never be offered, no matter how new the advertised version is.  Every network and
    parsing failure ends here as None as well, so a release page that is offline, rate-limited, or
    has not published its first release yet can never block or delay normal startup.
    """
    current = parse_version(current_version)
    if current is None:
        return None
    metadata = fetch_update_metadata(url)
    if metadata is None:
        return None
    available_version = parse_update_version(metadata)
    digest = parse_update_sha256(metadata)
    if available_version is None or digest is None:
        return None
    available = parse_version(available_version)
    if available is None or available <= current:
        return None
    return AvailableUpdate(version=available_version, sha256=digest, download_url=download_url)


def _discard(path: Path) -> None:
    """Remove a partial or rejected file without masking the failure that led here."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _content_length(response: object) -> int | None:
    """Return the response's Content-Length, or None when the server sends no usable one."""
    try:
        raw = response.headers.get("Content-Length")  # type: ignore[attr-defined]
    except Exception:
        return None
    try:
        total = int(raw)
    except (TypeError, ValueError):
        return None
    return total if total > 0 else None


def download_update(
    update: AvailableUpdate,
    destination: Path,
    *,
    progress: Callable[[int, int | None], None] | None = None,
    timeout: float = 30.0,
) -> Path:
    """Download the release executable and keep it only if it matches the published checksum.

    Hashed while writing rather than in a second pass, so an executable that does not match the
    metadata never exists on disk in a completed state.
    """
    digest = hashlib.sha256()
    received = 0
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(update.download_url, timeout=timeout) as response:
            total = _content_length(response)
            with open(destination, "wb") as handle:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if progress is not None:
                        progress(received, total)
    except Exception as error:
        _discard(destination)
        raise UpdateError(f"The update could not be downloaded ({error}).") from error

    if digest.hexdigest() != update.sha256:
        _discard(destination)
        raise UpdateError("Checksum mismatch. The update was discarded.")
    return destination


def install_update(new_exe: Path, target_exe: Path, *, sha256: str) -> None:
    """Hand the replace-and-relaunch to a detached helper and return.

    The caller must quit right afterwards so the helper's bounded wait for this process can finish.
    The helper retries the copy for ten seconds and reports its own failure if the file stays
    locked, so a GUI that refuses to exit cannot leave a half-installed application behind.
    """
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".ps1",
            prefix="anime-expedition-updater-",
            delete=False,
        ) as handle:
            handle.write(_UPDATE_HELPER_SCRIPT)
            script_path = Path(handle.name)
    except OSError as error:
        # Nothing will consume the download once the helper is out of the picture, and the staging
        # name is unique per launch, so leaving it behind would only accumulate dead megabytes.
        _discard(new_exe)
        raise UpdateError(f"The update helper could not be written ({error}).") from error

    # Every dynamic value travels through argv, never through the script text, so an install path
    # or application name can never inject PowerShell code into the helper.
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(script_path),
        "-ParentPid",
        str(os.getpid()),
        "-CurrentExe",
        str(target_exe),
        "-NewExe",
        str(new_exe),
        "-Sha256",
        sha256,
        "-AppName",
        APP_NAME,
    ]
    try:
        subprocess.Popen(command, creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)
    except OSError as error:
        _discard(script_path)
        _discard(new_exe)
        raise UpdateError(f"The update helper could not be started ({error}).") from error


def staged_update_path(data_dir: Path) -> Path:
    """Return a download path unique to this process, inside the given data directory.

    Never a fixed name: two launchers can be open at once and would otherwise write the same file,
    so one instance could verify its download while the other was still truncating and rewriting
    those very bytes - and the helper would then copy that half-written file over the installed EXE.
    """
    return data_dir / f"{RELEASE_EXE_NAME}.{os.getpid()}.{uuid.uuid4().hex}.update"


def self_update_target() -> Path | None:
    """Return the executable a self-update may replace, or None when there is none.

    Two conditions, both required.  Only a frozen build has an executable of its own at all (a
    development run's is the Python interpreter, which must never be overwritten with a release
    build), and it must be the canonical installed copy.  A frozen launch that is NOT the installed
    copy is a launch whose self-install failed or was bypassed - replacing that file would update a
    downloaded or portable EXE somewhere else on disk while leaving the installed application stale.
    """
    if not getattr(sys, "frozen", False):
        return None
    try:
        running = Path(sys.executable).resolve()
        installed = installed_gui_path().resolve()
    except (KeyError, OSError):
        return None
    if os.path.normcase(str(running)) != os.path.normcase(str(installed)):
        return None
    return running
