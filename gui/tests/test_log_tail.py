from __future__ import annotations

from pathlib import Path

from ipc.log_tail import LogTail


def test_log_tail_reads_appends_and_handles_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "macro_log.txt"
    tail = LogTail(path)
    assert tail.poll() == []
    path.write_text("old\n", encoding="utf-8")
    assert tail.poll() == []  # first successful poll seeks to current EOF
    with path.open("a", encoding="utf-8") as handle:
        handle.write("one\ntwo\n")
    assert tail.poll() == ["one", "two"]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("three\n")
    assert tail.poll() == ["three"]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("partial")
    assert tail.poll() == []
    with path.open("a", encoding="utf-8") as handle:
        handle.write(" line\n")
    assert tail.poll() == ["partial line"]


def test_log_tail_restarts_after_truncation(tmp_path: Path) -> None:
    path = tmp_path / "macro_log.txt"
    path.write_text("existing\n", encoding="utf-8")
    tail = LogTail(path, start_offset=path.stat().st_size)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("before\n")
    assert tail.poll() == ["before"]
    path.write_text("new\n", encoding="utf-8")
    assert tail.poll() == ["new"]
