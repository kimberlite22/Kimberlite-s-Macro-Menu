from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app import update_check


def test_parse_update_version_ignores_comments_and_invalid_versions() -> None:
    metadata = "\n# release metadata\nhash=abc\nversion=1.2.3\n"
    assert update_check.parse_update_version(metadata) == "1.2.3"
    assert update_check.parse_update_version("version=1.2\n") is None


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


def test_check_for_update_returns_only_strictly_newer_version(monkeypatch) -> None:
    response = MagicMock()
    response.read.return_value = b"# comment\nversion=1.3.0\n"
    urlopen = MagicMock()
    urlopen.return_value.__enter__.return_value = response
    monkeypatch.setattr(update_check.urllib.request, "urlopen", urlopen)

    assert update_check.check_for_update("1.2.9") == "1.3.0"
    urlopen.assert_called_with(update_check.UPDATE_METADATA_URL, timeout=5)


def test_check_for_update_ignores_network_errors_and_non_new_versions(monkeypatch) -> None:
    monkeypatch.setattr(update_check.urllib.request, "urlopen", MagicMock(side_effect=OSError("offline")))
    assert update_check.check_for_update("1.2.3") is None
