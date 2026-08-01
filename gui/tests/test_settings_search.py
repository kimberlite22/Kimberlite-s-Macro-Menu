from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

from app.main_window import MainWindow
from app.settings_search import SettingsSearchEntry, match_settings
from ipc.client import CommandAck


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _client() -> MagicMock:
    client = MagicMock()
    client.read_status.return_value = None
    client.send_command.return_value = CommandAck("test", True, "accepted", {})
    return client


def test_substring_matching_is_case_insensitive_and_ranks_prefixes_first() -> None:
    entries = [
        SettingsSearchEntry("Save", lambda: None),
        SettingsSearchEntry("Preset Save", lambda: None),
        SettingsSearchEntry("Save As", lambda: None),
    ]

    assert [entry.display_label for entry in match_settings(entries, "sAv")] == [
        "Save", "Save As", "Preset Save",
    ]
    assert match_settings(entries, "") == []
    assert match_settings(entries, "missing") == []


def test_main_window_index_contains_main_tab_and_secondary_window_labels(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)

    index = window._build_settings_search_index()
    labels = [entry.display_label for entry in index.entries]

    assert "Presets" in labels
    assert "Save" in labels
    assert "Remote Agent" in labels
    assert "Screens (Edit Preset)" in labels
    assert "Configure Outcomes... (Step Editor)" in labels

    next(entry for entry in index.entries if entry.display_label == "General").navigate()
    assert window.tabs.currentIndex() == 2


def test_secondary_result_requires_a_preset_then_reuses_the_editor(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    index = window._build_settings_search_index()
    result = next(entry for entry in index.entries if entry.display_label == "Screens (Edit Preset)")

    # MainWindow auto-selects a preset on load (mirrors the "Edit" button's own default state),
    # so the "nothing selected" guard is exercised by explicitly clearing the selection first.
    window._selected_preset_name = ""
    result.navigate()
    assert window.statusBar().currentMessage() == "Select a preset first."

    window.preset_list.setCurrentRow(0)
    result.navigate()
    assert window._selected_preset_name in window._edit_preset_windows


def test_step_editor_search_result_does_not_queue_a_phantom_new_step(qtbot, tmp_path: Path) -> None:
    # Regression test: navigating into the Step Editor / Advanced Outcomes from search must
    # be read-only. _open_step_editor(None) (the "Add Step" path) sets a real edit target
    # that a later Save would use to APPEND a new step; search must use
    # _open_step_editor_for_search() instead, which never touches that target.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    index = window._build_settings_search_index()
    result = next(entry for entry in index.entries if entry.display_label == "Configure Outcomes... (Step Editor)")

    window.preset_list.setCurrentRow(0)
    result.navigate()

    editor = window._edit_preset_windows[window._selected_preset_name]
    assert editor._step_edit_target is None
    assert editor._step_edit_window is None
    assert editor._search_preview_step_window is not None
    assert len(editor.preset.screens[0].steps) == 3
