"""Best-effort sampling spool for the separate OCR benchmark process."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image

SPOOL_DIRNAME = "ocr_benchmark_spool"
BENCHMARK_LOG_FILENAME = "ocr_benchmark_log.jsonl"


def shadow_enabled(default: bool, environ: dict[str, str] | None = None) -> bool:
    """Return the shadow mode environment override, or the supplied build default."""
    value = (environ if environ is not None else os.environ).get("AEM_OCR_SHADOW")
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


class ShadowSpooler:
    """Write bounded, rate-limited samples without affecting production OCR."""

    def __init__(
        self,
        data_dir: Path,
        *,
        max_pending: int = 50,
        min_interval_seconds: float = 2.0,
        prepare_image: Callable[[Image.Image], Image.Image] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.spool_dir = data_dir / SPOOL_DIRNAME
        self.max_pending = max_pending
        self.min_interval_seconds = min_interval_seconds
        # Applied to the captured image just before it is written. Production passes the OCR
        # engine's own upscale here rather than applying it at the call site, so the resize
        # lands on the spooler's worker thread instead of inside the detection the macro is
        # waiting on. Injected rather than imported so this module stays independent of the
        # WinRT engine, which the benchmark runner has no business loading.
        self.prepare_image = prepare_image
        self.skipped_throttled = 0
        self.skipped_backlog = 0
        self._last_accepted: float | None = None
        self._seq = 0

    def spool(
        self,
        image: Image.Image,
        *,
        region: dict,
        production_text: str,
        production_ms: float,
    ) -> None:
        """Best-effort write of one sample. Every failure is intentionally ignored."""
        json_tmp: Path | None = None
        png_tmp: Path | None = None
        published_png: Path | None = None
        completed = False
        try:
            now_monotonic = time.monotonic()
            if (
                self._last_accepted is not None
                and now_monotonic - self._last_accepted < self.min_interval_seconds
            ):
                self.skipped_throttled += 1
                return

            self.spool_dir.mkdir(parents=True, exist_ok=True)
            if sum(1 for _ in self.spool_dir.glob("*.png")) >= self.max_pending:
                self.skipped_backlog += 1
                return

            self._last_accepted = now_monotonic
            self._seq += 1
            timestamp = datetime.now(timezone.utc)
            filename_stamp = timestamp.strftime("%Y%m%dT%H%M%S.%fZ")
            stem = f"{self._seq:08d}-{filename_stamp}"
            json_path = self.spool_dir / f"{stem}.json"
            png_path = self.spool_dir / f"{stem}.png"
            record = {
                "seq": self._seq,
                "timestamp": timestamp.isoformat(),
                "region": region,
                "production_engine": "winsdk",
                "production_text": production_text,
                "production_ms": production_ms,
                "skipped_throttled": self.skipped_throttled,
                "skipped_backlog": self.skipped_backlog,
            }
            if self.prepare_image is not None:
                image = self.prepare_image(image)
            json_tmp = json_path.with_suffix(".json.tmp")
            png_tmp = png_path.with_suffix(".png.tmp")
            # The PNG is published FIRST and the sidecar second, and the order is what keeps the
            # spool bounded. The pending cap counts *.png, so whichever file is published first
            # is the one a half-written sample leaves behind, and it has to be the counted one:
            # publishing the sidecar first meant a run of PNG encode failures could strand an
            # unlimited number of orphan .json files that nothing counted and, with no benchmark
            # runner started, nothing ever collected. It also removes a race on the reader side,
            # since the runner pairs by looking up a sidecar's PNG and the PNG now always exists
            # by the time its sidecar does.
            image.save(png_tmp, format="PNG")
            os.replace(png_tmp, png_path)
            published_png = png_path
            json_tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            os.replace(json_tmp, json_path)
            completed = True
        except Exception:
            pass
        if completed:
            return
        for leftover in (json_tmp, png_tmp, published_png):
            if leftover is None:
                continue
            try:
                leftover.unlink(missing_ok=True)
            except Exception:
                pass
