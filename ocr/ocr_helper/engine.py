"""Windows OCR engine wrapper: screen capture (mss) + upscale (Pillow) + WinRT OCR.

Mirrors macro/ocr_server.ps1 / macro/ocr_region.ps1 (see CLAUDE.md, "Phase 1 implementation
plan"): the same `Windows.Media.Ocr` engine, the same upscale heuristic, and the same
"return empty string on any failure" behavior, so accuracy does not change from the
PowerShell implementation this replaces.

Unlike the PowerShell version, no temporary PNG file is written: winsdk's SoftwareBitmap
can be built directly from the captured BGRA pixel buffer (mss's native capture format),
so the round trip through a file and a WinRT BitmapDecoder is unnecessary here.
"""

from __future__ import annotations

import asyncio

import mss
from PIL import Image
from winsdk.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
from winsdk.windows.media.ocr import OcrEngine as _WinRtOcrEngine
from winsdk.windows.storage.streams import DataWriter

# Windows OCR recognizes small text (game banners/buttons) far more reliably when the
# image is enlarged. Upscale smaller regions 2x with high-quality interpolation; leave
# already-large regions at 1x so OCR doesn't slow down needlessly. Must match
# ocr_server.ps1's heuristic exactly, or detection accuracy shifts versus before.
_UPSCALE_MAX_HEIGHT = 300
_UPSCALE_MAX_WIDTH = 900
_UPSCALE_FACTOR = 2


def maybe_upscale(image: Image.Image) -> Image.Image:
    """Apply the production OCR resize heuristic without changing its pixels otherwise."""
    w, h = image.size
    if h < _UPSCALE_MAX_HEIGHT and w < _UPSCALE_MAX_WIDTH:
        return image.resize((w * _UPSCALE_FACTOR, h * _UPSCALE_FACTOR), Image.BICUBIC)
    return image


class OcrEngine:
    """Wraps a single, reused Windows.Media.Ocr.OcrEngine instance.

    Created once (like ocr_server.ps1's `$ocrEngine`) and reused across every
    `recognize_region` call for the life of the process, so the (~0.5s) engine
    creation cost is paid only once per session.
    """

    def __init__(self) -> None:
        self._winrt_engine = _WinRtOcrEngine.try_create_from_user_profile_languages()
        self._sct = mss.MSS()

    def recognize_region(self, x: int, y: int, width: int, height: int) -> str:
        """Captures (x, y, width, height) in absolute screen pixels and returns the
        recognized text, or "" if the region is empty, no OCR engine is available, or
        recognition fails for any reason (mirrors ocr_server.ps1's try/catch -> '')."""
        if width <= 0 or height <= 0:
            return ""
        try:
            image = self.capture_region(x, y, width, height)
        except Exception:
            return ""
        return self.recognize_image(image)

    def recognize_image(self, image: Image.Image) -> str:
        """Runs the same upscale + OCR pipeline as `recognize_region` on an already-
        captured image. Split out from `recognize_region` so tests can feed fixture
        images directly without a real screen capture."""
        if self._winrt_engine is None:
            return ""
        try:
            image = self._maybe_upscale(image)
            return asyncio.run(self._recognize(image))
        except Exception:
            return ""

    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        shot = self._sct.grab({"left": x, "top": y, "width": width, "height": height})
        return Image.frombytes("RGBA", shot.size, shot.raw, "raw", "BGRA")

    def _maybe_upscale(self, image: Image.Image) -> Image.Image:
        return maybe_upscale(image)

    async def _recognize(self, image: Image.Image) -> str:
        w, h = image.size
        data = image.convert("RGBA").tobytes("raw", "BGRA")
        writer = DataWriter()
        writer.write_bytes(data)
        buffer = writer.detach_buffer()
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            buffer, BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.IGNORE
        )
        try:
            result = await self._winrt_engine.recognize_async(bitmap)
            return result.text
        finally:
            bitmap.close()
