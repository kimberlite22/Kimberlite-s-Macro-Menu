"""Non-modal editor for one preset step."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from app.advanced_outcomes_window import AdvancedOutcomesWindow
from app.capture import capture_point, capture_region
from app.option_availability_window import OptionAvailabilityWindow
from app.widgets import (
    FormLayout,
    NoScrollComboBox,
    NoScrollDoubleSpinBox,
    NoScrollSpinBox,
    make_independently_minimizable,
)
from ipc.client import IpcBusyError, IpcTimeoutError
from ipc.config_reader import OptionConfig, StepConfig
from ipc.protocol import VERB_SHOW_POINT_PREVIEW, VERB_TEST_OCR, ocr_test_payload, show_point_preview_payload


STEP_TYPES = [
    "Start", "Option Select", "Button Click", "Press Start Button",
    "Restart Stage Button", "Camera Setup", "Place Towers", "Drag", "Zoom Out",
    "Wait", "Detect Map", "Round End Detection", "Ingame Detection", "Custom Detection",
]
LOGIC_STEP_TYPES = {"Detect Map", "Round End Detection", "Ingame Detection", "Custom Detection"}
POINT_STEP_TYPES = {"Button Click", "Press Start Button", "Restart Stage Button"}


class StepEditWindow(QDialog):
    """Keep one step edit local until Save emits a replacement StepConfig."""

    saved = Signal(object)

    def __init__(self, client: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        make_independently_minimizable(self)
        self.client = client
        self._screen_names: list[str] = []
        self._editing_outcomes_raw = ""
        self._advanced_outcomes_window: AdvancedOutcomesWindow | None = None
        self._options: list[OptionConfig] | None = None
        self.setWindowTitle("Step Editor")
        self.resize(950, 620)
        self._build_ui()
        # Deliberately no Qt parent: see make_independently_minimizable in app/widgets.py -
        # a parented QDialog becomes a native Windows "owned window" that minimizes together
        # with its owner, which is exactly what this window must not do.
        self.option_availability_window = OptionAvailabilityWindow(self.client)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        editor = QGridLayout()
        root.addLayout(editor)
        self._field_labels: dict[str, QLabel] = {}
        self._field_widgets: dict[str, QWidget] = {}

        self.step_type = NoScrollComboBox()
        self.step_type.setObjectName("step_type")
        self.step_type.addItems(STEP_TYPES)
        self.step_label = QLineEdit()
        self.step_label.setObjectName("step_label")
        self.step_x = self._number("step_x")
        self.step_y = self._number("step_y")
        self.step_end_x = self._number("step_end_x")
        self.step_end_y = self._number("step_end_y")
        self.step_drag_ms = self._integer("step_drag_ms", 0, 600000)
        self.step_seconds = self._number("step_seconds")
        self.step_once = QCheckBox("Once per cycle")
        self.step_once.setObjectName("step_once_per_cycle")
        self.step_on_true = NoScrollComboBox()
        self.step_on_true.setObjectName("step_on_true")
        self.step_on_false = NoScrollComboBox()
        self.step_on_false.setObjectName("step_on_false")
        self.step_fallback_enabled = QCheckBox()
        self.step_fallback_enabled.setObjectName("step_fallback_enabled")
        self.step_fallback_max = self._integer("step_fallback_max", 0, 99999)
        self.step_fallback_screen = NoScrollComboBox()
        self.step_fallback_screen.setObjectName("step_fallback_screen")
        self.step_advanced = QCheckBox()
        self.step_advanced.setObjectName("step_advanced")
        self.outcomes_button = QPushButton("Configure Outcomes...")
        self.outcomes_button.setObjectName("configure_outcomes_button")
        self.position_button = QPushButton("Set Position")
        self.position_button.setObjectName("step_position_button")
        self.test_ocr_button = QPushButton("Test OCR")
        self.test_ocr_button.setObjectName("step_test_ocr_button")
        self.show_position_button = QPushButton("Show")
        self.show_position_button.setObjectName("step_show_position_button")
        self.show_end_position_button = QPushButton("Show")
        self.show_end_position_button.setObjectName("step_show_end_position_button")
        show_positions = QWidget()
        show_positions_layout = QHBoxLayout(show_positions)
        show_positions_layout.setContentsMargins(0, 0, 0, 0)
        show_positions_layout.addWidget(self.show_position_button)
        show_positions_layout.addWidget(self.show_end_position_button)

        self._add_editor_row(editor, 0, "type", "Type", self.step_type)
        self._add_editor_row(editor, 0, "label", "Name", self.step_label, 2)
        self._add_editor_row(editor, 1, "x", "X", self.step_x)
        self._add_editor_row(editor, 1, "y", "Y", self.step_y, 2)
        self._add_editor_row(editor, 2, "end_x", "End X", self.step_end_x)
        self._add_editor_row(editor, 2, "end_y", "End Y", self.step_end_y, 2)
        self._add_editor_row(editor, 3, "drag_ms", "Drag", self.step_drag_ms)
        self._field_labels["drag_ms"].setToolTip("Measured in milliseconds.")
        self._field_widgets["drag_ms"].setToolTip("Measured in milliseconds.")
        self._add_editor_row(editor, 3, "seconds", "Wait After", self.step_seconds, 2)
        self._field_labels["seconds"].setToolTip("Measured in seconds.")
        self._field_widgets["seconds"].setToolTip("Measured in seconds.")
        self._add_editor_row(editor, 4, "on_true", "Then Go To ->", self.step_on_true)
        self._add_editor_row(editor, 4, "on_false", "On False ->", self.step_on_false, 2)
        self._add_editor_row(editor, 5, "fallback_enabled", "Fallback after N attempts", self.step_fallback_enabled)
        self._add_editor_row(editor, 5, "fallback_max", "Max attempts", self.step_fallback_max, 2)
        self._add_editor_row(editor, 6, "fallback_screen", "Fallback Screen ->", self.step_fallback_screen)
        self._add_editor_row(editor, 6, "advanced", "Advanced Detection", self.step_advanced, 2)
        self._add_editor_row(editor, 7, "outcomes", "", self.outcomes_button)
        self._add_editor_row(editor, 7, "position", "", self.position_button, 2)
        self._add_editor_row(editor, 8, "test_ocr", "", self.test_ocr_button)
        self._add_editor_row(editor, 8, "show_positions", "", show_positions, 2)
        editor.addWidget(self.step_once, 9, 0, 1, 4)

        self.options_box = QGroupBox("Challenge options")
        options_layout = QHBoxLayout(self.options_box)
        self.option_widgets: list[dict[str, QWidget]] = []
        for index in range(1, 4):
            group = QGroupBox(f"Option {index}")
            form = FormLayout(group)
            widgets: dict[str, QWidget] = {
                "name": QLineEdit(), "x": self._number(f"option_{index}_x"),
                "y": self._number(f"option_{index}_y"), "available": QCheckBox(),
                "priority": self._integer(f"option_{index}_priority", 0, 100),
                "max_uses": self._integer(f"option_{index}_max_uses", 0, 99999),
            }
            widgets["availability"] = QPushButton("Availability Check...")
            widgets["availability"].setObjectName(f"option_{index}_availability_button")
            widgets["show"] = QPushButton("Show")
            widgets["show"].setObjectName(f"option_{index}_show_button")
            form.addRow("Name", widgets["name"])
            form.addRow("X", widgets["x"])
            form.addRow("Y", widgets["y"])
            form.addRow(widgets["show"])
            form.addRow("Available at start", widgets["available"])
            form.addRow("Priority", widgets["priority"])
            form.addRow("Max uses", widgets["max_uses"])
            form.addRow(widgets["availability"])
            widgets["availability"].clicked.connect(lambda checked=False, option_index=index - 1: self._open_option_availability(option_index))  # type: ignore[attr-defined]
            widgets["show"].clicked.connect(lambda checked=False, option_index=index - 1: self._show_option_position(option_index))  # type: ignore[attr-defined]
            options_layout.addWidget(group)
            self.option_widgets.append(widgets)
        root.addWidget(self.options_box)

        self.status_label = QLabel()
        self.status_label.setObjectName("step_edit_status")
        root.addWidget(self.status_label)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("step_edit_save_button")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("step_edit_cancel_button")
        footer.addWidget(self.save_button)
        footer.addWidget(self.cancel_button)
        root.addLayout(footer)

        self.step_type.currentTextChanged.connect(self._update_field_visibility)
        self.step_advanced.toggled.connect(self._update_field_visibility)
        self.step_fallback_enabled.toggled.connect(self._update_field_visibility)
        self.outcomes_button.clicked.connect(self._edit_outcomes)
        self.position_button.clicked.connect(self._capture_position)
        self.test_ocr_button.clicked.connect(self._test_ocr)
        self.show_position_button.clicked.connect(self._show_position)
        self.show_end_position_button.clicked.connect(self._show_end_position)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self._reset_step_editor()

    def open_for(
        self, step: StepConfig | None, screen_names: list[str], options: list[OptionConfig],
    ) -> None:
        """Load an existing step or empty fields, and refresh explicit screen choices."""
        self.set_screen_names(screen_names)
        self._options = options
        self._load_options(options)
        if step is None:
            self._reset_step_editor()
        else:
            self._load_step(step)

    def set_screen_names(self, screen_names: list[str]) -> None:
        self._screen_names = list(screen_names)
        self._refresh_targets()

    def _add_editor_row(
        self, grid: QGridLayout, row: int, key: str, label: str, widget: QWidget,
        column: int = 0,
    ) -> None:
        field_label = QLabel(label)
        field_label.setBuddy(widget)
        self._field_labels[key] = field_label
        self._field_widgets[key] = widget
        grid.addWidget(field_label, row, column)
        grid.addWidget(widget, row, column + 1)

    @staticmethod
    def _number(name: str) -> QDoubleSpinBox:
        field = NoScrollDoubleSpinBox()
        field.setObjectName(name)
        field.setRange(-999999.0, 999999.0)
        field.setDecimals(6)
        return field

    @staticmethod
    def _integer(name: str, minimum: int, maximum: int) -> QSpinBox:
        field = NoScrollSpinBox()
        field.setObjectName(name)
        field.setRange(minimum, maximum)
        return field

    def _refresh_targets(self) -> None:
        self._replace_combo(self.step_on_true, ["(continue)", "(Repeat)", *self._screen_names], "(continue)")
        self._replace_combo(self.step_on_false, ["(continue)", "(Repeat)", *self._screen_names], "(continue)")
        self._replace_combo(
            self.step_fallback_screen,
            ["(none)", "(Stop Macro)", *self._screen_names],
            "(none)",
        )

    @staticmethod
    def _replace_combo(combo: QComboBox, values: list[str], fallback: str) -> None:
        current = combo.currentText()
        with QSignalBlocker(combo):
            combo.clear()
            combo.addItems(values)
            combo.setCurrentText(current if current in values else fallback)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str, fallback: str) -> None:
        combo.setCurrentText(value if value and combo.findText(value) >= 0 else fallback)

    def _set_visibility(self, key: str, visible: bool) -> None:
        self._field_labels[key].setVisible(visible)
        self._field_widgets[key].setVisible(visible)

    def _update_field_visibility(self, *args: Any) -> None:
        step_type = self.step_type.currentText()
        is_logic = step_type in LOGIC_STEP_TYPES
        is_drag = step_type == "Drag"
        is_custom = step_type == "Custom Detection"
        advanced = is_custom and self.step_advanced.isChecked()
        has_point = step_type in POINT_STEP_TYPES or is_drag or is_logic
        self._field_labels["label"].setText("Expected Text:" if step_type in {"Round End Detection", "Ingame Detection", "Custom Detection"} else "Name:")
        self._field_labels["x"].setText("Ticks:" if step_type == "Zoom Out" else ("Region1 X:" if is_logic else ("Start X:" if is_drag else "X:")))
        self._field_labels["y"].setText("Region1 Y:" if is_logic else "Y:")
        self._field_labels["end_x"].setText("Region2 X:" if is_logic else "End X:")
        self._field_labels["end_y"].setText("Region2 Y:" if is_logic else "End Y:")
        self.position_button.setText("Select Region" if is_logic else "Set Position")
        self._set_visibility("label", not advanced)
        self._set_visibility("x", has_point or step_type == "Zoom Out")
        self._set_visibility("y", has_point)
        self._set_visibility("end_x", is_drag or is_logic)
        self._set_visibility("end_y", is_drag or is_logic)
        self._set_visibility("drag_ms", is_drag)
        self._set_visibility("on_true", not advanced)
        self._field_labels["on_true"].setText("On True ->" if is_logic else "Then Go To ->")
        self._set_visibility("on_false", is_logic and not advanced)
        self._set_visibility("fallback_enabled", is_logic)
        self._set_visibility("fallback_max", is_logic)
        self._set_visibility("fallback_screen", is_logic)
        self._set_visibility("advanced", is_custom)
        self._set_visibility("outcomes", advanced)
        self._set_visibility("position", has_point)
        self._set_visibility("test_ocr", is_logic)
        self.show_position_button.setVisible(has_point)
        self.show_end_position_button.setVisible(is_drag or is_logic)
        self.options_box.setVisible(step_type == "Option Select")
        self.step_fallback_max.setEnabled(is_logic and self.step_fallback_enabled.isChecked())
        self.step_fallback_screen.setEnabled(is_logic and self.step_fallback_enabled.isChecked())

    def _reset_step_editor(self) -> None:
        with QSignalBlocker(self.step_type):
            self.step_type.setCurrentText("Button Click")
        self.step_label.clear()
        for field in (self.step_x, self.step_y, self.step_end_x, self.step_end_y, self.step_seconds):
            field.setValue(0)
        self.step_drag_ms.setValue(500)
        self.step_once.setChecked(False)
        self._set_combo(self.step_on_true, "(continue)", "(continue)")
        self._set_combo(self.step_on_false, "(continue)", "(continue)")
        self.step_fallback_enabled.setChecked(False)
        self.step_fallback_max.setValue(5)
        self._set_combo(self.step_fallback_screen, "(none)", "(none)")
        self.step_advanced.setChecked(False)
        self._editing_outcomes_raw = ""
        self._update_field_visibility()

    def _load_step(self, step: StepConfig) -> None:
        self._set_combo(self.step_type, step.type, "Button Click")
        self.step_label.setText(step.label)
        self.step_x.setValue(step.x)
        self.step_y.setValue(step.y)
        self.step_end_x.setValue(step.end_x)
        self.step_end_y.setValue(step.end_y)
        self.step_drag_ms.setValue(step.drag_ms)
        self.step_seconds.setValue(step.seconds)
        self.step_once.setChecked(step.once_per_cycle)
        self._set_combo(self.step_on_true, step.on_true_screen, "(continue)")
        self._set_combo(self.step_on_false, step.on_false_screen, "(continue)")
        self.step_fallback_enabled.setChecked(step.fallback_enabled)
        self.step_fallback_max.setValue(step.fallback_max_attempts)
        self._set_combo(self.step_fallback_screen, step.fallback_screen, "(none)")
        self.step_advanced.setChecked(step.advanced)
        self._editing_outcomes_raw = step.outcomes_raw
        self._update_field_visibility()

    def _load_options(self, options: list[OptionConfig]) -> None:
        for option, widgets in zip(options, self.option_widgets):
            widgets["name"].setText(option.name)  # type: ignore[attr-defined]
            widgets["x"].setValue(option.x)  # type: ignore[attr-defined]
            widgets["y"].setValue(option.y)  # type: ignore[attr-defined]
            widgets["available"].setChecked(option.available)  # type: ignore[attr-defined]
            widgets["priority"].setValue(option.priority)  # type: ignore[attr-defined]
            widgets["max_uses"].setValue(option.max_uses)  # type: ignore[attr-defined]

    def _write_options_from_editor(self) -> None:
        if self._options is None:
            return
        for option, widgets in zip(self._options, self.option_widgets):
            option.name = widgets["name"].text()  # type: ignore[attr-defined]
            option.x = widgets["x"].value()  # type: ignore[attr-defined]
            option.y = widgets["y"].value()  # type: ignore[attr-defined]
            option.available = widgets["available"].isChecked()  # type: ignore[attr-defined]
            option.priority = widgets["priority"].value()  # type: ignore[attr-defined]
            option.max_uses = widgets["max_uses"].value()  # type: ignore[attr-defined]

    def _step_from_editor(self) -> StepConfig:
        step_type = self.step_type.currentText()
        is_logic = step_type in LOGIC_STEP_TYPES
        advanced = step_type == "Custom Detection" and self.step_advanced.isChecked()
        return StepConfig(
            type=step_type, label=self.step_label.text(), x=self.step_x.value(), y=self.step_y.value(),
            end_x=self.step_end_x.value(), end_y=self.step_end_y.value(), drag_ms=self.step_drag_ms.value(),
            once_per_cycle=self.step_once.isChecked(), seconds=self.step_seconds.value(),
            on_true_screen=self.step_on_true.currentText(),
            on_false_screen=self.step_on_false.currentText() if is_logic else "(continue)",
            fallback_enabled=is_logic and self.step_fallback_enabled.isChecked(),
            fallback_max_attempts=self.step_fallback_max.value(),
            fallback_screen=self.step_fallback_screen.currentText(), advanced=advanced,
            outcomes_raw=self._editing_outcomes_raw if advanced else "",
        )

    def _save(self) -> None:
        self._write_options_from_editor()
        self.saved.emit(self._step_from_editor())
        self.accept()

    def reject(self) -> None:
        """Treat the title-bar close button exactly like Cancel."""
        self.done(QDialog.DialogCode.Rejected)

    def _edit_outcomes(self) -> None:
        # Deliberately no Qt parent: see make_independently_minimizable in app/widgets.py -
        # a parented QDialog becomes a native Windows "owned window" that minimizes together
        # with its owner, which is exactly what this window must not do.
        dialog = self._new_outcomes_dialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._editing_outcomes_raw = dialog.result_outcomes_raw

    def _open_outcomes_for_search(self) -> None:
        """Open the outcomes dialog without blocking search-result navigation."""
        dialog = self._new_outcomes_dialog()
        self._advanced_outcomes_window = dialog
        dialog.accepted.connect(lambda: setattr(self, "_editing_outcomes_raw", dialog.result_outcomes_raw))
        dialog.finished.connect(lambda *_: setattr(self, "_advanced_outcomes_window", None))
        dialog.open()

    def _new_outcomes_dialog(self) -> AdvancedOutcomesWindow:
        return AdvancedOutcomesWindow(self._editing_outcomes_raw, self._screen_names)

    def _open_option_availability(self, index: int) -> None:
        if self._options is None:
            return
        self.option_availability_window.set_target(index, self._options)
        self.option_availability_window.open()

    def _capture_position(self) -> None:
        is_region = self.step_type.currentText() in LOGIC_STEP_TYPES
        try:
            captured = capture_region(self.client, self) if is_region else capture_point(self.client, self)
        except Exception as error:
            self._message(f"Capture failed: {error}")
            return
        if captured is None:
            self._message("Capture cancelled.")
            return
        if is_region:
            x1, y1, x2, y2 = captured
            self.step_x.setValue(x1)
            self.step_y.setValue(y1)
            self.step_end_x.setValue(x2)
            self.step_end_y.setValue(y2)
        else:
            x, y = captured
            self.step_x.setValue(x)
            self.step_y.setValue(y)

    def _test_ocr(self) -> None:
        self.test_ocr_button.setEnabled(False)
        try:
            try:
                ack = self.client.send_command(
                    VERB_TEST_OCR,
                    ocr_test_payload(
                        self.step_x.value(), self.step_y.value(),
                        self.step_end_x.value(), self.step_end_y.value(),
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
            self._message(f"OCR result: {ack.data.get('text', '')}")
        finally:
            self.test_ocr_button.setEnabled(True)

    def _show_position(self) -> None:
        self._show_point_preview(self.step_x.value(), self.step_y.value())

    def _show_end_position(self) -> None:
        self._show_point_preview(self.step_end_x.value(), self.step_end_y.value())

    def _show_option_position(self, index: int) -> None:
        self._show_point_preview(
            self.option_widgets[index]["x"].value(), self.option_widgets[index]["y"].value(),
        )

    def _show_point_preview(self, x: float, y: float) -> None:
        try:
            ack = self.client.send_command(VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(x, y))
        except IpcTimeoutError:
            self._message("SHOW_POINT_PREVIEW: timed out, outcome unknown. Check status before retrying.")
            return
        except IpcBusyError as error:
            self._message(f"SHOW_POINT_PREVIEW: not sent ({error})")
            return
        except Exception as error:
            self._message(f"SHOW_POINT_PREVIEW: failed ({error})")
            return
        result = "OK" if ack.ok else "failed"
        self._message(f"SHOW_POINT_PREVIEW: {result} ({ack.message or result})")

    def _message(self, text: str) -> None:
        self.status_label.setText(text)
