"""File-based request/response protocol shared with tower_defense_macro_gui.ahk.

Mirrors macro/ocr_server.ps1's protocol exactly (see CLAUDE.md, "Phase 1 implementation
plan"). All files live in one directory (the macro's DataDir):

    ocr_ready.txt  - written once the engine is up; the macro waits for this before
                     sending requests.
    ocr_req.txt    - request written by the macro:
                     "<token>|<x>|<y>|<w>|<h>|<pad_x>|<pad_y>|<color>"
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
from typing import Callable


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
    pad_x: int = 0
    pad_y: int = 0
    color: str = ""


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

    Both the legacy five-field form and the current eight-field form are accepted. Malformed
    request lines (wrong field count, non-integer fields) are silently discarded, matching
    ocr_server.ps1's `continue`-on-bad-input behavior.
    """
    req_path = data_dir / REQUEST_FILENAME
    if not req_path.exists():
        return None

    try:
        line = req_path.read_text(encoding="utf-8")
    except OSError:
        return None
    except UnicodeError:
        # Undecodable bytes are a malformed request like any other, not a reason to take the server
        # down. UnicodeDecodeError is a ValueError, NOT an OSError, so it used to sail past the
        # handler above, out of serve_forever(), and end the process - costing every later detection
        # its persistent server (and a 6s timeout each) over one bad write. Fall through to the
        # consume-and-discard path below, which is what the docstring already promises.
        line = ""

    try:
        req_path.unlink()
    except OSError:
        pass

    if not line or not line.strip():
        return None

    parts = line.strip().split("|")
    if len(parts) not in (5, 8):
        return None

    try:
        pad_x = int(parts[5]) if len(parts) == 8 else 0
        pad_y = int(parts[6]) if len(parts) == 8 else 0
        color = parts[7].strip().lower() if len(parts) == 8 else ""
        if color not in {"black", "white"}:
            color = ""
        return ScanRequest(
            token=parts[0],
            x=int(parts[1]),
            y=int(parts[2]),
            width=int(parts[3]),
            height=int(parts[4]),
            pad_x=pad_x,
            pad_y=pad_y,
            color=color,
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


def serve_forever(
    data_dir: Path,
    handle_scan: Callable[[int, int, int, int, int, int, str], str],
) -> None:
    """Poll for requests and dispatch them to
    `handle_scan(x, y, width, height, pad_x, pad_y, color) -> str`.

    Runs until ocr_stop.txt appears. `handle_scan` is expected to already contain any
    per-scan exception handling and return "" on failure, matching ocr_server.ps1.
    """
    try:
        while not stop_requested(data_dir):
            request = read_next_request(data_dir)
            if request is None:
                time.sleep(_POLL_INTERVAL_SECONDS)
                continue
            text = handle_scan(
                request.x,
                request.y,
                request.width,
                request.height,
                request.pad_x,
                request.pad_y,
                request.color,
            )
            try:
                write_response(data_dir, request.token, text or "")
            except OSError:
                # Losing one response costs one scan: the macro is already waiting on its own
                # request timeout and escalates from there. Letting the error out of this loop
                # would instead end the server, so a single transient sharing violation or a
                # momentarily full disk would downgrade every future detection to the one-shot
                # path for the rest of the session.
                pass
    finally:
        cleanup(data_dir)
