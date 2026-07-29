from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt

from app.option_availability_window import OptionAvailabilityWindow
from ipc.config_reader import read_config


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
