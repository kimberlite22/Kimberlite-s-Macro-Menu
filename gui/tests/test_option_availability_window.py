from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt

from app.option_availability_window import OptionAvailabilityWindow
from ipc.client import CommandAck
from ipc.config_reader import read_config
from ipc.protocol import (
    VERB_SHOW_REGION_PREVIEW,
    VERB_TEST_OCR,
    show_region_preview_payload,
    ocr_test_payload,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _dialog(qtbot):
    options = read_config(FIXTURE).presets[0].options
    dialog = OptionAvailabilityWindow(MagicMock())
    qtbot.addWidget(dialog)
    return dialog, options


def test_retargeted_dialog_loads_and_saves_the_target_option(qtbot) -> None:
    dialog, options = _dialog(qtbot)

    dialog.set_target(0, options)
    dialog.show()

    assert dialog.region1_x.value() == 1
    assert dialog.region1_y.value() == 2
    assert dialog.region2_x.value() == 3
    assert dialog.region2_y.value() == 4
    assert dialog.expected_text.text() == "Ready | Go"
    assert dialog.invert_checkbox.isChecked()

    dialog.expected_text.setText("Ready now")
    dialog.region2_y.setValue(44.5)
    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert options[0].det_text == "Ready now"
    assert options[0].det_end_y == 44.5
    assert options[1].det_text == "Not Ready"


def test_window_has_independent_minimize_button(qtbot) -> None:
    # Regression guard, see make_independently_minimizable: OptionAvailabilityWindow would
    # otherwise have no minimize button of its own, and its caller (EditPresetWindow)
    # deliberately constructs it with no Qt parent since a parented QDialog would be a native
    # Windows "owned window" that auto-hides whenever its owner is minimized.
    dialog, _ = _dialog(qtbot)
    assert dialog.windowFlags() & Qt.WindowMinimizeButtonHint


def test_apply_to_all_copies_live_values_to_every_option(qtbot) -> None:
    dialog, options = _dialog(qtbot)
    dialog.set_target(1, options)
    dialog.show()

    dialog.region1_x.setValue(14.25)
    dialog.region1_y.setValue(15.5)
    dialog.region2_x.setValue(16.75)
    dialog.region2_y.setValue(17.0)
    dialog.expected_text.setText("No attempts left")
    dialog.invert_checkbox.setChecked(True)
    qtbot.mouseClick(dialog.apply_all_button, Qt.MouseButton.LeftButton)

    for option in options:
        assert (option.det_x, option.det_y, option.det_end_x, option.det_end_y) == (14.25, 15.5, 16.75, 17.0)
        assert option.det_text == "No attempts left"
        assert option.det_invert is True


def test_region_preview_and_ocr_use_the_current_region(qtbot) -> None:
    dialog, options = _dialog(qtbot)
    dialog.client.send_command.return_value = CommandAck("test", True, "accepted", {"text": "Found"})
    dialog.set_target(0, options)
    dialog.show()

    qtbot.mouseClick(dialog.show_region_button, Qt.MouseButton.LeftButton)
    dialog.client.send_command.assert_called_once_with(
        VERB_SHOW_REGION_PREVIEW, show_region_preview_payload(1, 2, 3, 4),
    )

    dialog.client.send_command.reset_mock()
    qtbot.mouseClick(dialog.test_ocr_button, Qt.MouseButton.LeftButton)
    call = dialog.client.send_command.call_args
    assert call.args == (VERB_TEST_OCR, ocr_test_payload(1, 2, 3, 4, "Ready | Go"))
    assert call.kwargs["timeout"] == 25.0


def test_ocr_result_reports_the_verdict_and_the_border_it_needed(qtbot) -> None:
    dialog, options = _dialog(qtbot)
    dialog.set_target(0, options)
    dialog.client.send_command.return_value = CommandAck(
        "test", True, "accepted",
        {
            "detected": 1, "text": "Ready | Go", "padPct": 10, "padColor": "black",
            "stagesTried": 2, "stagesTotal": 7, "capped": 0, "maxSide": 750,
        },
    )

    qtbot.mouseClick(dialog.test_ocr_button, Qt.MouseButton.LeftButton)

    assert dialog.message_label.text() == (
        'DETECTED: "Ready | Go" matched from a black border of 10% per side (framing 2 of 7). '
        'Read: "Ready | Go"'
    )

    dialog.client.send_command.return_value = CommandAck(
        "test", True, "accepted",
        {
            "detected": 0, "text": "",
            "stagesTried": 7, "stagesTotal": 7, "capped": 0, "maxSide": 750,
        },
    )
    qtbot.mouseClick(dialog.test_ocr_button, Qt.MouseButton.LeftButton)

    assert dialog.message_label.text() == (
        "NOT DETECTED: the region read nothing at all. All 7 framings were tried."
    )
