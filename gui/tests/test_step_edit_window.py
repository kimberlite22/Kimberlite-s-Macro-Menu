from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from app.step_edit_window import STEP_TYPES, StepEditWindow
from ipc.client import CommandAck
from ipc.config_reader import OptionConfig, StepConfig
from ipc.protocol import VERB_TEST_OCR, ocr_test_payload


def _window(qtbot) -> tuple[StepEditWindow, MagicMock]:
    client = MagicMock()
    client.send_command.return_value = CommandAck("test", True, "accepted", {"text": "Found"})
    window = StepEditWindow(client)
    qtbot.addWidget(window)
    window.open_for(None, ["Lobby", "Results"], [])
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
    window.step_type.setCurrentText("Detect Map")

    qtbot.mouseClick(window.test_ocr_button, Qt.MouseButton.LeftButton)

    call = client.send_command.call_args
    assert call.args == (VERB_TEST_OCR, ocr_test_payload(10.5, 20.25, 30.75, 40.5))
    assert call.kwargs["timeout"] == 25.0
    assert window.status_label.text() == "OCR result: Found"


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
