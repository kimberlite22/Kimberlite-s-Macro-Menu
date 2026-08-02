"""Tests for best-effort benchmark spool sampling."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from ocr_helper.shadow import SPOOL_DIRNAME, ShadowSpooler, shadow_enabled


def _sample() -> Image.Image:
    return Image.new("RGB", (3, 2), color="white")


def _double(image: Image.Image) -> Image.Image:
    """Stand-in for engine.maybe_upscale, without importing the WinRT engine into these tests."""
    return image.resize((image.width * 2, image.height * 2))


def test_spool_writes_atomic_pair_with_sidecar_and_throttles(tmp_path: Path) -> None:
    spooler = ShadowSpooler(tmp_path, min_interval_seconds=60)
    spooler.spool(
        _sample(),
        region={"x": 1, "y": 2, "width": 3, "height": 4},
        production_text="Map\nName",
        production_ms=12.5,
    )
    spooler.spool(_sample(), region={}, production_text="ignored", production_ms=0)

    spool_dir = tmp_path / SPOOL_DIRNAME
    json_paths = list(spool_dir.glob("*.json"))
    png_paths = list(spool_dir.glob("*.png"))
    assert len(json_paths) == len(png_paths) == 1
    assert not list(spool_dir.glob("*.tmp"))
    sidecar = json.loads(json_paths[0].read_text(encoding="utf-8"))
    assert sidecar["seq"] == 1
    assert sidecar["region"] == {"x": 1, "y": 2, "width": 3, "height": 4}
    assert sidecar["production_engine"] == "winsdk"
    assert sidecar["production_text"] == "Map\nName"
    assert sidecar["production_ms"] == 12.5
    assert sidecar["skipped_throttled"] == 0
    assert sidecar["skipped_backlog"] == 0
    assert spooler.skipped_throttled == 1


def test_spool_applies_backpressure(tmp_path: Path) -> None:
    spooler = ShadowSpooler(tmp_path, max_pending=1, min_interval_seconds=0)
    spooler.spool(_sample(), region={}, production_text="first", production_ms=1)
    spooler.spool(_sample(), region={}, production_text="second", production_ms=1)

    assert len(list((tmp_path / SPOOL_DIRNAME).glob("*.png"))) == 1
    assert spooler.skipped_backlog == 1


def test_spool_writes_the_prepared_image_not_the_raw_capture(tmp_path: Path) -> None:
    """The upscale the production engine applies has to reach the file the alternates read."""
    spooler = ShadowSpooler(tmp_path, min_interval_seconds=0, prepare_image=_double)
    spooler.spool(_sample(), region={}, production_text="", production_ms=0)

    png_path = next((tmp_path / SPOOL_DIRNAME).glob("*.png"))
    with Image.open(png_path) as written:
        assert written.size == (6, 4)


def test_a_failed_png_write_leaves_no_orphan_sidecar(tmp_path: Path) -> None:
    """A sample that cannot be encoded must leave nothing behind at all.

    The pending cap counts PNGs, so a stranded sidecar would be invisible to it. Repeated
    encode failures with no benchmark runner started could then fill the disk with files
    nothing counted and nothing collected.
    """

    def explode(image: Image.Image) -> Image.Image:
        raise OSError("encoder unavailable")

    spooler = ShadowSpooler(tmp_path, min_interval_seconds=0, prepare_image=explode)
    spooler.spool(_sample(), region={}, production_text="", production_ms=0)

    assert list((tmp_path / SPOOL_DIRNAME).iterdir()) == []


def test_spool_failure_never_raises(tmp_path: Path, monkeypatch) -> None:
    spooler = ShadowSpooler(tmp_path, min_interval_seconds=0)

    def fail_mkdir(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    spooler.spool(_sample(), region={}, production_text="", production_ms=0)


def test_shadow_enabled_parses_only_recognized_values() -> None:
    assert shadow_enabled(False, {"AEM_OCR_SHADOW": "yes"}) is True
    assert shadow_enabled(True, {"AEM_OCR_SHADOW": "off"}) is False
    assert shadow_enabled(True, {"AEM_OCR_SHADOW": "maybe"}) is True
    assert shadow_enabled(False, {}) is False
