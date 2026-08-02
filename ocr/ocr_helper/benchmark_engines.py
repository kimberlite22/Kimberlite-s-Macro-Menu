"""Lazy alternate OCR wrappers used only by the separate benchmark executable.

EasyOCR and PaddleOCR download their model weights when first used. Imports and model
initialization are intentionally deferred so a missing optional engine only affects its
own benchmark result, never the benchmark runner or production OCR helper.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PIL import Image


class _LazyEngine:
    name = ""

    def __init__(self) -> None:
        self.last_error: str | None = None
        self._loaded = False
        # Remembered separately from last_error, which every recognize_image call clears: an
        # engine that failed to load once is never retried, so without its own copy the very
        # first sample would report "not installed" and every later one would report a blank
        # error next to blank text, which reads as "this engine returned nothing" instead of
        # "this engine was never there".
        self._load_error: str | None = None

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return True
        if self._load_error is not None:
            self.last_error = self._load_error
            return False
        try:
            self._load()
            self._loaded = True
            return True
        except ImportError:
            self._load_error = "not installed"
        except Exception as exc:
            self._load_error = _error_text(exc)
        self.last_error = self._load_error
        return False

    def _load(self) -> None:
        raise NotImplementedError


def _error_text(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


class PytesseractEngine(_LazyEngine):
    name = "pytesseract"

    def _load(self) -> None:
        import pytesseract

        bundled_dir = _bundle_root() / "tesseract"
        bundled_exe = bundled_dir / "tesseract.exe"
        configured_exe = os.environ.get("AEM_TESSERACT_EXE")
        if configured_exe:
            pytesseract.pytesseract.tesseract_cmd = configured_exe
        elif bundled_exe.exists():
            pytesseract.pytesseract.tesseract_cmd = str(bundled_exe)
            os.environ["TESSDATA_PREFIX"] = str(bundled_dir / "tessdata")
        self._pytesseract = pytesseract

    def recognize_image(self, image: Image.Image) -> str:
        self.last_error = None
        if not self._ensure_loaded():
            return ""
        try:
            return self._pytesseract.image_to_string(image.convert("RGB"))
        except Exception as exc:
            self.last_error = _error_text(exc)
            return ""


class EasyOcrEngine(_LazyEngine):
    name = "easyocr"

    def _load(self) -> None:
        import easyocr
        import numpy

        self._numpy = numpy
        self._reader = easyocr.Reader(["en"], gpu=False)

    def recognize_image(self, image: Image.Image) -> str:
        self.last_error = None
        if not self._ensure_loaded():
            return ""
        try:
            results = self._reader.readtext(self._numpy.array(image.convert("RGB")))
            return "\n".join(str(result[1]) for result in results if len(result) > 1)
        except Exception as exc:
            self.last_error = _error_text(exc)
            return ""


class PaddleOcrEngine(_LazyEngine):
    name = "paddleocr"

    def _load(self) -> None:
        import numpy
        import paddleocr

        self._numpy = numpy
        try:
            self._reader = paddleocr.PaddleOCR(lang="en", use_angle_cls=False)
        except TypeError as exc:
            raise RuntimeError(f"unsupported PaddleOCR constructor: {_error_text(exc)}") from exc

    def recognize_image(self, image: Image.Image) -> str:
        self.last_error = None
        if not self._ensure_loaded():
            return ""
        try:
            pixels = self._numpy.array(image.convert("RGB"))
            if hasattr(self._reader, "predict"):
                try:
                    result = self._reader.predict(pixels)
                except TypeError as exc:
                    raise RuntimeError(f"unsupported PaddleOCR predict API: {_error_text(exc)}") from exc
            else:
                try:
                    result = self._reader.ocr(pixels, cls=False)
                except TypeError as exc:
                    raise RuntimeError(f"unsupported PaddleOCR ocr API: {_error_text(exc)}") from exc
            return "\n".join(_paddle_text_fragments(result))
        except Exception as exc:
            self.last_error = _error_text(exc)
            return ""


_MAX_PADDLE_DEPTH = 8


def _paddle_text_fragments(value: Any, depth: int = 0) -> list[str]:
    """Extract recognition strings from every PaddleOCR result shape this may meet.

    PaddleOCR changed its output twice over the versions the `benchmark` extra allows, and the
    benchmark is worthless if a working engine silently scores as empty text, so all three
    shapes are handled rather than pinning to one release:

    - 2.x `ocr()`: a nested list ending in `(box, (text, confidence))` tuples.
    - 3.x `predict()`: `Result` objects whose payload is a dict, with the recognized strings
      under `rec_texts`, itself frequently nested one level down under `res`.
    - Either version wrapped in a `.json` property rather than being a mapping itself.

    The depth cap is what keeps a self-referential result object (a `.json` that returns the
    same object) from recursing forever; nothing legitimate nests anywhere near that deep.
    """
    if value is None or depth > _MAX_PADDLE_DEPTH:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        for key in ("rec_texts", "texts", "text"):
            if key in value:
                return _paddle_text_fragments(value[key], depth + 1)
        # 3.x wraps the payload one level down; "overall_ocr_res" is the pipeline variant.
        for key in ("res", "overall_ocr_res"):
            if key in value:
                return _paddle_text_fragments(value[key], depth + 1)
        return []
    for attribute in ("rec_texts", "json"):
        payload = getattr(value, attribute, None)
        if payload is None or payload is value:
            continue
        fragments = _paddle_text_fragments(payload, depth + 1)
        if fragments:
            return fragments
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], (tuple, list)):
        if value[1] and isinstance(value[1][0], str):
            return [value[1][0]]
    if isinstance(value, (list, tuple)):
        fragments = []
        for item in value:
            fragments.extend(_paddle_text_fragments(item, depth + 1))
        return fragments
    if isinstance(value, Iterable):
        fragments = []
        for item in value:
            fragments.extend(_paddle_text_fragments(item, depth + 1))
        return fragments
    return []
