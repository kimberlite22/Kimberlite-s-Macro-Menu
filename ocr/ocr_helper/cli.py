"""Command-line entry point: server mode (persistent) and one-shot mode.

Mirrors ocr_server.ps1 (server mode: `--dir <DataDir>`) and ocr_region.ps1 (one-shot
mode: `--dir <DataDir> --x <x> --y <y> --width <w> --height <h>`). Both modes are one
binary (PyInstaller onefile), selected by which flags are present, so a single build
covers what used to be two separate .ps1 scripts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ocr_helper import protocol
from ocr_helper.engine import OcrEngine

ONE_SHOT_RESULT_FILENAME = "ocr_result.txt"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr_server",
        description="Windows OCR helper for Kimberlite's Anime Expedition Macro.",
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


def _run_server(data_dir: Path) -> int:
    engine = OcrEngine()
    protocol.signal_ready(data_dir)

    def handle_scan(x: int, y: int, width: int, height: int) -> str:
        try:
            return engine.recognize_region(x, y, width, height)
        except Exception:
            return ""

    protocol.serve_forever(data_dir, handle_scan)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    data_dir = Path(args.dir)
    data_dir.mkdir(parents=True, exist_ok=True)

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
        return _run_one_shot(data_dir, args.x, args.y, args.width, args.height)

    return _run_server(data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
