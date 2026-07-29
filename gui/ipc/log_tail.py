"""Small, polling-friendly tailer for macro_log.txt."""

from __future__ import annotations

from pathlib import Path


class LogTail:
    def __init__(self, path: str | Path, start_offset: int | None = None) -> None:
        self.path = Path(path)
        self.offset = start_offset
        self._partial = ""

    def poll(self) -> list[str]:
        """Return complete lines appended since the preceding poll.

        The first poll begins at EOF unless a starting offset was supplied.
        A smaller file is treated as rotation or truncation and read from zero.
        """
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if self.offset is None:
            self.offset = size
            return []
        if size < self.offset:
            self.offset = 0
            self._partial = ""
        try:
            with self.path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                handle.seek(self.offset)
                text = handle.read()
                self.offset = handle.tell()
        except OSError:
            return []
        combined = self._partial + text
        lines = combined.splitlines(keepends=True)
        self._partial = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            self._partial = lines.pop()
        return [line.rstrip("\r\n") for line in lines]
