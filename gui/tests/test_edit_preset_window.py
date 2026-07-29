from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt

from app.edit_preset_window import EditPresetWindow, STEP_TYPES
from ipc.client import CommandAck
from ipc.config_reader import read_config
from ipc.protocol import VERB_SAVE_PRESET


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
    assert window.step_list.count() == 3
    assert "Click" in window.step_list.item(0).text()

    first = window.step_list.takeItem(0)
    window.step_list.insertItem(2, first)
    window._step_rows_moved()
    assert [step.type for step in window.preset.screens[0].steps] == ["Wait", "Drag", "Button Click"]

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    verb, payload = client.send_command.call_args.args
    assert verb == VERB_SAVE_PRESET
    assert [step["type"] for step in payload["screens"][0]["steps"]] == ["Wait", "Drag", "Button Click"]
    assert payload["options"][0]["detText"] == "Ready | Go"
    assert payload["options"][0]["detInvert"] is True


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
