"""Tests for the one-shot CLI paths without requiring a real screen or OCR engine."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ocr_helper import cli


class StubEngine:
    def __init__(self) -> None:
        self.recognize_calls = 0

    def save_region_image(self, x, y, width, height, path) -> bool:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (width, height), (10, 20, 30, 255)).save(path, format="PNG")
        return True

    def recognize_region(self, x, y, width, height, *, pad_x=0, pad_y=0, color="") -> str:
        self.recognize_calls += 1
        return "recognized text"


def test_save_image_one_shot_writes_png_without_ocr_result(tmp_path: Path, monkeypatch) -> None:
    engine = StubEngine()
    monkeypatch.setattr(cli, "OcrEngine", lambda: engine)
    output = tmp_path / "samples" / "region.png"

    result = cli.main([
        "--dir", str(tmp_path / "data"), "--x", "1", "--y", "2", "--width", "6", "--height", "4",
        "--save-image", str(output),
    ])

    assert result == 0
    with Image.open(output) as image:
        assert image.size == (6, 4)
    assert not (tmp_path / "data" / cli.ONE_SHOT_RESULT_FILENAME).exists()
    assert engine.recognize_calls == 0


def test_save_image_alone_reports_missing_geometry(tmp_path: Path, capsys) -> None:
    result = cli.main(["--dir", str(tmp_path), "--save-image", str(tmp_path / "region.png")])

    assert result == 2
    assert "One-shot mode requires all of --x/--y/--width/--height" in capsys.readouterr().err


def test_normal_one_shot_still_writes_ocr_result(tmp_path: Path, monkeypatch) -> None:
    engine = StubEngine()
    monkeypatch.setattr(cli, "OcrEngine", lambda: engine)
    data_dir = tmp_path / "data"

    result = cli.main([
        "--dir", str(data_dir), "--x", "1", "--y", "2", "--width", "6", "--height", "4",
    ])

    assert result == 0
    assert (data_dir / cli.ONE_SHOT_RESULT_FILENAME).read_text(encoding="utf-8") == "recognized text"
    assert engine.recognize_calls == 1
