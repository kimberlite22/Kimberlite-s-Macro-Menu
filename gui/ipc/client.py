"""Synchronous client for the local AHK file bridge."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .protocol import CaptureResult, LocalStatus, dumps_payload, parse_ack_line


COMMAND_FILENAME = "local_cmd.txt"
ACK_FILENAME = "local_ack.txt"
STATUS_FILENAME = "local_status.json"
CAPTURE_RESULT_FILENAME = "local_capture_result.txt"


class IpcTimeoutError(TimeoutError):
    """Raised when the AHK bridge did not acknowledge a command in time.

    A timeout does NOT mean the command was retracted: local_cmd.txt is a single
    slot with no cancellation mechanism, so AHK may still consume and execute it
    (and publish an ack nobody is waiting for) after this exception is raised.
    Callers should treat a timeout as "unknown outcome," not "definitely failed,"
    and should disable the triggering control until either an ack or a fresh
    status snapshot confirms the effect, rather than blindly resending.
    """


class IpcBusyError(RuntimeError):
    """Raised when a previous command is still unconsumed in local_cmd.txt.

    Only one command can be in flight at a time (single-slot file protocol,
    mirroring macro/remote_bridge.ahk) - sending a second one before AHK
    consumes the first would silently overwrite or race with it.
    """


@dataclass(frozen=True)
class CommandAck:
    token: str
    ok: bool
    message: str
    data: dict[str, Any]


def atomic_write(path: Path, text: str) -> None:
    """Publish UTF-8 text by replacing the target after writing its sibling .tmp file."""
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


class LocalIpcClient:
    """Blocking local-bridge client intended for a future timer or worker thread."""

    def __init__(self, data_dir: str | Path, poll_interval: float = 0.075) -> None:
        self.data_dir = Path(data_dir)
        self.poll_interval = poll_interval

    @property
    def command_path(self) -> Path:
        return self.data_dir / COMMAND_FILENAME

    @property
    def ack_path(self) -> Path:
        return self.data_dir / ACK_FILENAME

    @property
    def status_path(self) -> Path:
        return self.data_dir / STATUS_FILENAME

    @property
    def capture_result_path(self) -> Path:
        return self.data_dir / CAPTURE_RESULT_FILENAME

    def send_command(
        self, verb: str, payload: Mapping[str, Any], timeout: float = 5.0,
    ) -> CommandAck:
        """Send one command and wait for its matching acknowledgement.

        Stale acknowledgements stay untouched because they may belong to another
        client.  They are ignored until this command's token appears.

        Raises IpcBusyError instead of overwriting a still-unconsumed prior
        command (see that class's docstring) - callers should keep the
        triggering UI control disabled until this returns rather than firing
        commands back-to-back.
        """
        if self.command_path.exists() or self.command_path.with_name(
            self.command_path.name + ".tmp"
        ).exists():
            raise IpcBusyError(
                f"a previous command is still pending in {self.command_path} - "
                "wait for it to be consumed before sending another"
            )
        token = uuid.uuid4().hex
        json_payload = dumps_payload(payload)  # raises TypeError for non-JSON data
        atomic_write(self.command_path, f"{token}|{verb}|{json_payload}\n")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ack = self._read_matching_ack(token)
            if ack is not None:
                return ack
            time.sleep(self.poll_interval)
        raise IpcTimeoutError(f"timed out after {timeout:g}s waiting for {verb} acknowledgement")

    def read_status(self) -> LocalStatus | None:
        """Return the latest status, or None when it is absent or transiently unreadable."""
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return LocalStatus.from_json_dict(data)

    def read_capture_result(self, consume: bool = False) -> CaptureResult | None:
        """Read the latest capture result, optionally consuming it after a valid read."""
        try:
            data = json.loads(self.capture_result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        result = CaptureResult.from_json_dict(data)
        if consume:
            try:
                self.capture_result_path.unlink()
            except OSError:
                pass
        return result

    def _read_matching_ack(self, expected_token: str) -> CommandAck | None:
        try:
            token, data = parse_ack_line(self.ack_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return None
        if token != expected_token:
            return None
        return CommandAck(
            token=token,
            ok=bool(data.get("ok", False)),
            message=str(data.get("message", "")),
            data=data,
        )


class ConfigChangeTracker:
    """Detect config changes from either the bridge counter or config.ini mtime."""

    def __init__(self) -> None:
        self._config_version: int | None = None
        self._mtime_ns: int | None = None

    def changed(self, status: LocalStatus | None, config_path: str | Path) -> bool:
        try:
            mtime_ns = Path(config_path).stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        version = status.config_version if status is not None else None
        is_changed = version != self._config_version or mtime_ns != self._mtime_ns
        self._config_version = version
        self._mtime_ns = mtime_ns
        return is_changed
