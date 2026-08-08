from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from app.step_edit_window import STEP_TYPES, StepEditWindow
from ipc.client import CommandAck
from ipc.config_reader import AdvancedStep, OptionConfig, StepConfig
from ipc.protocol import VERB_SHOW_POINT_PREVIEW, VERB_TEST_OCR, ocr_test_payload, show_point_preview_payload


def _window(qtbot) -> tuple[StepEditWindow, MagicMock]:
    client = MagicMock()
    client.send_command.return_value = CommandAck("test", True, "accepted", {"text": "Found"})
    window = StepEditWindow(client)
    qtbot.addWidget(window)
    window.open_for(None, ["Lobby", "Results"], [])
    window.show()
    return window, client


def _map_action_window(qtbot) -> tuple[StepEditWindow, MagicMock]:
    client = MagicMock()
    window = StepEditWindow(client, map_action_mode=True)
    qtbot.addWidget(window)
    window.open_for_map_action(None)
    window.show()
    return window, client


def test_step_type_visibility_matches_ahk_rules(qtbot) -> None:
    window, _ = _window(qtbot)

    assert [window.step_type.itemText(index) for index in range(window.step_type.count())] == STEP_TYPES
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


def test_map_action_mode_limits_types_and_hides_preset_only_fields(qtbot) -> None:
    window, _ = _map_action_window(qtbot)

    assert window.windowTitle() == "Map Action Editor"
    assert [window.step_type.itemText(index) for index in range(window.step_type.count())] == ["Drag", "Zoom Out"]
    for step_type in ("Drag", "Zoom Out"):
        window.step_type.setCurrentText(step_type)
        assert window.step_label.isHidden()
        assert window.step_seconds.isHidden()
        assert window.step_on_true.isHidden()
        assert window.step_on_false.isHidden()
        assert window.step_fallback_enabled.isHidden()
        assert window.step_fallback_max.isHidden()
        assert window.step_fallback_screen.isHidden()
        assert window.step_advanced.isHidden()
        assert window.outcomes_button.isHidden()
        assert window.test_ocr_button.isHidden()
        assert window.step_once.isHidden()
        assert window.options_box.isHidden()
    window.step_type.setCurrentText("Drag")
    assert window.set_end_position_button.isVisible()


def test_open_for_map_action_round_trips_the_advanced_step_fields(qtbot) -> None:
    window, _ = _map_action_window(qtbot)
    received: list[StepConfig] = []
    window.saved.connect(received.append)
    step = AdvancedStep(type="Drag", x=12.5, y=34.25, end_x=56.75, end_y=78.5, drag_ms=900)

    window.open_for_map_action(step)

    assert window.step_type.currentText() == "Drag"
    assert (
        window.step_x.value(), window.step_y.value(), window.step_end_x.value(), window.step_end_y.value(),
        window.step_drag_ms.value(),
    ) == (12.5, 34.25, 56.75, 78.5, 900)
    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    assert len(received) == 1
    saved = received[0]
    assert (saved.type, saved.x, saved.y, saved.end_x, saved.end_y, saved.drag_ms) == (
        "Drag", 12.5, 34.25, 56.75, 78.5, 900,
    )
    assert saved.label == ""
    assert saved.seconds == 0
    assert not saved.once_per_cycle
    assert saved.on_true_screen == "(continue)"
    assert saved.on_false_screen == "(continue)"
    assert not saved.fallback_enabled
    assert not saved.advanced
    assert saved.outcomes_raw == ""


def test_open_for_map_action_without_a_step_resets_to_an_empty_drag(qtbot) -> None:
    window, _ = _map_action_window(qtbot)
    window.open_for_map_action(AdvancedStep(type="Drag", x=1, y=2, end_x=3, end_y=4, drag_ms=900))

    window.open_for_map_action(None)

    assert window.step_type.currentText() == "Drag"
    assert (window.step_x.value(), window.step_y.value(), window.step_end_x.value(), window.step_end_y.value()) == (
        0, 0, 0, 0,
    )


def test_end_position_button_captures_drag_endpoint_and_only_shows_for_drag(qtbot) -> None:
    window, _ = _window(qtbot)
    window.step_type.setCurrentText("Drag")
    assert window.set_end_position_button.isVisible()

    with patch("app.step_edit_window.capture_point", return_value=(12.5, 34.25)) as capture:
        qtbot.mouseClick(window.set_end_position_button, Qt.MouseButton.LeftButton)

    capture.assert_called_once_with(window.client, window)
    assert (window.step_end_x.value(), window.step_end_y.value()) == (12.5, 34.25)

    window.step_type.setCurrentText("Zoom Out")
    assert window.set_end_position_button.isHidden()
    window.step_type.setCurrentText("Button Click")
    assert window.set_end_position_button.isHidden()


def test_default_window_keeps_all_step_types_and_label_field(qtbot) -> None:
    window, _ = _window(qtbot)

    assert window.windowTitle() == "Step Editor"
    assert [window.step_type.itemText(index) for index in range(window.step_type.count())] == STEP_TYPES
    assert window.step_label.isVisible()


def test_challenge_options_are_shared_and_only_visible_for_option_select(qtbot) -> None:
    client = MagicMock()
    options = [
        OptionConfig(name="First", x=1.5, y=2.5, available=True, priority=3, max_uses=4),
        OptionConfig(name="Second"),
        OptionConfig(name="Third"),
    ]
    first_option = options[0]
    window = StepEditWindow(client)
    qtbot.addWidget(window)
    window.open_for(StepConfig(type="Option Select"), ["Lobby"], options)
    window.show()

    assert window.options_box.isVisible()
    assert window.option_widgets[0]["name"].text() == "First"
    assert window.option_widgets[0]["x"].value() == 1.5
    assert window.option_widgets[0]["available"].isChecked()
    assert window.option_widgets[0]["priority"].value() == 3
    assert window.option_widgets[0]["max_uses"].value() == 4

    window.step_type.setCurrentText("Wait")
    assert window.options_box.isHidden()
    window.step_type.setCurrentText("Option Select")
    assert window.options_box.isVisible()
    window.option_widgets[0]["name"].setText("Changed")
    window.option_widgets[0]["x"].setValue(9.5)
    window.option_widgets[0]["priority"].setValue(8)
    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    assert options[0] is first_option
    assert options[0].name == "Changed"
    assert options[0].x == 9.5
    assert options[0].priority == 8


def test_window_with_a_parent_remains_a_visible_top_level_dialog(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    window = StepEditWindow(MagicMock(), parent)
    qtbot.addWidget(window)
    window.open_for(None, ["Lobby"], [])
    window.show()

    assert window.isWindow()
    assert window in QApplication.topLevelWidgets()
    # make_independently_minimizable's flag is applied unconditionally in __init__, regardless
    # of whether a parent is supplied - this test passes one deliberately (unlike production,
    # which constructs StepEditWindow with no parent, see edit_preset_window.py) to prove the
    # flag doesn't depend on it.
    assert window.windowFlags() & Qt.WindowMinimizeButtonHint


def test_position_button_captures_point_and_region(qtbot) -> None:
    window, _ = _window(qtbot)
    window.step_type.setCurrentText("Button Click")
    assert window.position_button.text() == "Set Position"

    with patch("app.step_edit_window.capture_point", return_value=(12.5, 34.25)) as capture:
        qtbot.mouseClick(window.position_button, Qt.MouseButton.LeftButton)

    capture.assert_called_once_with(window.client, window)
    assert (window.step_x.value(), window.step_y.value()) == (12.5, 34.25)

    window.step_type.setCurrentText("Detect Map")
    assert window.position_button.text() == "Select Region"
    with patch("app.step_edit_window.capture_region", return_value=(10.5, 20.25, 30.75, 40.5)) as capture:
        qtbot.mouseClick(window.position_button, Qt.MouseButton.LeftButton)

    capture.assert_called_once_with(window.client, window)
    assert (
        window.step_x.value(), window.step_y.value(),
        window.step_end_x.value(), window.step_end_y.value(),
    ) == (10.5, 20.25, 30.75, 40.5)


def test_ocr_button_uses_the_current_step_region(qtbot) -> None:
    window, client = _window(qtbot)
    window.step_x.setValue(10.5)
    window.step_y.setValue(20.25)
    window.step_end_x.setValue(30.75)
    window.step_end_y.setValue(40.5)
    window.step_label.setText("Map ready")
    window.step_type.setCurrentText("Detect Map")

    qtbot.mouseClick(window.test_ocr_button, Qt.MouseButton.LeftButton)

    call = client.send_command.call_args
    assert call.args == (VERB_TEST_OCR, ocr_test_payload(10.5, 20.25, 30.75, 40.5, "Map ready"))
    assert call.kwargs["timeout"] == 25.0
    assert window.status_label.text() == "OCR result: Found (no detection)"


def test_ocr_result_reports_the_escalation_stage_or_no_detection(qtbot) -> None:
    window, client = _window(qtbot)
    client.send_command.return_value = CommandAck(
        "test", True, "accepted", {"text": "Found", "stage": "white border +25%"},
    )

    qtbot.mouseClick(window.test_ocr_button, Qt.MouseButton.LeftButton)

    assert window.status_label.text() == "OCR result: Found (detected at: white border +25%)"

    client.send_command.return_value = CommandAck("test", True, "accepted", {"text": ""})
    qtbot.mouseClick(window.test_ocr_button, Qt.MouseButton.LeftButton)

    assert window.status_label.text() == "OCR result:  (no detection)"


def test_show_buttons_use_the_current_step_and_option_coordinates(qtbot) -> None:
    window, client = _window(qtbot)
    window.step_type.setCurrentText("Drag")
    window.step_x.setValue(10.5)
    window.step_y.setValue(20.25)
    window.step_end_x.setValue(30.75)
    window.step_end_y.setValue(40.5)

    qtbot.mouseClick(window.show_position_button, Qt.MouseButton.LeftButton)
    client.send_command.assert_called_once_with(
        VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(10.5, 20.25),
    )

    client.send_command.reset_mock()
    qtbot.mouseClick(window.show_end_position_button, Qt.MouseButton.LeftButton)
    client.send_command.assert_called_once_with(
        VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(30.75, 40.5),
    )

    window.step_type.setCurrentText("Option Select")
    window.option_widgets[0]["x"].setValue(50.5)
    window.option_widgets[0]["y"].setValue(60.25)
    client.send_command.reset_mock()
    qtbot.mouseClick(window.option_widgets[0]["show"], Qt.MouseButton.LeftButton)
    client.send_command.assert_called_once_with(
        VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(50.5, 60.25),
    )


def test_configure_outcomes_uses_current_screen_names_and_round_trips(qtbot) -> None:
    window, _ = _window(qtbot)
    window.step_type.setCurrentText("Custom Detection")
    window.step_advanced.setChecked(True)

    with patch("app.step_edit_window.AdvancedOutcomesWindow") as dialog_class:
        dialog = dialog_class.return_value
        dialog.exec.return_value = QDialog.DialogCode.Accepted
        dialog.result_outcomes_raw = "Boss=Results"
        qtbot.mouseClick(window.outcomes_button, Qt.MouseButton.LeftButton)

    # No Qt parent: see make_independently_minimizable, a parented QDialog would be a native
    # Windows "owned window" that auto-hides whenever its owner (this StepEditWindow) minimizes.
    dialog_class.assert_called_once_with("", ["Lobby", "Results"])
    assert window._editing_outcomes_raw == "Boss=Results"
    assert window._step_from_editor().outcomes_raw == "Boss=Results"


def test_save_emits_step_and_cancel_or_title_close_discards_edits(qtbot) -> None:
    window, _ = _window(qtbot)
    received: list[StepConfig] = []
    window.saved.connect(received.append)
    window.step_label.setText("Saved step")
    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    assert len(received) == 1
    assert received[0].label == "Saved step"
    assert not window.isVisible()

    window.open_for(None, ["Lobby"], [])
    window.show()
    window.step_label.setText("Discarded")
    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    assert len(received) == 1

    window.open_for(None, ["Lobby"], [])
    window.show()
    window.step_label.setText("Also discarded")
    window.close()
    assert len(received) == 1
