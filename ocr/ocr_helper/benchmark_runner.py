"""Polling runner for OCR benchmark spool samples."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from ocr_helper.benchmark_engines import EasyOcrEngine, PaddleOcrEngine, PytesseractEngine
from ocr_helper.shadow import BENCHMARK_LOG_FILENAME, SPOOL_DIRNAME

STOP_FILENAME = "ocr_benchmark_stop.txt"
# Appended to a spooled PNG's full filename (so "x.png" becomes "x.png.claimed") the moment
# this runner takes ownership of it. Deliberately a suffix on the whole name: it matches
# neither the producer's "*.png" pending count nor this runner's own "*.png" pairing glob.
CLAIM_SUFFIX = ".claimed"


class BenchmarkRunner:
    """Drain spool pairs, compare engines, and append one JSONL record for each pair."""

    def __init__(
        self,
        data_dir: Path,
        *,
        engines: Iterable[Any] | None = None,
        poll_interval_seconds: float = 0.25,
        orphan_grace_seconds: float = 5.0,
        progress_interval_seconds: float = 10.0,
    ) -> None:
        self.data_dir = data_dir
        self.spool_dir = data_dir / SPOOL_DIRNAME
        self.log_path = data_dir / BENCHMARK_LOG_FILENAME
        self.engines = list(engines) if engines is not None else [
            PytesseractEngine(), EasyOcrEngine(), PaddleOcrEngine()
        ]
        self.poll_interval_seconds = poll_interval_seconds
        self.orphan_grace_seconds = orphan_grace_seconds
        self.progress_interval_seconds = progress_interval_seconds
        self.processed_count = 0
        self._elapsed_ms: dict[str, float] = {engine.name: 0.0 for engine in self.engines}
        self._last_progress = time.monotonic()

    def build_record(self, sidecar: dict[str, Any], image: Image.Image) -> dict[str, Any]:
        results: dict[str, dict[str, Any]] = {
            "production": {
                "text": sidecar.get("production_text", ""),
                "ms": sidecar.get("production_ms", 0.0),
                "error": None,
            }
        }
        for engine in self.engines:
            started = time.perf_counter()
            text = ""
            error: str | None = None
            try:
                text = engine.recognize_image(image)
                error = getattr(engine, "last_error", None)
            except Exception as exc:
                error = str(exc) or type(exc).__name__
            elapsed_ms = (time.perf_counter() - started) * 1000
            results[engine.name] = {"text": text or "", "ms": elapsed_ms, "error": error}
            self._elapsed_ms[engine.name] = self._elapsed_ms.get(engine.name, 0.0) + elapsed_ms

        record = dict(sidecar)
        record["results"] = results
        return record

    def drain_once(self) -> int:
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale()
        processed = 0
        for json_path in sorted(self.spool_dir.glob("*.json"), key=self._oldest_first_key):
            png_path = json_path.with_suffix(".png")
            if not png_path.exists():
                continue
            claimed_png = self._claim(png_path)
            if claimed_png is None:
                continue
            if self._process_pair(json_path, claimed_png):
                processed += 1
        return processed

    @staticmethod
    def _oldest_first_key(path: Path) -> tuple[float, str]:
        try:
            return (path.stat().st_mtime, path.name)
        except OSError:
            return (float("inf"), path.name)

    def _claim(self, png_path: Path) -> Path | None:
        """Rename the PNG out of the way before any OCR runs, or return None.

        This single rename is what makes the drain safe, and it has to happen BEFORE the
        expensive work rather than after it. Deleting the pair only at the end left two ways
        to go wrong: a failed JSON delete meant the very same sample was re-OCR'd and appended
        to the log on every following poll, and a failed PNG delete meant a file that counts
        against the spooler's pending cap was never reclaimed. Renaming first fixes both,
        because a claimed name matches neither the drain's own "*.json" plus "*.png" pairing
        nor the producer's "*.png" backlog count, so a crash anywhere after this point can
        only ever leave files behind for the age sweep to collect - never a duplicate record.
        """
        claimed = png_path.with_name(png_path.name + CLAIM_SUFFIX)
        try:
            os.replace(png_path, claimed)
        except OSError:
            return None
        return claimed

    def _process_pair(self, json_path: Path, claimed_png: Path) -> bool:
        try:
            sidecar = json.loads(json_path.read_text(encoding="utf-8"))
            with Image.open(claimed_png) as opened:
                image = opened.copy()
            record = self.build_record(sidecar, image)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            # The claimed PNG stays behind for the age sweep instead of being retried: a sample
            # whose image or sidecar cannot be read will not become readable on the next poll,
            # and one unusable frame out of a ten hour session is worth nothing next to a drain
            # loop that could spin on it forever.
            return False
        for path in (json_path, claimed_png):
            try:
                path.unlink()
            except OSError:
                pass
        self.processed_count += 1
        return True

    def _cleanup_stale(self) -> None:
        """Collect anything the pairing logic can no longer act on, once it is old enough.

        Three shapes end up here: a sidecar whose PNG never arrived (the producer died between
        the two writes), a PNG claimed by a run that then crashed, and a PNG whose sidecar is
        gone. The grace period is what keeps this from racing the producer, which writes the
        sidecar first and the PNG a moment later.
        """
        cutoff = time.time() - self.orphan_grace_seconds
        for path in self.spool_dir.iterdir():
            name = path.name
            if name.endswith(".json"):
                partner: Path | None = path.with_suffix(".png")
            elif name.endswith(".png" + CLAIM_SUFFIX):
                partner = None
            elif name.endswith(".png"):
                partner = path.with_suffix(".json")
            else:
                continue
            try:
                if path.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            if partner is not None and partner.exists():
                continue
            try:
                path.unlink()
            except OSError:
                pass

    def run(self, *, once: bool = False) -> int:
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        try:
            while not (self.data_dir / STOP_FILENAME).exists():
                processed = self.drain_once()
                self._print_progress_if_due()
                if once:
                    return 0
                if processed == 0:
                    time.sleep(self.poll_interval_seconds)
        except KeyboardInterrupt:
            return 0
        return 0

    def _print_progress_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_progress < self.progress_interval_seconds:
            return
        self._last_progress = now
        averages = ", ".join(
            f"{engine.name}={self._elapsed_ms.get(engine.name, 0.0) / self.processed_count:.1f}ms"
            for engine in self.engines
        ) if self.processed_count else "no samples yet"
        print(f"OCR benchmark: processed={self.processed_count}, {averages}", flush=True)
