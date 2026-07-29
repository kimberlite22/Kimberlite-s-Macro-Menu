"""Compares the Python OCR engine's output against a frozen PowerShell/WinRT baseline.

`tests/fixtures/*.png` are synthetic "game UI text" samples (banners, map names, a
larger-than-upscale-threshold paragraph). `tests/fixtures/baseline_manifest.json` records
what the OLD implementation (macro/ocr_region.ps1, before this migration deleted it, using
the identical Windows.Media.Ocr decode + recognize path) produced for each fixture, upscaled
with the exact same heuristic. This is the actual "no accuracy regression" proof for Phase 1
of the Python migration (see CLAUDE.md): same engine, same heuristic, same result -- down to
reproducing the old engine's misreads (e.g. "1x" -> "lx" on tiny text), which is the point.

Skipped automatically if no WinRT OCR engine is available on the machine running the tests
(e.g. missing language pack), since that is an environment limitation, not a code defect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from ocr_helper.engine import OcrEngine

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


def test_upscale_heuristic_matches_powershell_thresholds(engine: OcrEngine) -> None:
    # h < 300 and w < 900 -> upscaled 2x; anything else stays 1x. Must match
    # ocr_server.ps1:74-75 / ocr_region.ps1:19 exactly (see CLAUDE.md).
    small = Image.new("RGB", (899, 299), color="white")
    assert engine._maybe_upscale(small).size == (899 * 2, 299 * 2)

    wide = Image.new("RGB", (900, 299), color="white")
    assert engine._maybe_upscale(wide).size == (900, 299)

    tall = Image.new("RGB", (899, 300), color="white")
    assert engine._maybe_upscale(tall).size == (899, 300)
