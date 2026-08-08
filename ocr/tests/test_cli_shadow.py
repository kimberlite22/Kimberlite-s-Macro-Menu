"""Tests for server-only shadow plumbing with injected lightweight doubles."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ocr_helper.cli import _build_arg_parser, _run_server, resolve_shadow_mode


class StubEngine:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def recognize_region(
        self, x: int, y: int, width: int, height: int, *, pad_x: int = 0, pad_y: int = 0, color: str = "",
    ) -> str:
        self.calls.append(("recognize_region", x, y, width, height, pad_x, pad_y, color))
        return "production text"

    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        self.calls.append(("capture_region", x, y, width, height))
        return Image.new("RGB", (4, 3), color="white")

    def recognize_image(self, image: Image.Image) -> str:
        self.calls.append(("recognize_image", image.size))
        return "production text"


class StubSpooler:
    def __init__(self) -> None:
        self.samples: list[dict] = []

    def spool(self, image: Image.Image, **kwargs) -> None:
        self.samples.append({"size": image.size, **kwargs})


def _serve_one_request(data_dir: Path, handle_scan) -> None:
    # A padded rung, so the assertions below also prove the padding fields reach the engine
    # rather than being dropped somewhere between the protocol and the scan handler.
    _serve_one_request.result = handle_scan(10, 20, 4, 3, 2, 1, "black")


def test_resolution_order_and_mutually_exclusive_flags() -> None:
    assert resolve_shadow_mode(True, environ={"AEM_OCR_SHADOW": "0"}, build_default=False) is True
    assert resolve_shadow_mode(None, environ={"AEM_OCR_SHADOW": "yes"}, build_default=False) is True
    assert resolve_shadow_mode(None, environ={}, build_default=True) is True
    parser = _build_arg_parser()
    assert parser.parse_args(["--dir", "x"]).shadow_ocr is None
    assert parser.parse_args(["--dir", "x", "--no-shadow-ocr"]).shadow_ocr is False


def test_server_off_uses_exact_production_recognize_region_path(tmp_path: Path) -> None:
    engine = StubEngine()

    assert _run_server(tmp_path, engine=engine, serve_forever=_serve_one_request) == 0
    assert _serve_one_request.result == "production text"
    assert engine.calls == [("recognize_region", 10, 20, 4, 3, 2, 1, "black")]


def test_server_shadow_returns_production_text_after_one_capture(tmp_path: Path) -> None:
    engine = StubEngine()
    spooler = StubSpooler()

    assert _run_server(
        tmp_path,
        shadow_mode=True,
        engine=engine,
        spooler=spooler,
        serve_forever=_serve_one_request,
    ) == 0
    assert _serve_one_request.result == "production text"
    # The 4x3 stub capture becomes 8x5 once the requested rung's 2px/1px border is applied, which
    # is what proves the padding lands between the capture and the recognize rather than being
    # dropped: recognize_image must see the PADDED image, not the raw capture.
    assert engine.calls == [
        ("capture_region", 10, 20, 4, 3),
        ("recognize_image", (8, 5)),
    ]
    assert len(spooler.samples) == 1
    # The spooled sample is the exact image WinRT read, border included, so an alternate engine
    # scoring it is scored on the same pixels rather than on a differently framed crop.
    assert spooler.samples[0]["size"] == (8, 5)
    assert spooler.samples[0]["production_text"] == "production text"
