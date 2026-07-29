"""Launch the PySide6 presentation process for the local macro bridge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main_window import MainWindow


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="animeexpedition-gui",
        description="PySide6 GUI for Kimberlite's Anime Expedition Macro.",
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Directory containing config.ini and the local bridge files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    data_dir = Path(args.dir).resolve()

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    stylesheet_path = Path(__file__).with_name("style.qss")
    app.setStyleSheet(stylesheet_path.read_text(encoding="utf-8"))
    window = MainWindow(data_dir)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
