"""Windows OCR engine wrapper: screen capture (mss) + optional border padding + WinRT OCR.

Mirrors macro/ocr_server.ps1 / macro/ocr_region.ps1 (see CLAUDE.md, "Phase 1 implementation
plan"): the same `Windows.Media.Ocr` engine and the same "return empty string on any failure"
behavior. Captures reach WinRT unchanged unless the caller explicitly requests a black or white
border to give tightly cropped text a quiet zone.

Unlike the PowerShell version, no temporary PNG file is written: winsdk's SoftwareBitmap
can be built directly from the captured BGRA pixel buffer (mss's native capture format),
so the round trip through a file and a WinRT BitmapDecoder is unnecessary here.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import mss
from PIL import Image, ImageOps
from winsdk.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
from winsdk.windows.media.ocr import OcrEngine as _WinRtOcrEngine
from winsdk.windows.storage.streams import DataWriter

def pad_image(image: Image.Image, pad_x: int, pad_y: int, color: str) -> Image.Image:
    """Return `image` with an optional solid border on all four sides.

    Either axis alone is enough to pad: the caller derives pad_x/pad_y from the region's own
    width and height, so a very short region can legitimately round pad_y down to 0 while pad_x
    is still meaningful. Requiring both would silently drop the border in exactly the tightly
    cropped case this exists for. Negative values are clamped rather than rejected, since
    ImageOps.expand would otherwise crop instead of pad.
    """
    pad_x = max(0, pad_x)
    pad_y = max(0, pad_y)
    if (pad_x == 0 and pad_y == 0) or not color:
        return image
    return ImageOps.expand(image, border=(pad_x, pad_y, pad_x, pad_y), fill=color)


class OcrEngine:
    """Wraps a single, reused Windows.Media.Ocr.OcrEngine instance.

    Created once (like ocr_server.ps1's `$ocrEngine`) and reused across every
    `recognize_region` call for the life of the process, so the (~0.5s) engine
    creation cost is paid only once per session.
    """

    def __init__(self) -> None:
        self._winrt_engine = _WinRtOcrEngine.try_create_from_user_profile_languages()
        self._sct = mss.MSS()

    def recognize_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        pad_x: int = 0,
        pad_y: int = 0,
        color: str = "",
    ) -> str:
        """Captures (x, y, width, height) in absolute screen pixels and returns the
        recognized text, or "" if the region is empty, no OCR engine is available, or
        recognition fails for any reason (mirrors ocr_server.ps1's try/catch -> '')."""
        if width <= 0 or height <= 0:
            return ""
        try:
            image = self.capture_region(x, y, width, height)
            image = pad_image(image, pad_x, pad_y, color)
        except Exception:
            return ""
        return self.recognize_image(image)

    def recognize_image(self, image: Image.Image) -> str:
        """Run WinRT OCR on an already-captured image without modifying it."""
        if self._winrt_engine is None:
            return ""
        try:
            return asyncio.run(self._recognize(image))
        except Exception:
            return ""

    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        shot = self._sct.grab({"left": x, "top": y, "width": width, "height": height})
        return Image.frombytes("RGBA", shot.size, shot.raw, "raw", "BGRA")

    def save_region_image(self, x, y, width, height, path) -> bool:
        """Capture a raw screen region and publish it atomically as a PNG."""
        if width <= 0 or height <= 0:
            return False
        target = Path(path)
        tmp_path = target.with_suffix(target.suffix + ".tmp")
        try:
            image = self.capture_region(x, y, width, height)
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(tmp_path, format="PNG")
            os.replace(tmp_path, target)
            return True
        except Exception:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            return False

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
