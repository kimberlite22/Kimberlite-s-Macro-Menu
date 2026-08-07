from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel

from app.live_stats_tab import LOG_MAX_LINES, LiveStatsTab, dropped_prefix_lines, format_duration_ms
from ipc.protocol import LocalStatus


@pytest.mark.parametrize(("milliseconds", "expected"), [
    (0, "0:00"),
    (59_999, "0:59"),
    (60_000, "1:00"),
    (3_599_999, "59:59"),
    (3_600_000, "1:00:00"),
    (-1, "0:00"),
])
def test_format_duration_ms_boundaries(milliseconds: int, expected: str) -> None:
    assert format_duration_ms(milliseconds) == expected


def test_application_stats_use_ahk_placeholders_and_format_values(qtbot, tmp_path: Path) -> None:
    tab = LiveStatsTab(tmp_path)
    qtbot.addWidget(tab)

    tab.update_status(LocalStatus(), stale=False)

    assert tab.findChild(QLabel, "stat_value_map").text() == "(none)"
    assert tab.findChild(QLabel, "stat_value_screen").text() == "-"
    assert tab.findChild(QLabel, "stat_value_step").text() == "-"
    assert tab.findChild(QLabel, "stat_value_current_step_time").text() == "-"

    tab.update_status(LocalStatus(
        current_map="Map", current_screen="Lobby", current_step="Wait", session_time_ms=61_000,
        current_step_time_ms=3_600_000,
    ), stale=False)

    assert tab.findChild(QLabel, "stat_value_map").text() == "Map"
    assert tab.findChild(QLabel, "stat_value_session_time").text() == "1:01"
    assert tab.findChild(QLabel, "stat_value_current_step_time").text() == "1:00:00"


def test_copy_text_matches_copy_stats_click(qtbot, tmp_path: Path) -> None:
    tab = LiveStatsTab(tmp_path)
    qtbot.addWidget(tab)
    tab.update_status(LocalStatus(
        cycle_count=7, current_map="Map", current_screen="Lobby", current_step="Wait (ready)",
        step_repeat_count=8, session_time_ms=3_600_000, current_step_time_ms=61_000,
        start_repeat_count=9, victory_count=10, defeat_count=11,
    ), stale=False)

    assert tab.copy_text() == "\n".join((
        "Screen Repetition Count: 7",
        "Current Map: Map",
        "Current Screen: Lobby",
        "Current Step: Wait (ready)",
        "Step Repetition Count: 8",
        "Session Time: 1:00:00",
        "Current Step Time: 1:01",
        "Start Repetition Count: 9",
        "Victory Count: 10",
        "Defeat Count: 11",
    ))


def test_screen_time_rows_keep_preset_order_and_do_not_rebuild(qtbot, tmp_path: Path) -> None:
    tab = LiveStatsTab(tmp_path)
    qtbot.addWidget(tab)
    tab.set_preset_screens(["Lobby", "Battle"])
    first_item = tab.screen_time_table.item(0, 0)
    tab.set_preset_screens(["Lobby", "Battle"])

    assert tab.screen_time_table.item(0, 0) is first_item
    tab.update_status(LocalStatus(screen_time_ms={"Battle": 61_000, "Unknown": 2_000}), stale=False)

    assert [tab.screen_time_table.item(row, 0).text() for row in range(3)] == [
        "Lobby", "Battle", "Unknown",
    ]
    assert [tab.screen_time_table.item(row, 1).text() for row in range(3)] == [
        "0:00", "1:01", "0:02",
    ]


def test_offline_status_retains_values_until_a_fresh_status_arrives(qtbot, tmp_path: Path) -> None:
    tab = LiveStatsTab(tmp_path)
    qtbot.addWidget(tab)
    tab.update_status(LocalStatus(current_map="Map"), stale=False)

    tab.update_status(None, stale=True)

    assert tab.findChild(QLabel, "stat_value_map").text() == "Map"
    assert not tab.live_stats_offline_label.isHidden()
    tab.update_status(LocalStatus(current_map="New Map"), stale=False)
    assert tab.live_stats_offline_label.isHidden()
    assert tab.findChild(QLabel, "stat_value_map").text() == "New Map"


def test_log_tail_limits_lines_and_drops_a_partial_first_line(qtbot, tmp_path: Path) -> None:
    tab = LiveStatsTab(tmp_path, log_tail_bytes=1201)
    qtbot.addWidget(tab)
    log_path = tmp_path / "macro_log.txt"
    log_path.write_text("".join(f"{index:03d}\n" for index in range(400)), encoding="utf-8")

    tab.refresh_log()

    lines = tab.live_log_view.toPlainText().splitlines()
    assert len(lines) == LOG_MAX_LINES
    assert lines[0] == "200"
    assert lines[-1] == "399"

    tab.log_tail_bytes = 14
    log_path.write_text("partial-line\nwhole\nlast\n", encoding="utf-8")
    tab.refresh_log()
    assert tab.live_log_view.toPlainText() == "whole\nlast"

    log_path.unlink()
    tab.refresh_log()
    assert tab.live_log_view.toPlainText() == ""


def test_log_scroll_position_compensates_for_dropped_rolling_tail_lines(qtbot, tmp_path: Path) -> None:
    tab = LiveStatsTab(tmp_path)
    qtbot.addWidget(tab)
    tab.resize(900, 700)
    tab.show()
    qtbot.wait(10)
    log_path = tmp_path / "macro_log.txt"
    log_path.write_text("".join(f"{index:04d}\n" for index in range(LOG_MAX_LINES)), encoding="utf-8")
    tab.refresh_log()

    scrollbar = tab.live_log_view.verticalScrollBar()
    assert scrollbar.maximum() > 20
    previous_value = scrollbar.maximum() // 2
    scrollbar.setValue(previous_value)
    appended_lines = 12
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("".join(
            f"{index:04d}\n" for index in range(LOG_MAX_LINES, LOG_MAX_LINES + appended_lines)
        ))

    tab.refresh_log()

    assert scrollbar.value() == previous_value - appended_lines


def test_log_scroll_at_bottom_stays_at_bottom_after_append(qtbot, tmp_path: Path) -> None:
    tab = LiveStatsTab(tmp_path)
    qtbot.addWidget(tab)
    tab.resize(900, 700)
    tab.show()
    qtbot.wait(10)
    log_path = tmp_path / "macro_log.txt"
    log_path.write_text("".join(f"{index:04d}\n" for index in range(LOG_MAX_LINES)), encoding="utf-8")
    tab.refresh_log()

    scrollbar = tab.live_log_view.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("after bottom\n")
    tab.refresh_log()

    assert scrollbar.value() == scrollbar.maximum()


def test_log_scroll_handles_replaced_log_without_overlap(qtbot, tmp_path: Path) -> None:
    tab = LiveStatsTab(tmp_path)
    qtbot.addWidget(tab)
    tab.resize(900, 700)
    tab.show()
    qtbot.wait(10)
    log_path = tmp_path / "macro_log.txt"
    original_lines = [f"old {index:04d}" for index in range(LOG_MAX_LINES)]
    log_path.write_text("\n".join(original_lines), encoding="utf-8")
    tab.refresh_log()

    scrollbar = tab.live_log_view.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum() // 2)
    new_lines = [f"new {index:04d}" for index in range(LOG_MAX_LINES)]
    log_path.write_text("\n".join(new_lines), encoding="utf-8")
    tab.refresh_log()

    assert dropped_prefix_lines(original_lines, new_lines) == len(original_lines)
    assert scrollbar.minimum() <= scrollbar.value() <= scrollbar.maximum()
