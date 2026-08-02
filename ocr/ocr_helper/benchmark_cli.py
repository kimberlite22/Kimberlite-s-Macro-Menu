"""Command-line entry point for the separate OCR benchmark executable."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ocr_helper.benchmark_runner import BenchmarkRunner
from ocr_helper.shadow import SPOOL_DIRNAME

# Must stay identical to APP_NAME in gui/app/launcher_paths.py and AppName in
# macro/tower_defense_macro_gui.ahk: it is what makes the installed app's DataDir
# (%LOCALAPPDATA%\<APP_NAME>) resolvable from here without being told.
APP_NAME = "Kimberlite's Macro Menu"


def default_data_dir(environ: dict[str, str] | None = None) -> Path | None:
    """Return the installed app's DataDir, so the benchmark exe can just be double-clicked.

    Whoever runs this is testing a game for hours, not operating a build tool. Requiring an
    explicit --dir would mean opening a terminal and typing a path containing an apostrophe
    before the session could even start.
    """
    local_app_data = (environ if environ is not None else os.environ).get("LOCALAPPDATA")
    return Path(local_app_data) / APP_NAME if local_app_data else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ocr_benchmark")
    parser.add_argument(
        "--dir",
        default=None,
        help="The macro DataDir holding the benchmark spool. Defaults to the installed app's.",
    )
    parser.add_argument("--once", action="store_true", help="Drain currently complete spool pairs, then exit.")
    args = parser.parse_args(argv)
    data_dir = Path(args.dir) if args.dir else default_data_dir()
    if data_dir is None:
        parser.error("--dir is required because LOCALAPPDATA is not set.")
    print(f"OCR benchmark: watching {data_dir / SPOOL_DIRNAME}", flush=True)
    print("Leave this window open for the whole session. Press Ctrl+C to stop.", flush=True)
    return BenchmarkRunner(data_dir).run(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
