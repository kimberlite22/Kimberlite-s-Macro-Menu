"""File-based request/response protocol shared with tower_defense_macro_gui.ahk.

Mirrors macro/ocr_server.ps1's protocol exactly (see CLAUDE.md, "Phase 1 implementation
plan"). All files live in one directory (the macro's DataDir):

    ocr_ready.txt  - written once the engine is up; the macro waits for this before
                     sending requests.
    ocr_req.txt    - request written by the macro: "<token>|<x>|<y>|<w>|<h>"
                     (this server deletes it after reading).
    ocr_resp.txt   - response written by this server: "<token>|<recognized text>".
    ocr_stop.txt   - the macro writes this to ask the server to exit cleanly.

Both the request and the response are published atomically: written to a ".tmp" file
first, then renamed into place, so a reader never observes a half-written file.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


READY_FILENAME = "ocr_ready.txt"
REQUEST_FILENAME = "ocr_req.txt"
RESPONSE_FILENAME = "ocr_resp.txt"
STOP_FILENAME = "ocr_stop.txt"

_POLL_INTERVAL_SECONDS = 0.015


@dataclass
class ScanRequest:
    token: str
    x: int
    y: int
    width: int
    height: int


def _atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` without a reader ever seeing a partial file."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def signal_ready(data_dir: Path) -> None:
    """Write ocr_ready.txt once the OCR engine has finished initializing."""
    (data_dir / READY_FILENAME).write_text("1", encoding="utf-8")


def stop_requested(data_dir: Path) -> bool:
    return (data_dir / STOP_FILENAME).exists()


def read_next_request(data_dir: Path) -> ScanRequest | None:
    """Return the next pending request, consuming (deleting) it, or None if idle.

    Malformed request lines (wrong field count, non-integer fields) are silently
    discarded, matching ocr_server.ps1's `continue`-on-bad-input behavior.
    """
    req_path = data_dir / REQUEST_FILENAME
    if not req_path.exists():
        return None

    try:
        line = req_path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        req_path.unlink()
    except OSError:
        pass

    if not line or not line.strip():
        return None

    parts = line.strip().split("|")
    if len(parts) < 5:
        return None

    try:
        return ScanRequest(
            token=parts[0],
            x=int(parts[1]),
            y=int(parts[2]),
            width=int(parts[3]),
            height=int(parts[4]),
        )
    except ValueError:
        return None


def write_response(data_dir: Path, token: str, text: str) -> None:
    _atomic_write(data_dir / RESPONSE_FILENAME, f"{token}|{text}")


def cleanup(data_dir: Path) -> None:
    """Remove protocol files left behind on exit (mirrors ocr_server.ps1's tail)."""
    for filename in (READY_FILENAME, STOP_FILENAME):
        try:
            (data_dir / filename).unlink()
        except OSError:
            pass


def serve_forever(data_dir: Path, handle_scan) -> None:
    """Poll for requests and dispatch them to `handle_scan(x, y, width, height) -> str`.

    Runs until ocr_stop.txt appears. `handle_scan` is expected to already contain any
    per-scan exception handling and return "" on failure, matching ocr_server.ps1.
    """
    try:
        while not stop_requested(data_dir):
            request = read_next_request(data_dir)
            if request is None:
                time.sleep(_POLL_INTERVAL_SECONDS)
                continue
            text = handle_scan(request.x, request.y, request.width, request.height)
            write_response(data_dir, request.token, text or "")
    finally:
        cleanup(data_dir)
