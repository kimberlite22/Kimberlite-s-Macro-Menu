"""Drives the file protocol in isolation (temp dir, no real OCR engine needed)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ocr_helper import protocol


def test_signal_ready_writes_marker_file(tmp_path: Path) -> None:
    protocol.signal_ready(tmp_path)
    assert (tmp_path / protocol.READY_FILENAME).read_text(encoding="utf-8") == "1"


def test_stop_requested_false_until_stop_file_exists(tmp_path: Path) -> None:
    assert protocol.stop_requested(tmp_path) is False
    (tmp_path / protocol.STOP_FILENAME).write_text("1", encoding="utf-8")
    assert protocol.stop_requested(tmp_path) is True


def test_read_next_request_returns_none_when_no_request_file(tmp_path: Path) -> None:
    assert protocol.read_next_request(tmp_path) is None


def test_read_next_request_parses_and_consumes_request(tmp_path: Path) -> None:
    req_path = tmp_path / protocol.REQUEST_FILENAME
    req_path.write_text("42|100|200|300|400", encoding="utf-8")

    request = protocol.read_next_request(tmp_path)

    assert request is not None
    assert request.token == "42"
    assert (request.x, request.y, request.width, request.height) == (100, 200, 300, 400)
    assert not req_path.exists()  # consumed on read, like ocr_server.ps1


@pytest.mark.parametrize(
    "bad_line",
    [
        "",
        "   ",
        "42|100|200",  # too few fields
        "42|abc|200|300|400",  # non-integer field
    ],
)
def test_read_next_request_discards_malformed_lines(tmp_path: Path, bad_line: str) -> None:
    req_path = tmp_path / protocol.REQUEST_FILENAME
    req_path.write_text(bad_line, encoding="utf-8")

    request = protocol.read_next_request(tmp_path)

    assert request is None
    assert not req_path.exists()


def test_write_response_is_atomic_and_readable(tmp_path: Path) -> None:
    protocol.write_response(tmp_path, "7", "Recognized Text")

    resp_path = tmp_path / protocol.RESPONSE_FILENAME
    assert resp_path.read_text(encoding="utf-8") == "7|Recognized Text"
    # no leftover .tmp file after the atomic rename
    assert not (tmp_path / (protocol.RESPONSE_FILENAME + ".tmp")).exists()


def test_write_response_handles_empty_text(tmp_path: Path) -> None:
    protocol.write_response(tmp_path, "3", "")
    assert (tmp_path / protocol.RESPONSE_FILENAME).read_text(encoding="utf-8") == "3|"


def test_cleanup_removes_ready_and_stop_files_but_keeps_others(tmp_path: Path) -> None:
    (tmp_path / protocol.READY_FILENAME).write_text("1", encoding="utf-8")
    (tmp_path / protocol.STOP_FILENAME).write_text("1", encoding="utf-8")
    (tmp_path / protocol.RESPONSE_FILENAME).write_text("1|x", encoding="utf-8")

    protocol.cleanup(tmp_path)

    assert not (tmp_path / protocol.READY_FILENAME).exists()
    assert not (tmp_path / protocol.STOP_FILENAME).exists()
    assert (tmp_path / protocol.RESPONSE_FILENAME).exists()  # cleanup only touches ready/stop


def test_serve_forever_handles_one_request_then_stops(tmp_path: Path) -> None:
    calls = []

    def handle_scan(x: int, y: int, width: int, height: int, pad_x: int, pad_y: int, color: str) -> str:
        calls.append((x, y, width, height, pad_x, pad_y, color))
        # Ask the server to stop right after handling the first request, so
        # serve_forever() returns instead of polling forever in this test.
        (tmp_path / protocol.STOP_FILENAME).write_text("1", encoding="utf-8")
        return "hello world"

    req_tmp = tmp_path / (protocol.REQUEST_FILENAME + ".tmp")
    req_path = tmp_path / protocol.REQUEST_FILENAME
    req_tmp.write_text("9|1|2|3|4|5|6|white", encoding="utf-8")
    req_tmp.replace(req_path)

    protocol.serve_forever(tmp_path, handle_scan)

    assert calls == [(1, 2, 3, 4, 5, 6, "white")]
    resp_text = (tmp_path / protocol.RESPONSE_FILENAME).read_text(encoding="utf-8")
    assert resp_text == "9|hello world"
    # cleanup() ran on exit
    assert not (tmp_path / protocol.READY_FILENAME).exists()


def test_serve_forever_exits_promptly_when_stop_file_present_from_start(tmp_path: Path) -> None:
    (tmp_path / protocol.STOP_FILENAME).write_text("1", encoding="utf-8")

    start = time.monotonic()
    protocol.serve_forever(tmp_path, lambda x, y, w, h: "unused")
    elapsed = time.monotonic() - start

    assert elapsed < 1.0


# --------------------------------------------------------------------------------------------
# The server has to survive bad input and transient I/O. It is a PERSISTENT process the macro
# depends on: every exit downgrades detection to the one-shot path, which pays full engine
# startup per scan, so "crash and let AHK restart it" is not a cheap failure here.
# --------------------------------------------------------------------------------------------


def test_an_undecodable_request_is_discarded_rather_than_raising(tmp_path: Path) -> None:
    # UnicodeDecodeError is a ValueError, not an OSError, so it used to sail past the read handler,
    # out of serve_forever(), and end the process.
    req_path = tmp_path / protocol.REQUEST_FILENAME
    req_path.write_bytes(b"\xff\xfe\x00garbage|not|a|request")

    assert protocol.read_next_request(tmp_path) is None
    assert not req_path.exists()  # consumed, so it cannot be re-read in a tight loop


def test_serve_forever_survives_an_undecodable_request_and_serves_the_next_one(tmp_path: Path) -> None:
    (tmp_path / protocol.REQUEST_FILENAME).write_bytes(b"\xff\xfe\x00bad")
    served: list[tuple] = []

    def handle_scan(x, y, w, h, pad_x, pad_y, color):
        served.append((x, y, w, h))
        # Stop only once a real request got through, which proves the bad one did not end the loop.
        (tmp_path / protocol.STOP_FILENAME).write_text("1", encoding="utf-8")
        return "ok"

    def feed_good_request():
        time.sleep(0.05)
        (tmp_path / protocol.REQUEST_FILENAME).write_text("7|1|2|3|4", encoding="utf-8")

    thread = threading.Thread(target=feed_good_request)
    thread.start()
    try:
        protocol.serve_forever(tmp_path, handle_scan)
    finally:
        thread.join()

    assert served == [(1, 2, 3, 4)]


def test_a_failed_response_write_costs_one_scan_not_the_server(tmp_path: Path, monkeypatch) -> None:
    # A sharing violation or a momentarily full disk must not end the loop: the macro is already
    # waiting on its own request timeout and escalates from there.
    (tmp_path / protocol.REQUEST_FILENAME).write_text("7|1|2|3|4", encoding="utf-8")
    attempts: list[str] = []

    def exploding_write(data_dir, token, text):
        attempts.append(token)
        (tmp_path / protocol.STOP_FILENAME).write_text("1", encoding="utf-8")
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(protocol, "write_response", exploding_write)

    protocol.serve_forever(tmp_path, lambda *args: "text")   # must return normally, not raise

    assert attempts == ["7"]
