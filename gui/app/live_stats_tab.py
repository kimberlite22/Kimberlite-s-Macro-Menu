"""Qt home for the live panels the AHK overlay used to show around the game window."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ipc.protocol import LocalStatus


LOG_TAIL_BYTES = 64 * 1024
LOG_MAX_LINES = 200


def dropped_prefix_lines(previous_lines: list[str], new_lines: list[str]) -> int:
    """Return how many leading displayed lines a rolling append-only tail removed."""
    for dropped in range(len(previous_lines)):
        retained = previous_lines[dropped:]
        if new_lines[:len(retained)] == retained:
            return dropped
    return len(previous_lines)


def format_duration_ms(ms: int) -> str:
    """Format a duration exactly as the AHK overlay does."""
    total_seconds = int(max(ms, 0) / 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds // 60) % 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class LiveStatsTab(QWidget):
    """Shows the engine's detailed run state, screen timing and macro log."""

    def __init__(
        self,
        data_dir: str | Path,
        parent: QWidget | None = None,
        *,
        log_tail_bytes: int = LOG_TAIL_BYTES,
    ) -> None:
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.log_path = self.data_dir / "macro_log.txt"
        self.log_tail_bytes = log_tail_bytes
        self._last_status: LocalStatus | None = None
        self._preset_screens: list[str] = []
        self._table_screen_names: list[str] = []
        self._log_signature: tuple[int, int] | None = None
        self._log_lines: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        stats_box = QGroupBox("Application Stats")
        stats_layout = QVBoxLayout(stats_box)
        stats_header = QHBoxLayout()
        self.live_stats_offline_label = QLabel("Engine offline")
        self.live_stats_offline_label.setObjectName("live_stats_offline_label")
        self.live_stats_offline_label.setStyleSheet("color: #f0c674;")
        stats_header.addWidget(self.live_stats_offline_label)
        stats_header.addStretch(1)
        self.stats_copy_button = QPushButton("Copy")
        self.stats_copy_button.setObjectName("stats_copy_button")
        stats_header.addWidget(self.stats_copy_button)
        stats_layout.addLayout(stats_header)

        stats_grid = QGridLayout()
        stats = (
            ("Current Map", "stat_value_map"),
            ("Current Screen", "stat_value_screen"),
            ("Current Step", "stat_value_step"),
            ("Session Time", "stat_value_session_time"),
            ("Step Repetition Count", "stat_value_step_repeat"),
            ("Current Step Time", "stat_value_current_step_time"),
            ("Start Repetition Count", "stat_value_start_repeat"),
            ("Victory Count", "stat_value_victory"),
            ("Defeat Count", "stat_value_defeat"),
        )
        self._stat_values: dict[str, QLabel] = {}
        for index, (caption, object_name) in enumerate(stats):
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.setSpacing(2)
            caption_label = QLabel(caption)
            caption_label.setStyleSheet("color: #aeb8ca;")
            value_label = QLabel()
            value_label.setObjectName(object_name)
            value_label.setWordWrap(True)
            value_label.setStyleSheet("font-size: 16px; font-weight: 700;")
            cell_layout.addWidget(caption_label)
            cell_layout.addWidget(value_label)
            stats_grid.addWidget(cell, index // 3, index % 3)
            self._stat_values[object_name] = value_label
        stats_layout.addLayout(stats_grid)
        self.copy_feedback_label = QLabel()
        self.copy_feedback_label.setWordWrap(True)
        self.copy_feedback_label.hide()
        stats_layout.addWidget(self.copy_feedback_label)
        root.addWidget(stats_box)

        screen_time_box = QGroupBox("Screen Time")
        screen_time_layout = QVBoxLayout(screen_time_box)
        self.screen_time_table = QTableWidget(0, 2)
        self.screen_time_table.setObjectName("screen_time_table")
        self.screen_time_table.setHorizontalHeaderLabels(["Screen", "Time"])
        self.screen_time_table.verticalHeader().setVisible(False)
        self.screen_time_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.screen_time_table.horizontalHeader().setStretchLastSection(True)
        screen_time_layout.addWidget(self.screen_time_table)
        root.addWidget(screen_time_box)

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.live_log_view = QPlainTextEdit()
        self.live_log_view.setObjectName("live_log_view")
        self.live_log_view.setReadOnly(True)
        self.live_log_view.setMaximumBlockCount(LOG_MAX_LINES)
        # One document block must equal one scrollbar step, so rolling-tail compensation is exact.
        # Unwrapped timestamped log lines are also easier to scan.
        self.live_log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.live_log_view.setFont(QFont("Consolas"))
        log_layout.addWidget(self.live_log_view)
        log_caption = QLabel(f"Live tail of {self.log_path}")
        log_caption.setWordWrap(True)
        log_layout.addWidget(log_caption)
        root.addWidget(log_box, 1)

        self.stats_copy_button.clicked.connect(self._copy_stats)
        self._render_status(LocalStatus())
        self.live_stats_offline_label.show()

    def update_status(self, status: LocalStatus | None, *, stale: bool) -> None:
        """Render a fresh status, retaining the last known values while offline."""
        if status is not None and not stale:
            self._last_status = status
            self._render_status(status)
            self._render_screen_times(status.screen_time_ms)
        self.live_stats_offline_label.setVisible(status is None or stale)

    def set_preset_screens(self, screen_names: Sequence[str]) -> None:
        """Set the ordered screen rows supplied by the active or running preset."""
        names = list(screen_names)
        if names == self._preset_screens:
            return
        self._preset_screens = names
        screen_times = self._last_status.screen_time_ms if self._last_status is not None else {}
        self._render_screen_times(screen_times)

    def refresh_log(self) -> None:
        """Tail macro_log.txt without disrupting a user reading earlier log entries."""
        try:
            stat = self.log_path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            if signature == self._log_signature:
                return
            with self.log_path.open("rb") as log_file:
                if stat.st_size > self.log_tail_bytes:
                    log_file.seek(-self.log_tail_bytes, 2)
                    data = log_file.read()
                    first_newline = data.find(b"\n")
                    data = data[first_newline + 1:] if first_newline >= 0 else b""
                else:
                    data = log_file.read()
        except OSError:
            self._log_signature = None
            self._log_lines = []
            self.live_log_view.setPlainText("")
            return

        lines = data.decode("utf-8", errors="replace").splitlines()[-LOG_MAX_LINES:]
        scrollbar = self.live_log_view.verticalScrollBar()
        scroll_value = scrollbar.value()
        at_bottom = scrollbar.value() >= scrollbar.maximum()
        dropped = dropped_prefix_lines(self._log_lines, lines)
        self.live_log_view.setPlainText("\n".join(lines))
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            # A rolling tail can drop leading lines. With NoWrap, one dropped line is exactly one
            # scrollbar step, keeping the same log line under a reader's eye.
            scrollbar.setValue(scroll_value - dropped)
        self._log_signature = signature
        self._log_lines = lines

    def copy_text(self) -> str:
        """Return the exact text copied by the AHK overlay's Copy button."""
        status = self._last_status or LocalStatus()
        current_map = status.current_map or "(none)"
        current_screen = status.current_screen or "-"
        current_step = status.current_step or "-"
        current_step_time = (
            format_duration_ms(status.current_step_time_ms)
            if status.current_step_time_ms >= 0
            else "-"
        )
        return "\n".join((
            f"Screen Repetition Count: {status.cycle_count}",
            f"Current Map: {current_map}",
            f"Current Screen: {current_screen}",
            f"Current Step: {current_step}",
            f"Step Repetition Count: {status.step_repeat_count}",
            f"Session Time: {format_duration_ms(status.session_time_ms)}",
            f"Current Step Time: {current_step_time}",
            f"Start Repetition Count: {status.start_repeat_count}",
            f"Victory Count: {status.victory_count}",
            f"Defeat Count: {status.defeat_count}",
        ))

    def _copy_stats(self) -> None:
        QApplication.clipboard().setText(self.copy_text())
        self.copy_feedback_label.setText("Copied to clipboard.")
        self.copy_feedback_label.show()
        QTimer.singleShot(1500, self.copy_feedback_label.hide)

    def _render_status(self, status: LocalStatus) -> None:
        values = {
            "stat_value_map": status.current_map or "(none)",
            "stat_value_screen": status.current_screen or "-",
            "stat_value_step": status.current_step or "-",
            "stat_value_session_time": format_duration_ms(status.session_time_ms),
            "stat_value_step_repeat": str(status.step_repeat_count),
            "stat_value_current_step_time": (
                format_duration_ms(status.current_step_time_ms)
                if status.current_step_time_ms >= 0
                else "-"
            ),
            "stat_value_start_repeat": str(status.start_repeat_count),
            "stat_value_victory": str(status.victory_count),
            "stat_value_defeat": str(status.defeat_count),
        }
        for object_name, value in values.items():
            self._stat_values[object_name].setText(value)

    def _render_screen_times(self, screen_times: Mapping[str, int]) -> None:
        times = dict(screen_times)
        names = list(self._preset_screens)
        names.extend(name for name in times if name not in names)
        if names != self._table_screen_names:
            self._table_screen_names = names
            self.screen_time_table.setRowCount(len(names))
            for row, name in enumerate(names):
                self.screen_time_table.setItem(row, 0, QTableWidgetItem(name))
                self.screen_time_table.setItem(row, 1, QTableWidgetItem())
        for row, name in enumerate(names):
            self.screen_time_table.item(row, 1).setText(format_duration_ms(times.get(name, 0)))
