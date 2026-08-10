"""Shared in-memory editor for one challenge option's availability detector."""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout,
)

from app.capture import capture_region
from app.widgets import FormLayout, NoScrollDoubleSpinBox, make_independently_minimizable
from ipc.client import IpcBusyError, IpcTimeoutError
from ipc.config_reader import OptionConfig
from ipc.protocol import (
    OcrTestResult,
    VERB_SHOW_REGION_PREVIEW,
    VERB_TEST_OCR,
    format_ocr_test_result,
    show_region_preview_payload,
    ocr_test_payload,
)


class OptionAvailabilityWindow(QDialog):
    """Edit the detector fields on the caller-owned option objects only.

    ``set_target`` retargets this reusable dialog at an entry in the same
    in-memory option list that ``EditPresetWindow`` later serializes.  No IPC
    save is performed here.
    """

    def __init__(self, client: Any, parent=None) -> None:
        super().__init__(parent)
        make_independently_minimizable(self)
        self.setWindowTitle("Option Availability Check")
        self.setModal(True)
        self.client = client
        self._options: Sequence[OptionConfig] = ()
        self._target_index: int | None = None

        layout = QVBoxLayout(self)
        self.editing_label = QLabel()
        self.editing_label.setObjectName("option_availability_editing_label")
        layout.addWidget(self.editing_label)

        form = FormLayout()
        self.region1_x = self._number("option_availability_region1_x")
        self.region1_y = self._number("option_availability_region1_y")
        self.region2_x = self._number("option_availability_region2_x")
        self.region2_y = self._number("option_availability_region2_y")
        self.expected_text = QLineEdit()
        self.expected_text.setObjectName("option_availability_expected_text")
        form.addRow("Region1 X", self.region1_x)
        form.addRow("Region1 Y", self.region1_y)
        form.addRow("Region2 X", self.region2_x)
        form.addRow("Region2 Y", self.region2_y)
        form.addRow("Expected Text", self.expected_text)
        layout.addLayout(form)

        self.select_region_button = QPushButton("Select Region")
        self.select_region_button.setObjectName("option_availability_select_region_button")
        layout.addWidget(self.select_region_button)

        self.invert_checkbox = QCheckBox("Text found means UNAVAILABLE")
        self.invert_checkbox.setToolTip(
            "When unchecked, finding the text means the option is available instead."
        )
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
        # See step_edit_window: the OCR test result is a sentence quoting recognized text, so it has
        # to wrap rather than widen the dialog to fit whatever the game displayed.
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("option_availability_close_button")
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.select_region_button.clicked.connect(self._capture_region)
        self.test_ocr_button.clicked.connect(self._test_ocr)
        self.show_region_button.clicked.connect(self._show_region_preview)
        self.apply_all_button.clicked.connect(self._apply_to_all)
        self.close_button.clicked.connect(self._close)

    @staticmethod
    def _number(name: str) -> QDoubleSpinBox:
        field = NoScrollDoubleSpinBox()
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

    def _show_region_preview(self) -> None:
        try:
            ack = self.client.send_command(
                VERB_SHOW_REGION_PREVIEW,
                show_region_preview_payload(
                    self.region1_x.value(), self.region1_y.value(),
                    self.region2_x.value(), self.region2_y.value(),
                ),
            )
        except IpcTimeoutError:
            self._message("SHOW_REGION_PREVIEW: timed out, outcome unknown. Check status before retrying.")
            return
        except IpcBusyError as error:
            self._message(f"SHOW_REGION_PREVIEW: not sent ({error})")
            return
        except Exception as error:
            self._message(f"SHOW_REGION_PREVIEW: failed ({error})")
            return
        result = "OK" if ack.ok else "failed"
        self._message(f"SHOW_REGION_PREVIEW: {result} ({ack.message or result})")

    def _test_ocr(self) -> None:
        # Disabled for the whole call, not just left to the GUI looking unresponsive: pump=... below
        # keeps Qt events flowing during the up-to-~21s wait (cold OCR-server start plus its own
        # response timeout), so a second click during that same wait must not race a fresh TEST_OCR
        # command against the first one's still-pending acknowledgement (single-slot command file).
        expected = self.expected_text.text()
        self.test_ocr_button.setEnabled(False)
        try:
            try:
                ack = self.client.send_command(
                    VERB_TEST_OCR,
                    ocr_test_payload(
                        self.region1_x.value(), self.region1_y.value(),
                        self.region2_x.value(), self.region2_y.value(),
                        expected,
                    ),
                    timeout=25.0,
                    pump=QApplication.processEvents,
                )
            except IpcTimeoutError:
                self._message("TEST_OCR: timed out, outcome unknown. Check status before retrying.")
                return
            except IpcBusyError as error:
                self._message(f"TEST_OCR: not sent ({error})")
                return
            except Exception as error:
                self._message(f"TEST_OCR: failed ({error})")
                return
            if not ack.ok:
                self._message(f"TEST_OCR: failed ({ack.message or 'failed'})")
                return
            self._message(format_ocr_test_result(OcrTestResult.from_ack_data(ack.data), expected))
        finally:
            self.test_ocr_button.setEnabled(True)

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
