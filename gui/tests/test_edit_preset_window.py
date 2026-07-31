from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

from app.edit_preset_window import EditPresetWindow, STEP_TYPES
from ipc.client import CommandAck
from ipc.config_reader import read_config
from ipc.protocol import (
    VERB_SAVE_PRESET,
    VERB_TEST_OCR,
    ocr_test_payload,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _window(qtbot) -> tuple[EditPresetWindow, MagicMock]:
    config = read_config(FIXTURE)
    client = MagicMock()
    client.send_command.return_value = CommandAck("test", True, "accepted", {})
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
    assert [window.step_type.itemText(index) for index in range(window.step_type.count())] == STEP_TYPES
    assert window.screen_list.item(0).text() == "Lobby"
    assert window.step_list.rowCount() == 3
    assert "Click" in window.step_list.item(0, 0).text()

    window.step_list.verticalHeader().moveSection(0, 2)
    assert [step.type for step in window.preset.screens[0].steps] == ["Wait", "Drag", "Button Click"]

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    verb, payload = client.send_command.call_args.args
    assert verb == VERB_SAVE_PRESET
    assert [step["type"] for step in payload["screens"][0]["steps"]] == ["Wait", "Drag", "Button Click"]
    assert payload["options"][0]["detText"] == "Ready | Go"
    assert payload["options"][0]["detInvert"] is True


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
    _, payload = client.send_command.call_args.args
    assert payload["fallbackScreen"] == "Lobby"


def test_option_availability_button_round_trips_detector_values_into_parent_save(qtbot) -> None:
    window, client = _window(qtbot)

    qtbot.mouseClick(window.option_widgets[0]["availability"], Qt.MouseButton.LeftButton)
    dialog = window.option_availability_window
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

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    _, payload = client.send_command.call_args.args
    assert payload["options"][0]["detX"] == 91.25
    assert payload["options"][0]["detEndY"] == 94.5
    assert payload["options"][0]["detText"] == "Availability confirmed"
    assert payload["options"][0]["detInvert"] is False


def test_step_type_visibility_matches_ahk_rules(qtbot) -> None:
    window, _ = _window(qtbot)

    window.step_type.setCurrentText("Wait")
    assert window.step_x.isHidden()
    assert window.step_end_x.isHidden()
    assert window.step_on_true.isVisible()
    assert window.step_on_false.isHidden()

    window.step_type.setCurrentText("Drag")
    assert window.step_x.isVisible()
    assert window.step_end_x.isVisible()
    assert window.step_drag_ms.isVisible()
    assert window.test_ocr_button.isHidden()

    window.step_type.setCurrentText("Custom Detection")
    window.step_advanced.setChecked(True)
    assert window.step_end_x.isVisible()
    assert window.step_on_true.isHidden()
    assert window.step_on_false.isHidden()
    assert window.outcomes_button.isVisible()


def test_position_button_captures_a_point_for_point_type_steps(qtbot) -> None:
    window, _ = _window(qtbot)
    window.step_type.setCurrentText("Button Click")
    assert window.position_button.text() == "Set Position"

    with patch("app.edit_preset_window.capture_point", return_value=(12.5, 34.25)) as capture:
        qtbot.mouseClick(window.position_button, Qt.MouseButton.LeftButton)

    capture.assert_called_once_with(window.client, window)
    assert window.step_x.value() == 12.5
    assert window.step_y.value() == 34.25


def test_position_button_captures_a_region_for_logic_type_steps(qtbot) -> None:
    # Regression test: this button used to always show a single-point preview of whatever was
    # already typed, even for logic/detection steps that need TWO corners - it never actually let
    # a user capture a step's position/region by clicking on screen at all.
    window, _ = _window(qtbot)
    window.step_type.setCurrentText("Detect Map")
    assert window.position_button.text() == "Select Region"

    with patch("app.edit_preset_window.capture_region", return_value=(10.5, 20.25, 30.75, 40.5)) as capture:
        qtbot.mouseClick(window.position_button, Qt.MouseButton.LeftButton)

    capture.assert_called_once_with(window.client, window)
    assert window.step_x.value() == 10.5
    assert window.step_y.value() == 20.25
    assert window.step_end_x.value() == 30.75
    assert window.step_end_y.value() == 40.5


def test_ocr_button_uses_the_current_step_region(qtbot) -> None:
    window, client = _window(qtbot)
    window.step_x.setValue(10.5)
    window.step_y.setValue(20.25)
    window.step_end_x.setValue(30.75)
    window.step_end_y.setValue(40.5)
    window.step_type.setCurrentText("Detect Map")

    qtbot.mouseClick(window.test_ocr_button, Qt.MouseButton.LeftButton)
    call = client.send_command.call_args
    assert call.args == (
        VERB_TEST_OCR, ocr_test_payload(10.5, 20.25, 30.75, 40.5),
    )
    assert call.kwargs["timeout"] == 25.0
