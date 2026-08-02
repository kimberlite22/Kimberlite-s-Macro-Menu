"""Tests for the benchmark spool drain using fake, dependency-free engines."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from PIL import Image

from ocr_helper.benchmark_runner import BenchmarkRunner
from ocr_helper.shadow import BENCHMARK_LOG_FILENAME, SPOOL_DIRNAME


class FakeEngine:
    def __init__(self, name: str, text: str = "", raises: bool = False) -> None:
        self.name = name
        self.text = text
        self.raises = raises
        self.last_error: str | None = None

    def recognize_image(self, image: Image.Image) -> str:
        if self.raises:
            raise RuntimeError("engine failed")
        return self.text


def _write_pair(data_dir: Path, stem: str = "00000001-sample") -> tuple[Path, Path]:
    spool_dir = data_dir / SPOOL_DIRNAME
    spool_dir.mkdir()
    sidecar = {
        "seq": 1,
        "timestamp": "2026-08-02T00:00:00+00:00",
        "region": {"x": 1, "y": 2, "width": 3, "height": 4},
        "production_engine": "winsdk",
        "production_text": "production",
        "production_ms": 4.0,
        "skipped_throttled": 2,
        "skipped_backlog": 3,
    }
    json_path = spool_dir / f"{stem}.json"
    png_path = spool_dir / f"{stem}.png"
    json_path.write_text(json.dumps(sidecar), encoding="utf-8")
    Image.new("RGB", (2, 2), color="white").save(png_path)
    return json_path, png_path


def test_drain_writes_one_jsonl_record_and_removes_pair(tmp_path: Path) -> None:
    json_path, png_path = _write_pair(tmp_path)
    runner = BenchmarkRunner(
        tmp_path,
        engines=[FakeEngine("pytesseract", "one"), FakeEngine("easyocr", "two"), FakeEngine("paddleocr", "three")],
    )

    assert runner.drain_once() == 1
    assert not json_path.exists()
    assert not png_path.exists()
    lines = (tmp_path / BENCHMARK_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record["results"]) == {"production", "pytesseract", "easyocr", "paddleocr"}
    assert record["results"]["production"]["text"] == "production"
    assert record["results"]["easyocr"]["text"] == "two"


def test_engine_exception_is_logged_without_stopping_drain(tmp_path: Path) -> None:
    _write_pair(tmp_path)
    runner = BenchmarkRunner(tmp_path, engines=[FakeEngine("broken", raises=True)])

    assert runner.drain_once() == 1
    record = json.loads((tmp_path / BENCHMARK_LOG_FILENAME).read_text(encoding="utf-8"))
    assert record["results"]["broken"]["text"] == ""
    assert "engine failed" in record["results"]["broken"]["error"]


def test_undeletable_pair_is_never_logged_twice(tmp_path: Path, monkeypatch) -> None:
    """A spool pair the runner cannot delete must still be logged exactly once.

    This is the failure the claim-before-OCR rename exists for: with the delete happening
    only at the end, a sidecar that refuses to go away meant the same sample was re-OCR'd
    and re-appended on every single poll for the rest of the session.
    """
    _write_pair(tmp_path)
    runner = BenchmarkRunner(tmp_path, engines=[FakeEngine("stub", "text")])
    monkeypatch.setattr(Path, "unlink", lambda self, **kwargs: (_ for _ in ()).throw(OSError("locked")))

    assert runner.drain_once() == 1
    assert runner.drain_once() == 0
    lines = (tmp_path / BENCHMARK_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_claimed_png_stops_counting_against_the_producer_backlog(tmp_path: Path) -> None:
    """The claim rename has to free the pending slot the spooler counts, not just hide the file."""
    _write_pair(tmp_path)
    spool_dir = tmp_path / SPOOL_DIRNAME
    runner = BenchmarkRunner(tmp_path, engines=[FakeEngine("stub", "text")])

    claimed = runner._claim(spool_dir / "00000001-sample.png")
    assert claimed is not None and claimed.exists()
    assert list(spool_dir.glob("*.png")) == []


def test_orphan_json_is_removed_after_grace_period(tmp_path: Path) -> None:
    spool_dir = tmp_path / SPOOL_DIRNAME
    spool_dir.mkdir()
    orphan = spool_dir / "orphan.json"
    orphan.write_text("{}", encoding="utf-8")
    old = time.time() - 10
    os.utime(orphan, (old, old))
    runner = BenchmarkRunner(tmp_path, engines=[], orphan_grace_seconds=1)

    assert runner.drain_once() == 0
    assert not orphan.exists()
