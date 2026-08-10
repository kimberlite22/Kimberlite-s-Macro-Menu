"""Compares the Python OCR engine's output against a frozen PowerShell/WinRT baseline.

`tests/fixtures/*.png` are synthetic "game UI text" samples (banners, map names, a large
paragraph). `tests/fixtures/baseline_manifest.json` records what the OLD implementation
(macro/ocr_region.ps1, before this migration deleted it, using the identical
Windows.Media.Ocr decode + recognize path) produced for each fixture. This is the actual
"no accuracy regression" proof for Phase 1 of the Python migration (see CLAUDE.md): same
engine, same result -- down to reproducing the old engine's misreads (e.g. "1x" -> "lx" on
tiny text), which is the point.

The baseline was originally recorded with the 2x upscale heuristic both implementations then
applied. That heuristic has since been deleted (tasklist/open/fixes/ocr-padding-escalation.md:
the user reported detection was reliable before it existed and unreliable after, so it was the
suspect rather than a safety net). These assertions were deliberately NOT re-frozen afterwards,
and they did not need to be: five of the six fixtures were small enough to have been upscaled,
and every one of them still recognizes byte-for-byte identically without it. The manifest
therefore still means what it always meant, and it now also documents that the upscale was not
what produced these results.

Skipped automatically if no WinRT OCR engine is available on the machine running the tests
(e.g. missing language pack), since that is an environment limitation, not a code defect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from ocr_helper.engine import OcrEngine, pad_image

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BASELINE_MANIFEST = FIXTURES_DIR / "baseline_manifest.json"


def _load_baseline() -> dict[str, str]:
    with open(BASELINE_MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def _engine_or_skip() -> OcrEngine:
    engine = OcrEngine()
    if engine._winrt_engine is None:
        pytest.skip("No Windows OCR engine available on this machine (missing language pack?)")
    return engine


@pytest.fixture(scope="module")
def engine() -> OcrEngine:
    return _engine_or_skip()


@pytest.fixture(scope="module")
def baseline() -> dict[str, str]:
    return _load_baseline()


def _fixture_names() -> list[str]:
    return sorted(p.name for p in FIXTURES_DIR.glob("*.png"))


@pytest.mark.parametrize("fixture_name", _fixture_names())
def test_matches_powershell_winrt_baseline(engine: OcrEngine, baseline: dict[str, str], fixture_name: str) -> None:
    image = Image.open(FIXTURES_DIR / fixture_name)
    recognized = engine.recognize_image(image)
    expected = baseline[fixture_name]
    assert recognized == expected, (
        f"{fixture_name}: Python engine recognized {recognized!r}, "
        f"but the PowerShell/WinRT baseline recognized {expected!r}"
    )


def test_all_fixtures_have_a_baseline_entry(baseline: dict[str, str]) -> None:
    fixture_names = set(_fixture_names())
    assert fixture_names <= baseline.keys()
    assert fixture_names, "expected at least one fixture image in tests/fixtures/"


def test_empty_region_returns_empty_string_without_capturing(engine: OcrEngine) -> None:
    assert engine.recognize_region(0, 0, 0, 100) == ""
    assert engine.recognize_region(0, 0, 100, 0) == ""


def test_save_region_image_writes_raw_png(tmp_path: Path) -> None:
    engine = OcrEngine.__new__(OcrEngine)
    engine.capture_region = lambda x, y, width, height: Image.new("RGBA", (width, height), (1, 2, 3, 4))

    output = tmp_path / "nested" / "sample.png"

    assert engine.save_region_image(10, 20, 7, 5, output) is True
    with Image.open(output) as image:
        assert image.size == (7, 5)
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0)) == (1, 2, 3, 4)
    assert not output.with_suffix(output.suffix + ".tmp").exists()


@pytest.mark.parametrize("width,height", [(0, 5), (-1, 5), (5, 0), (5, -1)])
def test_save_region_image_rejects_empty_regions(tmp_path: Path, width: int, height: int) -> None:
    engine = OcrEngine.__new__(OcrEngine)
    output = tmp_path / "sample.png"

    assert engine.save_region_image(0, 0, width, height, output) is False
    assert not output.exists()


def test_save_region_image_handles_capture_failure_without_partial_file(tmp_path: Path) -> None:
    engine = OcrEngine.__new__(OcrEngine)

    def fail_capture(*args):
        raise RuntimeError("capture failed")

    engine.capture_region = fail_capture
    output = tmp_path / "sample.png"

    assert engine.save_region_image(0, 0, 5, 5, output) is False
    assert not output.exists()
    assert not output.with_suffix(output.suffix + ".tmp").exists()


def test_pad_image_adds_the_border_on_all_four_sides() -> None:
    image = Image.new("RGB", (100, 40), color="red")
    padded = pad_image(image, 10, 4, "black")

    assert padded.size == (100 + 2 * 10, 40 + 2 * 4)
    assert padded.getpixel((0, 0)) == (0, 0, 0)
    assert padded.getpixel((padded.width - 1, padded.height - 1)) == (0, 0, 0)
    # The original pixels survive, shifted by exactly the border.
    assert padded.getpixel((10, 4)) == (255, 0, 0)


def test_pad_image_supports_a_white_border() -> None:
    padded = pad_image(Image.new("RGB", (20, 20), color="red"), 5, 5, "white")

    assert padded.size == (30, 30)
    assert padded.getpixel((0, 0)) == (255, 255, 255)


def test_pad_image_returns_the_image_unchanged_without_padding_or_color() -> None:
    image = Image.new("RGB", (20, 20), color="red")

    assert pad_image(image, 0, 0, "black") is image
    assert pad_image(image, 5, 5, "") is image
    # A negative value is clamped rather than passed to ImageOps.expand, which would crop.
    assert pad_image(image, -5, -5, "black") is image


def test_pad_image_pads_a_single_axis() -> None:
    # A very short region rounds its own pad_y down to 0 while pad_x is still meaningful;
    # requiring both would drop the border in exactly the tightly cropped case this is for.
    padded = pad_image(Image.new("RGB", (100, 6), color="red"), 10, 0, "black")

    assert padded.size == (120, 6)
