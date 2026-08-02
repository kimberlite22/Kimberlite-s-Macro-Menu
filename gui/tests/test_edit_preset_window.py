from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

from app.edit_preset_window import EditPresetWindow
from ipc.client import CommandAck
from ipc.config_reader import ScreenConfig, read_config


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _window(qtbot) -> tuple[EditPresetWindow, MagicMock]:
    config = read_config(FIXTURE)
    client = MagicMock()
    client.send_command.return_value = CommandAck("test", True, "accepted", {})
    client.save_config.return_value = "Saved: preset Preset One."
    window = EditPresetWindow(
        config.presets[0], client, [preset.name for preset in config.presets],
        [profile.name for profile in config.map_profiles],
    )
    qtbot.addWidget(window)
    window.show()
    return window, client


def test_edit_preset_populates_and_save_uses_reordered_in_memory_steps(qtbot) -> None:
    window, client = _window(qtbot)

    assert window.screen_list.count() == 2
    assert window.screen_list.item(0).text() == "Lobby"
    assert window.step_list.rowCount() == 3
    assert "Click" in window.step_list.item(0, 0).text()

    window.step_list.verticalHeader().moveSection(0, 2)
    assert [step.type for step in window.preset.screens[0].steps] == ["Wait", "Drag", "Button Click"]

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert [step["type"] for step in payload["screens"][0]["steps"]] == ["Wait", "Drag", "Button Click"]
    assert payload["options"][0]["detText"] == "Ready | Go"
    assert payload["options"][0]["detInvert"] is True


def test_window_has_independent_minimize_button(qtbot) -> None:
    # Regression guard, see make_independently_minimizable: EditPresetWindow is a QDialog
    # that would otherwise have no minimize button of its own (Qt.Dialog's default flags
    # omit one). Its caller (MainWindow) also deliberately constructs it with no Qt parent,
    # since a parented QDialog would be a native Windows "owned window" that auto-hides
    # whenever its owner is minimized regardless of this flag.
    window, _ = _window(qtbot)
    assert window.windowFlags() & Qt.WindowMinimizeButtonHint


def test_editor_content_scrolls_while_save_footer_remains_reachable(qtbot) -> None:
    window, _ = _window(qtbot)
    window.resize(500, 300)
    qtbot.waitUntil(lambda: window.editor_scroll_area.verticalScrollBar().maximum() > 0)

    scroll_area = window.findChild(QScrollArea, "preset_editor_scroll_area")
    assert scroll_area is window.editor_scroll_area
    assert not scroll_area.widget().isAncestorOf(window.save_button)
    assert window.save_button.isVisible()
    assert window.save_button.geometry().bottom() <= window.contentsRect().bottom()


def test_preset_fallback_screen_is_preselected_and_survives_save(qtbot) -> None:
    # Regression test: the fallback combo used to be selected before it had any items, so the
    # selection silently fell back to "(none)" and stayed that way even after the real screen
    # names were populated - saving any preset with a real fallback screen silently cleared it.
    window, client = _window(qtbot)

    assert window.preset_fallback_screen.currentText() == "Lobby"

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert payload["fallbackScreen"] == "Lobby"


def test_option_availability_button_round_trips_detector_values_into_parent_save(qtbot) -> None:
    window, client = _window(qtbot)

    window.step_list.setCurrentCell(0, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None
    editor.step_type.setCurrentText("Option Select")
    qtbot.mouseClick(editor.option_widgets[0]["availability"], Qt.MouseButton.LeftButton)
    dialog = editor.option_availability_window
    assert dialog.isVisible()
    assert dialog.region1_x.value() == 1
    assert dialog.region1_y.value() == 2
    assert dialog.region2_x.value() == 3
    assert dialog.region2_y.value() == 4
    assert dialog.expected_text.text() == "Ready | Go"
    assert dialog.invert_checkbox.isChecked()

    dialog.region1_x.setValue(91.25)
    dialog.region2_y.setValue(94.5)
    dialog.expected_text.setText("Availability confirmed")
    dialog.invert_checkbox.setChecked(False)
    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(editor.cancel_button, Qt.MouseButton.LeftButton)

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert payload["options"][0]["detX"] == 91.25
    assert payload["options"][0]["detEndY"] == 94.5
    assert payload["options"][0]["detText"] == "Availability confirmed"
    assert payload["options"][0]["detInvert"] is False


def test_step_editor_save_commits_shared_challenge_options_to_parent_save(qtbot) -> None:
    window, client = _window(qtbot)

    window.step_list.setCurrentCell(0, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None
    editor.step_type.setCurrentText("Option Select")
    editor.option_widgets[0]["name"].setText("Changed option")
    editor.option_widgets[0]["x"].setValue(91.25)
    editor.option_widgets[0]["priority"].setValue(7)
    qtbot.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert payload["options"][0]["name"] == "Changed option"
    assert payload["options"][0]["x"] == 91.25
    assert payload["options"][0]["priority"] == 7


def test_step_editor_cancel_discards_unsaved_challenge_option_edits(qtbot) -> None:
    window, client = _window(qtbot)

    window.step_list.setCurrentCell(0, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None
    editor.step_type.setCurrentText("Option Select")
    editor.option_widgets[0]["name"].setText("Discarded option")
    qtbot.mouseClick(editor.cancel_button, Qt.MouseButton.LeftButton)

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert payload["options"][0]["name"] == "Priority Tower"


def test_step_editor_openers_reuse_one_window_and_save_back_into_parent(qtbot) -> None:
    window, client = _window(qtbot)
    original = window.preset.screens[0].steps[0]

    window.step_list.setCurrentCell(0, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None
    assert editor.isVisible()
    assert editor.step_label.text() == original.label

    window.step_list.cellDoubleClicked.emit(1, 0)
    assert window._step_edit_window is editor
    assert editor.step_label.text() == window.preset.screens[0].steps[1].label

    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    assert window._step_edit_window is editor
    assert editor.step_type.currentText() == "Button Click"
    editor.step_label.setText("Added from secondary window")
    qtbot.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)

    assert window.preset.screens[0].steps[-1].label == "Added from secondary window"
    assert window.step_list.currentRow() == window.step_list.rowCount() - 1
    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert payload["screens"][0]["steps"][-1]["label"] == "Added from secondary window"


def test_step_editor_save_replaces_the_targeted_row(qtbot) -> None:
    window, client = _window(qtbot)

    window.step_list.setCurrentCell(1, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None
    editor.step_label.setText("Updated through secondary window")
    editor.step_x.setValue(42.5)
    qtbot.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)

    step = window.preset.screens[0].steps[1]
    assert step.label == "Updated through secondary window"
    assert step.x == 42.5
    assert window.step_list.currentRow() == 1
    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert payload["screens"][0]["steps"][1]["label"] == "Updated through secondary window"


def test_open_step_editor_screen_choices_refresh_when_screens_change(qtbot) -> None:
    window, _ = _window(qtbot)
    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None

    window.preset.screens.append(ScreenConfig(name="Results"))
    window._render_screens()

    assert editor.step_on_true.findText("Results") >= 0
    assert editor.step_fallback_screen.findText("Results") >= 0


def test_step_editor_target_survives_reordering_while_open(qtbot) -> None:
    # Regression test: the editor used to remember its target by ROW NUMBER. This window is
    # deliberately non-modal, so the steps table underneath it stays interactive - reordering
    # rows while the editor is still open used to silently repoint a stale row number at a
    # DIFFERENT step by the time Save ran, corrupting that other step instead of the one being
    # edited. Tracking the target step by object identity must survive the reorder.
    window, client = _window(qtbot)
    original = window.preset.screens[0].steps[0]
    assert original.type == "Button Click"

    window.step_list.setCurrentCell(0, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None
    assert editor.step_label.text() == original.label

    # Reorder rows in the still-interactive table while the editor remains open on `original`.
    window.step_list.verticalHeader().moveSection(0, 2)
    assert [step.type for step in window.preset.screens[0].steps] == ["Wait", "Drag", "Button Click"]
    assert window.preset.screens[0].steps[-1] is original

    editor.step_label.setText("Edited after reorder")
    qtbot.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)

    assert window.preset.screens[0].steps[-1].label == "Edited after reorder"
    assert window.preset.screens[0].steps[0].type == "Wait"
    assert window.preset.screens[0].steps[1].type == "Drag"

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert payload["screens"][0]["steps"][-1]["label"] == "Edited after reorder"


def test_screen_rename_while_step_editor_open_resyncs_migrated_target(qtbot) -> None:
    # Regression test: renaming a screen migrates on_true/on_false/fallback references onto the
    # canonical StepConfig objects (_replace_targets), but an already-open editor used to only
    # get its dropdown CHOICES refreshed, not its selected VALUE - the old name it still showed
    # was no longer a valid choice, so it silently fell back to "(continue)". Saving afterwards
    # then overwrote the correctly migrated step with that fallback. The editor must instead
    # resync from the already-migrated canonical step.
    window, client = _window(qtbot)
    step = window.preset.screens[0].steps[0]
    assert step.on_true_screen == "Battle"

    window.step_list.setCurrentCell(0, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None
    assert editor.step_on_true.currentText() == "Battle"

    window.screen_list.setCurrentRow(1)  # "Battle" is the second screen in the fixture preset.
    assert window._current_screen.name == "Battle"
    with patch("app.edit_preset_window.QInputDialog.getText", return_value=("Boss Battle", True)):
        qtbot.mouseClick(window.rename_screen_button, Qt.MouseButton.LeftButton)

    assert step.on_true_screen == "Boss Battle"
    assert editor.step_on_true.currentText() == "Boss Battle"

    qtbot.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)
    assert window.preset.screens[0].steps[0].on_true_screen == "Boss Battle"

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    payload = client.save_config.call_args.kwargs["preset"]
    assert payload["screens"][0]["steps"][0]["onTrueScreen"] == "Boss Battle"
