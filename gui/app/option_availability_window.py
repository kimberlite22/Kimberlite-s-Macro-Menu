"""Shared in-memory editor for one challenge option's availability detector."""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout,
)

from app.capture import capture_region
from ipc.config_reader import OptionConfig


class OptionAvailabilityWindow(QDialog):
    """Edit the detector fields on the caller-owned option objects only.

    ``set_target`` retargets this reusable dialog at an entry in the same
    in-memory option list that ``EditPresetWindow`` later serializes.  No IPC
    save is performed here.
    """

    def __init__(self, client: Any, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Option Availability Check")
        self.setModal(True)
        self.client = client
        self._options: Sequence[OptionConfig] = ()
        self._target_index: int | None = None

        layout = QVBoxLayout(self)
        self.editing_label = QLabel()
        self.editing_label.setObjectName("option_availability_editing_label")
        layout.addWidget(self.editing_label)

        form = QFormLayout()
        self.region1_x = self._number("option_availability_region1_x")
        self.region1_y = self._number("option_availability_region1_y")
        self.region2_x = self._number("option_availability_region2_x")
        self.region2_y = self._number("option_availability_region2_y")
        self.expected_text = QLineEdit()
        self.expected_text.setObjectName("option_availability_expected_text")
        form.addRow("Region1 X:", self.region1_x)
        form.addRow("Region1 Y:", self.region1_y)
        form.addRow("Region2 X:", self.region2_x)
        form.addRow("Region2 Y:", self.region2_y)
        form.addRow("Expected Text:", self.expected_text)
        layout.addLayout(form)

        self.select_region_button = QPushButton("Select Region")
        self.select_region_button.setObjectName("option_availability_select_region_button")
        layout.addWidget(self.select_region_button)

        self.invert_checkbox = QCheckBox("Text found means UNAVAILABLE (instead of available)")
        self.invert_checkbox.setObjectName("option_availability_invert")
        layout.addWidget(self.invert_checkbox)

        actions = QHBoxLayout()
        self.test_ocr_button = QPushButton("Test OCR")
        self.test_ocr_button.setObjectName("option_availability_test_ocr_button")
        self.show_region_button = QPushButton("Show Region")
        self.show_region_button.setObjectName("option_availability_show_region_button")
        actions.addWidget(self.test_ocr_button)
        actions.addWidget(self.show_region_button)
        layout.addLayout(actions)

        self.apply_all_button = QPushButton("Apply to All 3 Options")
        self.apply_all_button.setObjectName("option_availability_apply_all_button")
        layout.addWidget(self.apply_all_button)

        self.message_label = QLabel()
        self.message_label.setObjectName("option_availability_message")
        layout.addWidget(self.message_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("option_availability_close_button")
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.select_region_button.clicked.connect(self._capture_region)
        self.test_ocr_button.clicked.connect(lambda: self._message("OCR test is not implemented yet."))
        self.show_region_button.clicked.connect(lambda: self._message("Region preview is not implemented yet."))
        self.apply_all_button.clicked.connect(self._apply_to_all)
        self.close_button.clicked.connect(self._close)

    @staticmethod
    def _number(name: str) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setObjectName(name)
        field.setRange(-999999.0, 999999.0)
        field.setDecimals(6)
        return field

    def set_target(self, index: int, options: Sequence[OptionConfig]) -> None:
        """Load one option and retain its caller-owned option collection."""
        if not 0 <= index < len(options):
            raise IndexError("option availability target is outside the option list")
        self._target_index = index
        self._options = options
        option = options[index]
        self.editing_label.setText(f"Editing: Option {index + 1} ({option.name}) availability check")
        self.region1_x.setValue(option.det_x)
        self.region1_y.setValue(option.det_y)
        self.region2_x.setValue(option.det_end_x)
        self.region2_y.setValue(option.det_end_y)
        self.expected_text.setText(option.det_text)
        self.invert_checkbox.setChecked(option.det_invert)
        self.message_label.clear()

    def _capture_region(self) -> None:
        # Hiding this dialog, rather than its parent editor, leaves the editor intact and restores
        # the exact popup the user was editing once the AHK capture overlay finishes.
        try:
            captured = capture_region(self.client, self)
        except Exception as error:
            # Matches MainWindow._capture_placement's handling: a busy/offline/timed-out bridge
            # must surface as a status message here too, not an unhandled exception from this slot.
            self._message(f"Capture failed: {error}")
            return
        if captured is None:
            self._message("Capture cancelled.")
            return
        self.region1_x.setValue(captured[0])
        self.region1_y.setValue(captured[1])
        self.region2_x.setValue(captured[2])
        self.region2_y.setValue(captured[3])

    def _field_values(self) -> tuple[float, float, float, float, str, bool]:
        return (
            self.region1_x.value(), self.region1_y.value(),
            self.region2_x.value(), self.region2_y.value(),
            self.expected_text.text(), self.invert_checkbox.isChecked(),
        )

    def _write_to(self, option: OptionConfig) -> None:
        det_x, det_y, det_end_x, det_end_y, det_text, det_invert = self._field_values()
        option.det_x = det_x
        option.det_y = det_y
        option.det_end_x = det_end_x
        option.det_end_y = det_end_y
        option.det_text = det_text
        option.det_invert = det_invert

    def _apply_to_all(self) -> None:
        for option in self._options:
            self._write_to(option)
        self._message("Availability Check settings applied to all 3 options.")

    def _close(self) -> None:
        if self._target_index is not None:
            self._write_to(self._options[self._target_index])
        self.accept()

    def reject(self) -> None:
        """Treat the title-bar close control the same as AHK's Close button."""
        self._close()

    def _message(self, text: str) -> None:
        self.message_label.setText(text)
