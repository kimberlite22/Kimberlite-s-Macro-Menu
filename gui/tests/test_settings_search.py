from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt

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


def test_update_settings_search_reclaims_focus_after_showing_popup(qtbot, tmp_path: Path) -> None:
    # Regression test for the "typing unfocuses the search box" bug: showing
    # self._settings_search_popup (a Qt.WindowType.Popup widget) makes Qt move keyboard
    # focus onto the popup/its list, independent of any window-manager activation, so
    # _update_settings_search must reclaim focus on settings_search_edit right after
    # showing the popup. hasFocus()/isActiveWindow() are not reliable under the
    # offscreen QPA platform this suite runs under (no real window manager, so
    # activateWindow() never actually makes a window "active"), so this asserts the
    # call order directly instead of relying on OS-level focus/activation state.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)

    call_order: list[str] = []
    original_show = window._settings_search_popup.show

    def tracked_show():
        call_order.append("popup.show")
        return original_show()

    window._settings_search_popup.show = tracked_show

    original_set_focus = window.settings_search_edit.setFocus

    def tracked_set_focus(*args, **kwargs):
        call_order.append("edit.setFocus")
        return original_set_focus(*args, **kwargs)

    window.settings_search_edit.setFocus = tracked_set_focus

    window._update_settings_search("save")

    assert window._settings_search_popup.isVisible()
    assert call_order == ["popup.show", "edit.setFocus"]


def test_settings_search_popup_and_its_list_never_accept_keyboard_focus(qtbot, tmp_path: Path) -> None:
    # Structural regression test for the follow-up report: typing a first character worked, but
    # further typing silently stopped registering once the results popup was showing. Qt's own
    # popup machinery (QApplicationPrivate::openPopup) auto-focuses the first focusable child
    # inside a Qt.WindowType.Popup widget when it becomes visible, and can reassign that focus
    # again on later geometry/content updates too - independent of any window-manager activation,
    # and independent of the explicit settings_search_edit.setFocus() call this module already
    # makes right after popup.show(). A one-shot reclaim right after the first show() cannot rule
    # out a later steal once the popup is already visible and gets updated by another keystroke.
    # The robust fix denies focus to the popup and its list outright so Qt has nothing focusable
    # inside the popup to ever reassign focus to, regardless of timing.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)

    assert window._settings_search_popup.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert window._settings_search_list.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_typing_a_second_character_while_the_popup_is_showing_keeps_focus_on_the_search_box(
    qtbot, tmp_path: Path,
) -> None:
    # Behavioral counterpart of the structural test above: types real key events into the search
    # box across two keystrokes, with the popup already visible and repopulated for the second
    # one, and asserts the search box keeps Qt's internal keyboard focus throughout. This is the
    # exact scenario test_update_settings_search_reclaims_focus_after_showing_popup (a single
    # direct call, asserting call order rather than actual focus state) could not cover.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    window.settings_search_edit.setFocus()
    qtbot.waitUntil(window.settings_search_edit.hasFocus)

    qtbot.keyClicks(window.settings_search_edit, "s")
    qtbot.waitUntil(lambda: window._settings_search_popup.isVisible())
    assert window.settings_search_edit.hasFocus()

    # Second keystroke while the popup is already visible and its list repopulates - the case a
    # one-shot post-show() reclaim does not cover.
    qtbot.keyClicks(window.settings_search_edit, "a")
    qtbot.waitUntil(lambda: window._settings_search_list.count() > 0)
    assert window.settings_search_edit.hasFocus()
    assert window.settings_search_edit.text() == "sa"


def test_focus_and_highlight_can_skip_or_apply_search_highlight(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    widget = window.settings_search_edit
    original_style = widget.styleSheet()

    window._focus_and_highlight(widget, highlight=False)
    assert widget.styleSheet() == original_style
    assert "#f0c674" not in widget.styleSheet()

    window._focus_and_highlight(widget)
    assert "#f0c674" in widget.styleSheet()


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
    assert (window.config.active_game, window._selected_preset_name) in window._edit_preset_windows


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

    editor = window._edit_preset_windows[(window.config.active_game, window._selected_preset_name)]
    assert editor._step_edit_target is None
    assert editor._step_edit_window is None
    assert editor._search_preview_step_window is not None
    assert len(editor.preset.screens[0].steps) == 3
