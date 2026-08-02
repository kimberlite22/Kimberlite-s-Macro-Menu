"""Tests for the alternate engine wrappers that need none of the engines installed.

Nothing here imports pytesseract, easyocr, paddleocr or torch. Those are gigabytes and only
ever exist inside the separate benchmark bundle, so what is covered here is the wrapper
behavior around them: that a missing engine reports itself as missing on every sample rather
than only the first, and that a PaddleOCR result is read correctly whichever of its output
shapes turns up.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ocr_helper.benchmark_cli import default_data_dir
from ocr_helper.benchmark_engines import _LazyEngine, _paddle_text_fragments


class _MissingEngine(_LazyEngine):
    name = "missing"

    def __init__(self) -> None:
        super().__init__()
        self.load_attempts = 0

    def _load(self) -> None:
        self.load_attempts += 1
        raise ImportError("no module named nothing")

    def recognize_image(self, image: Image.Image) -> str:
        self.last_error = None
        if not self._ensure_loaded():
            return ""
        return "unreachable"


def test_missing_engine_reports_itself_on_every_sample_and_loads_once() -> None:
    engine = _MissingEngine()
    image = Image.new("RGB", (2, 2))

    assert engine.recognize_image(image) == ""
    assert engine.last_error == "not installed"
    assert engine.recognize_image(image) == ""
    assert engine.last_error == "not installed"
    assert engine.load_attempts == 1


def test_paddle_fragments_read_the_legacy_2x_nested_list_shape() -> None:
    result = [[[[[0, 0], [9, 0], [9, 9], [0, 9]], ("VICTORY", 0.98)]]]

    assert _paddle_text_fragments(result) == ["VICTORY"]


def test_paddle_fragments_read_the_3x_rec_texts_payload_nested_under_res() -> None:
    assert _paddle_text_fragments([{"res": {"rec_texts": ["Round", "12"]}}]) == ["Round", "12"]


def test_paddle_fragments_read_a_result_object_exposing_json() -> None:
    class Result:
        json = {"res": {"rec_texts": ["Rose Kingdom"]}}

    assert _paddle_text_fragments([Result()]) == ["Rose Kingdom"]


def test_paddle_fragments_survive_a_self_referential_result() -> None:
    class Recursive:
        @property
        def json(self):
            return [self]

    assert _paddle_text_fragments(Recursive()) == []


def test_default_data_dir_points_at_the_installed_apps_folder() -> None:
    assert default_data_dir({"LOCALAPPDATA": r"C:\Users\x\AppData\Local"}) == Path(
        r"C:\Users\x\AppData\Local\Kimberlite's Anime Expedition Macro"
    )
    assert default_data_dir({}) is None
