"""Small, failure-tolerant release metadata check for the GUI launcher."""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path


UPDATE_METADATA_URL = (
    "https://github.com/kimberlite22/Anime-Expedition-Macro-Menu/releases/latest/download/update.ini"
)
_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_update_version(metadata: str) -> str | None:
    """Return the `version` value from simple comment-tolerant update metadata."""
    for raw_line in metadata.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "version":
            version = value.strip()
            return version if _VERSION_PATTERN.fullmatch(version) else None
    return None


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


def check_for_update(current_version: str, *, url: str = UPDATE_METADATA_URL) -> str | None:
    """Return a newer release version, or None for no update and every network failure."""
    current = parse_version(current_version)
    if current is None:
        return None
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            metadata = response.read().decode("utf-8")
    except Exception:
        return None
    available_version = parse_update_version(metadata)
    available = parse_version(available_version) if available_version is not None else None
    return available_version if available is not None and available > current else None
