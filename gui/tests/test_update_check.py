from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import update_check


def _metadata_response(payload: bytes) -> MagicMock:
    response = MagicMock()
    response.read.return_value = payload
    urlopen = MagicMock()
    urlopen.return_value.__enter__.return_value = response
    return urlopen


class _FakeDownloadResponse:
    """Minimal stand-in for the urlopen response object download_update consumes."""

    def __init__(self, payload: bytes, *, content_length: str | None) -> None:
        self._payload = payload
        self._offset = 0
        self.headers = {} if content_length is None else {"Content-Length": content_length}

    def __enter__(self) -> "_FakeDownloadResponse":
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def read(self, size: int) -> bytes:
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_parse_update_version_ignores_comments_and_invalid_versions() -> None:
    metadata = "\n# release metadata\nhash=abc\nversion=1.2.3\n"
    assert update_check.parse_update_version(metadata) == "1.2.3"
    assert update_check.parse_update_version("version=1.2\n") is None


def test_parse_update_sha256_normalizes_case_and_rejects_malformed_digests() -> None:
    digest = "A" * 64
    assert update_check.parse_update_sha256(f"sha256={digest}\n") == "a" * 64
    assert update_check.parse_update_sha256("sha256=abc\n") is None
    assert update_check.parse_update_sha256("version=1.2.3\n") is None


def test_parse_update_metadata_keeps_the_first_value_for_a_duplicated_key() -> None:
    values = update_check.parse_update_metadata("Version=1.2.3\nversion=9.9.9\n")
    assert values == {"version": "1.2.3"}


def test_read_current_version_prefers_bundle_adjacent_file(tmp_path: Path) -> None:
    entry_file = tmp_path / "bundle" / "main.py"
    entry_file.parent.mkdir()
    entry_file.write_text("", encoding="utf-8")
    entry_file.with_name("VERSION").write_text("1.2.3\n", encoding="utf-8")

    assert update_check.read_current_version(entry_file) == "1.2.3"


def test_read_current_version_falls_back_to_repository_root(tmp_path: Path) -> None:
    entry_file = tmp_path / "repository" / "gui" / "app" / "main.py"
    entry_file.parent.mkdir(parents=True)
    entry_file.write_text("", encoding="utf-8")
    (tmp_path / "repository" / "VERSION").write_text("4.5.6\n", encoding="utf-8")

    assert update_check.read_current_version(entry_file) == "4.5.6"


def test_check_available_update_returns_only_strictly_newer_verifiable_releases(monkeypatch) -> None:
    digest = "b" * 64
    urlopen = _metadata_response(f"# comment\nversion=1.3.0\nsha256={digest}\n".encode("utf-8"))
    monkeypatch.setattr(update_check.urllib.request, "urlopen", urlopen)

    available = update_check.check_available_update("1.2.9")
    assert available == update_check.AvailableUpdate(
        version="1.3.0", sha256=digest, download_url=update_check.UPDATE_EXE_URL
    )
    urlopen.assert_called_with(update_check.UPDATE_METADATA_URL, timeout=5)
    assert update_check.check_available_update("1.3.0") is None
    assert update_check.check_available_update("2.0.0") is None


def test_check_available_update_rejects_metadata_without_a_usable_checksum(monkeypatch) -> None:
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        _metadata_response(b"version=1.3.0\n"),
    )
    assert update_check.check_available_update("1.2.9") is None

    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        _metadata_response(b"version=1.3.0\nsha256=not-a-digest\n"),
    )
    assert update_check.check_available_update("1.2.9") is None


def test_check_available_update_ignores_network_errors(monkeypatch) -> None:
    monkeypatch.setattr(update_check.urllib.request, "urlopen", MagicMock(side_effect=OSError("offline")))
    assert update_check.check_available_update("1.2.3") is None


def test_download_update_writes_the_payload_and_reports_progress(monkeypatch, tmp_path: Path) -> None:
    payload = b"x" * (update_check.DOWNLOAD_CHUNK_SIZE + 17)
    update = update_check.AvailableUpdate(
        version="1.3.0",
        sha256=hashlib.sha256(payload).hexdigest(),
        download_url="https://example.invalid/release.exe",
    )
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        lambda url, timeout: _FakeDownloadResponse(payload, content_length=str(len(payload))),
    )
    seen: list[tuple[int, int | None]] = []
    destination = tmp_path / "nested" / "release.exe.update"

    result = update_check.download_update(
        update, destination, progress=lambda received, total: seen.append((received, total))
    )

    assert result == destination
    assert destination.read_bytes() == payload
    assert seen[0] == (update_check.DOWNLOAD_CHUNK_SIZE, len(payload))
    assert seen[-1] == (len(payload), len(payload))


def test_download_update_reports_progress_without_a_content_length(monkeypatch, tmp_path: Path) -> None:
    payload = b"y" * 32
    update = update_check.AvailableUpdate(
        version="1.3.0",
        sha256=hashlib.sha256(payload).hexdigest(),
        download_url="https://example.invalid/release.exe",
    )
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        lambda url, timeout: _FakeDownloadResponse(payload, content_length=None),
    )
    seen: list[tuple[int, int | None]] = []

    update_check.download_update(
        update,
        tmp_path / "release.exe.update",
        progress=lambda received, total: seen.append((received, total)),
    )

    assert seen == [(len(payload), None)]


def test_download_update_discards_a_payload_that_fails_the_checksum(monkeypatch, tmp_path: Path) -> None:
    update = update_check.AvailableUpdate(
        version="1.3.0", sha256="c" * 64, download_url="https://example.invalid/release.exe"
    )
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        lambda url, timeout: _FakeDownloadResponse(b"tampered", content_length="8"),
    )
    destination = tmp_path / "release.exe.update"

    with pytest.raises(update_check.UpdateError, match="Checksum mismatch"):
        update_check.download_update(update, destination)
    assert not destination.exists()


def test_download_update_discards_a_partial_payload_after_a_network_failure(monkeypatch, tmp_path: Path) -> None:
    update = update_check.AvailableUpdate(
        version="1.3.0", sha256="d" * 64, download_url="https://example.invalid/release.exe"
    )
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        MagicMock(side_effect=OSError("connection reset")),
    )
    destination = tmp_path / "release.exe.update"
    destination.write_bytes(b"stale")

    with pytest.raises(update_check.UpdateError, match="could not be downloaded"):
        update_check.download_update(update, destination)
    assert not destination.exists()


def test_install_update_starts_a_detached_helper_with_every_value_in_argv(monkeypatch, tmp_path: Path) -> None:
    popen = MagicMock()
    monkeypatch.setattr(update_check.subprocess, "Popen", popen)
    new_exe = tmp_path / "release.exe.update"
    new_exe.write_bytes(b"payload")
    target_exe = tmp_path / "Programs" / "gui.exe"

    update_check.install_update(new_exe, target_exe, sha256="e" * 64)

    command = popen.call_args.args[0]
    script_path = Path(command[command.index("-File") + 1])
    try:
        assert script_path.read_text(encoding="utf-8") == update_check._UPDATE_HELPER_SCRIPT
        assert command[command.index("-CurrentExe") + 1] == str(target_exe)
        assert command[command.index("-NewExe") + 1] == str(new_exe)
        assert command[command.index("-Sha256") + 1] == "e" * 64
        assert command[command.index("-AppName") + 1] == update_check.APP_NAME
        assert command[command.index("-ParentPid") + 1].isdigit()
        assert popen.call_args.kwargs["creationflags"] & update_check.DETACHED_PROCESS
    finally:
        script_path.unlink(missing_ok=True)
    # Handed to the helper, which deletes it once it has installed or rejected it.
    assert new_exe.exists()


def test_install_update_reports_and_cleans_up_a_helper_that_cannot_start(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(update_check.subprocess, "Popen", MagicMock(side_effect=OSError("no shell")))
    new_exe = tmp_path / "new.exe"
    new_exe.write_bytes(b"payload")

    with pytest.raises(update_check.UpdateError, match="could not be started"):
        update_check.install_update(new_exe, tmp_path / "current.exe", sha256="f" * 64)
    assert not new_exe.exists()


def test_staged_update_path_is_unique_per_process_and_lands_in_the_data_directory(tmp_path: Path) -> None:
    first = update_check.staged_update_path(tmp_path)
    second = update_check.staged_update_path(tmp_path)

    assert first.parent == tmp_path
    assert first.name.startswith(update_check.RELEASE_EXE_NAME)
    assert first.suffix == ".update"
    assert first != second


def test_self_update_target_requires_a_frozen_build_running_from_the_install_location(
    monkeypatch, tmp_path: Path
) -> None:
    installed = tmp_path / "Programs" / "gui.exe"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"exe")
    monkeypatch.setattr(update_check, "installed_gui_path", lambda: installed)

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(installed))
    assert update_check.self_update_target() is None

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert update_check.self_update_target() == installed.resolve()

    # A frozen launch that never reached the install location (a failed or bypassed self-install)
    # must not overwrite whatever EXE it happens to be running from.
    portable = tmp_path / "Downloads" / "gui.exe"
    portable.parent.mkdir(parents=True)
    portable.write_bytes(b"exe")
    monkeypatch.setattr(sys, "executable", str(portable))
    assert update_check.self_update_target() is None
