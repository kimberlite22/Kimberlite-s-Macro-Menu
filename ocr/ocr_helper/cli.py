"""Command-line entry point: server mode (persistent) and one-shot mode.

Mirrors ocr_server.ps1 (server mode: `--dir <DataDir>`) and ocr_region.ps1 (one-shot
mode: `--dir <DataDir> --x <x> --y <y> --width <w> --height <h>`). Both modes are one
binary (PyInstaller onefile), selected by which flags are present, so a single build
covers what used to be two separate .ps1 scripts.
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from ocr_helper import protocol
from ocr_helper import build_config
from ocr_helper.engine import OcrEngine, maybe_upscale
from ocr_helper.shadow import SPOOL_DIRNAME, ShadowSpooler, shadow_enabled

ONE_SHOT_RESULT_FILENAME = "ocr_result.txt"


class _AsyncShadowSpooler:
    """Keep the PNG encode and disk I/O outside the protocol request-response critical path.

    Exposes the same `spool(image, **fields)` call as `ShadowSpooler` so `handle_scan` has
    exactly one spooler contract to satisfy, whether it got the real asynchronous wrapper or
    a synchronous double.
    """

    def __init__(self, spooler: ShadowSpooler) -> None:
        self._spooler = spooler
        self._pending: queue.Queue[tuple] = queue.Queue(maxsize=2)
        self._worker = threading.Thread(target=self._run, name="ocr-shadow-spool", daemon=True)
        self._worker.start()

    def spool(self, image, **kwargs) -> None:
        try:
            self._pending.put_nowait((image, kwargs))
        except queue.Full:
            # This is further back-pressure. It remains observational and is reflected in
            # the next successful sidecar through the spooler's running counter.
            self._spooler.skipped_backlog += 1

    def _run(self) -> None:
        while True:
            image, kwargs = self._pending.get()
            try:
                self._spooler.spool(image, **kwargs)
            except Exception:
                pass


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr_server",
        description="Windows OCR helper for Kimberlite's Macro Menu.",
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Directory holding the protocol files (the macro's DataDir).",
    )
    parser.add_argument("--x", type=int, help="One-shot mode: region left, in screen pixels.")
    parser.add_argument("--y", type=int, help="One-shot mode: region top, in screen pixels.")
    parser.add_argument("--width", type=int, help="One-shot mode: region width, in pixels.")
    parser.add_argument("--height", type=int, help="One-shot mode: region height, in pixels.")
    shadow_group = parser.add_mutually_exclusive_group()
    shadow_group.add_argument("--shadow-ocr", dest="shadow_ocr", action="store_true")
    shadow_group.add_argument("--no-shadow-ocr", dest="shadow_ocr", action="store_false")
    parser.set_defaults(shadow_ocr=None)
    return parser


def _is_one_shot(args: argparse.Namespace) -> bool:
    fields = (args.x, args.y, args.width, args.height)
    return any(f is not None for f in fields)


def _run_one_shot(data_dir: Path, x: int, y: int, width: int, height: int) -> int:
    engine = OcrEngine()
    text = engine.recognize_region(x, y, width, height)

    result_path = data_dir / ONE_SHOT_RESULT_FILENAME
    tmp_path = result_path.with_suffix(result_path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(result_path)
    return 0


def resolve_shadow_mode(
    cli_value: bool | None,
    *,
    environ: dict[str, str] | None = None,
    build_default: bool | None = None,
) -> bool:
    """Resolve explicit flag, environment override, then the build-time default."""
    if cli_value is not None:
        return cli_value
    default = build_config.SHADOW_OCR_DEFAULT if build_default is None else build_default
    return shadow_enabled(default, environ)


def _run_server(
    data_dir: Path,
    *,
    shadow_mode: bool = False,
    engine: OcrEngine | None = None,
    spooler: object | None = None,
    serve_forever: Callable[[Path, Callable[[int, int, int, int], str]], None] | None = None,
) -> int:
    engine = engine if engine is not None else OcrEngine()
    protocol.signal_ready(data_dir)

    # Keep the normal path structurally identical to the original production server.
    if not shadow_mode:
        def handle_scan(x: int, y: int, width: int, height: int) -> str:
            try:
                return engine.recognize_region(x, y, width, height)
            except Exception:
                return ""

        (serve_forever or protocol.serve_forever)(data_dir, handle_scan)
        return 0

    # maybe_upscale is handed to the spooler rather than applied here so that the resize runs on
    # the spooler's worker thread. Every alternate engine still scores the exact pixels WinRT
    # read, because it is the same function the production engine applies internally.
    spooler = spooler if spooler is not None else _AsyncShadowSpooler(
        ShadowSpooler(data_dir, prepare_image=maybe_upscale)
    )

    def handle_scan(x: int, y: int, width: int, height: int) -> str:
        try:
            if width <= 0 or height <= 0:
                return engine.recognize_region(x, y, width, height)
            captured = engine.capture_region(x, y, width, height)
            start = time.perf_counter()
            text = engine.recognize_image(captured)
            production_ms = (time.perf_counter() - start) * 1000
        except Exception:
            return ""
        try:
            # The production result is already in hand, so nothing below can change what the
            # macro receives. This hands over the captured frame and returns immediately: the
            # upscale, the PNG encode and the disk write all happen on the spooler's worker
            # thread, so no part of the sampling sits in the request-response path.
            spooler.spool(
                captured,
                region={"x": x, "y": y, "width": width, "height": height},
                production_text=text,
                production_ms=production_ms,
            )
        except Exception:
            pass
        return text

    (serve_forever or protocol.serve_forever)(data_dir, handle_scan)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    data_dir = Path(args.dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    shadow_mode = resolve_shadow_mode(args.shadow_ocr)
    spool_dir = data_dir / SPOOL_DIRNAME
    print(
        f"Shadow OCR: {'on' if shadow_mode else 'off'} (spool: {spool_dir})",
        file=sys.stderr,
    )

    if _is_one_shot(args):
        missing = [
            name
            for name, value in (
                ("--x", args.x),
                ("--y", args.y),
                ("--width", args.width),
                ("--height", args.height),
            )
            if value is None
        ]
        if missing:
            print(f"One-shot mode requires all of --x/--y/--width/--height (missing: {', '.join(missing)})", file=sys.stderr)
            return 2
        # One-shot mode remains unchanged. It is a fallback path, not gameplay sampling.
        return _run_one_shot(data_dir, args.x, args.y, args.width, args.height)

    return _run_server(data_dir, shadow_mode=shadow_mode)


if __name__ == "__main__":
    raise SystemExit(main())
