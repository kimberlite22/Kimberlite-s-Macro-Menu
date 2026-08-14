"""Non-modal editor for one preset step."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QGridLayout,
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from app.advanced_outcomes_window import AdvancedOutcomesWindow, parse_outcomes
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
from ipc.config_reader import AdvancedStep, OptionConfig, StepConfig
from ipc.protocol import (
    OCR_TEST_SOURCE_MAPS,
    OCR_TEST_SOURCE_OUTCOMES,
    OCR_TEST_SOURCE_TEXT,
    OcrTestResult,
    VERB_GET_OCR_SAMPLE,
    VERB_SAVE_OCR_SAMPLE,
    VERB_SET_OCR_SAMPLE,
    VERB_SHOW_POINT_PREVIEW,
    VERB_TEST_OCR,
    format_ocr_test_result,
    get_ocr_sample_payload,
    ocr_test_payload,
    save_ocr_sample_payload,
    set_ocr_sample_payload,
    show_point_preview_payload,
)


STEP_TYPES = [
    "Start", "Option Select", "Button Click", "Press Start Button",
    "Restart Stage Button", "Camera Setup", "Place Towers", "Drag", "Zoom Out",
    "Key Press", "Wait", "Detect Map", "Round End Detection", "Ingame Detection",
    "Custom Detection",
]
LOGIC_STEP_TYPES = {"Detect Map", "Round End Detection", "Ingame Detection", "Custom Detection"}
POINT_STEP_TYPES = {"Button Click", "Press Start Button", "Restart Stage Button"}

# A "Key Press" step's Hold Until choice meaning "no target step, just use the hold time".
# ``HoldUntilNoneChoice()`` in tower_defense_macro_gui.ahk holds the same literal - the engine has
# to recognize it, because it is what a saved config carries for a step with no target.
HOLD_UNTIL_NONE = "(hold duration)"


def hold_until_choice(index: int, step: StepConfig) -> str:
    """The Hold Until entry for the step at 1-based `index`, e.g. "3. Click Button".

    Both halves are deliberate, and the engine parses both back out
    (``ResolveHoldUntilStepIndex``). Steps have no stable identity of their own, so the name is what
    survives the user reordering the screen afterwards, and the position is all a step whose Name
    field is empty ever had to be identified by.
    """
    return f"{index}. {step.label.strip() or step.type}"


def _hold_until_position(choice: str) -> int | None:
    """The 1-based position a Hold Until entry names, or None when it names none.

    The engine's own ``ResolveHoldUntilStepIndex`` reads the same leading number, and prefers a
    matching step Name over it; this is only used to warn about an obviously earlier target, where
    the number is the half that answers the question.
    """
    head = choice.split(".", 1)[0].strip()
    return int(head) if head.isdigit() else None


class StepEditWindow(QDialog):
    """Keep one step edit local until Save emits a replacement StepConfig."""

    saved = Signal(object)

    def __init__(self, client: Any, parent: QWidget | None = None, *, map_action_mode: bool = False) -> None:
        super().__init__(parent)
        make_independently_minimizable(self)
        self.client = client
        self._map_action_mode = map_action_mode
        self._screen_names: list[str] = []
        self._sibling_steps: list[StepConfig] = []
        self._editing_step: StepConfig | None = None
        self._editing_outcomes_raw = ""
        self._advanced_outcomes_window: AdvancedOutcomesWindow | None = None
        self._options: list[OptionConfig] | None = None
        self.setWindowTitle("Map Action Editor" if self._map_action_mode else "Step Editor")
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
        self.step_type.addItems(["Drag", "Zoom Out"] if self._map_action_mode else STEP_TYPES)
        self.step_label = QLineEdit()
        self.step_label.setObjectName("step_label")
        self.step_x = self._number("step_x")
        self.step_y = self._number("step_y")
        self.step_end_x = self._number("step_end_x")
        self.step_end_y = self._number("step_end_y")
        self.step_drag_ms = self._integer("step_drag_ms", 0, 600000)
        self.step_seconds = self._number("step_seconds")
        self.step_key = QLineEdit()
        self.step_key.setObjectName("step_key")
        self.step_key.setToolTip(
            "One key name in AutoHotkey notation, without the braces: e, 5, Space, Enter, F1, "
            "LShift. Not a sequence of keys - a sequence could not be held down as a unit."
        )
        self.step_hold_ms = self._integer("step_hold_ms", 0, 600000)
        self.step_hold_async = QCheckBox("Go to next step while holding")
        self.step_hold_async.setObjectName("step_hold_async")
        self.step_hold_async.setToolTip(
            "Press the key and move on immediately instead of waiting out the hold. The key is "
            "released once the hold time is up, whatever step the macro has reached by then."
        )
        self.step_hold_until = NoScrollComboBox()
        self.step_hold_until.setObjectName("step_hold_until")
        self.step_hold_until.setToolTip(
            "Hold the key until the chosen step of this screen has finished, instead of for a "
            "fixed time. The macro always continues to the next step while holding, because the "
            "step that ends the hold is a later one. A hold time is then an upper limit."
        )
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
        self.set_end_position_button = QPushButton("Set End Position")
        self.set_end_position_button.setObjectName("step_set_end_position_button")
        self.test_ocr_button = QPushButton("Test OCR")
        self.test_ocr_button.setObjectName("step_test_ocr_button")
        self.save_sample_button = QPushButton("Save Sample")
        self.save_sample_button.setObjectName("step_save_sample_button")
        self.save_sample_button.setToolTip(
            "Save a screenshot of this region as the sample for this expected text. "
            "Detections that use the same expected text share it."
        )
        self.choose_sample_button = QPushButton("Choose Sample...")
        self.choose_sample_button.setObjectName("step_choose_sample_button")
        self.choose_sample_button.setToolTip(
            "Pick a different picture to use as this expected text's sample."
        )
        self.show_position_button = QPushButton("Show")
        self.show_position_button.setObjectName("step_show_position_button")
        self.show_end_position_button = QPushButton("Show")
        self.show_end_position_button.setObjectName("step_show_end_position_button")
        show_positions = QWidget()
        show_positions_layout = QHBoxLayout(show_positions)
        show_positions_layout.setContentsMargins(0, 0, 0, 0)
        show_positions_layout.addWidget(self.show_position_button)
        show_positions_layout.addWidget(self.show_end_position_button)
        ocr_actions = QWidget()
        ocr_actions_layout = QHBoxLayout(ocr_actions)
        ocr_actions_layout.setContentsMargins(0, 0, 0, 0)
        ocr_actions_layout.addWidget(self.test_ocr_button)
        ocr_actions_layout.addWidget(self.save_sample_button)
        ocr_actions_layout.addWidget(self.choose_sample_button)

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
        self._add_editor_row(editor, 4, "key", "Key", self.step_key)
        self._add_editor_row(editor, 4, "hold_ms", "Hold", self.step_hold_ms, 2)
        self._field_labels["hold_ms"].setToolTip("Measured in milliseconds. 0 = a plain key press.")
        self._field_widgets["hold_ms"].setToolTip("Measured in milliseconds. 0 = a plain key press.")
        self._add_editor_row(editor, 5, "hold_until", "Hold Until", self.step_hold_until)
        self._add_editor_row(editor, 5, "hold_async", "", self.step_hold_async, 2)
        self._add_editor_row(editor, 6, "on_true", "Then Go To ->", self.step_on_true)
        self._add_editor_row(editor, 6, "on_false", "On False ->", self.step_on_false, 2)
        self._add_editor_row(editor, 7, "fallback_enabled", "Fallback after N attempts", self.step_fallback_enabled)
        self._add_editor_row(editor, 7, "fallback_max", "Max attempts", self.step_fallback_max, 2)
        self._add_editor_row(editor, 8, "fallback_screen", "Fallback Screen ->", self.step_fallback_screen)
        self._add_editor_row(editor, 8, "advanced", "Advanced Detection", self.step_advanced, 2)
        self._add_editor_row(editor, 9, "position", "", self.position_button)
        self._add_editor_row(editor, 9, "end_position", "", self.set_end_position_button, 2)
        self._add_editor_row(editor, 10, "outcomes", "", self.outcomes_button)
        self._add_editor_row(editor, 10, "test_ocr", "", ocr_actions, 2)
        self._add_editor_row(editor, 11, "show_positions", "", show_positions)
        editor.addWidget(self.step_once, 12, 0, 1, 4)

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
        # The OCR test result is a full sentence quoting both the expected and the recognized text,
        # so without wrapping it would stretch the dialog to whatever the game happened to display.
        self.status_label.setWordWrap(True)
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
        self.step_hold_until.currentTextChanged.connect(self._update_field_visibility)
        self.step_hold_until.currentTextChanged.connect(self._warn_about_an_earlier_hold_until)
        self.outcomes_button.clicked.connect(self._edit_outcomes)
        self.position_button.clicked.connect(lambda: self._capture_position())
        self.set_end_position_button.clicked.connect(
            lambda: self._capture_position(target_x=self.step_end_x, target_y=self.step_end_y),
        )
        self.test_ocr_button.clicked.connect(self._test_ocr)
        self.save_sample_button.clicked.connect(self._save_ocr_sample)
        self.choose_sample_button.clicked.connect(self._choose_ocr_sample)
        self.show_position_button.clicked.connect(self._show_position)
        self.show_end_position_button.clicked.connect(self._show_end_position)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self._reset_step_editor()

    def open_for(
        self, step: StepConfig | None, screen_names: list[str], options: list[OptionConfig],
        sibling_steps: list[StepConfig] | None = None,
    ) -> None:
        """Load an existing step or empty fields, and refresh explicit screen choices.

        ``sibling_steps`` is the screen's own step list, which a "Key Press" step's Hold Until
        choices are built from. The step being edited is identified inside it by identity, so it can
        be left out of its own choices; a brand new step is simply not in the list yet.
        """
        self._sibling_steps = list(sibling_steps or [])
        self._editing_step = step
        self._refresh_hold_until_choices()
        self.set_screen_names(screen_names)
        self._options = options
        self._load_options(options)
        if step is None:
            self._reset_step_editor()
        else:
            self._load_step(step)

    def open_for_map_action(self, step: AdvancedStep | None) -> None:
        """Load one map action without requiring preset-only data."""
        self._options = None
        if step is None:
            self._reset_step_editor()
            return
        self._load_step(StepConfig(
            type=step.type, x=step.x, y=step.y, end_x=step.end_x, end_y=step.end_y,
            drag_ms=step.drag_ms,
        ))

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

    def _warn_about_an_earlier_hold_until(self, *args: Any) -> None:
        """Say so when the chosen target step runs BEFORE this one.

        The engine handles it (the hold then simply ends with the screen, and it logs why), but from
        the combo alone the choice looks like any other, and the difference only shows up as a key
        held far longer than intended. The choice is left available rather than filtered out: which
        step comes first is a question of step order, which the user can still change afterwards.
        """
        own_index = next(
            (index for index, step in enumerate(self._sibling_steps, start=1) if step is self._editing_step),
            None,
        )
        target_index = self._resolve_hold_until_index(self.step_hold_until.currentText())
        if own_index is not None and target_index is not None and target_index < own_index:
            self._message(
                "That step runs before this one, so the key would stay held until the screen ends. "
                "Move this step above it, or pick a later one."
            )

    def _resolve_hold_until_index(self, choice: str) -> int | None:
        """Which step the engine would actually wait for: by Name first, then by position.

        A mirror of ``ResolveHoldUntilStepIndex`` in macro/held_keys.ahk, and it has to stay one. A
        stored choice can outlive the step order it was written against (see _set_hold_until), so a
        warning that read only the position would point at a different step than the one the engine
        waits for, which is the exact confusion the warning exists to prevent.
        """
        text = choice.strip()
        if not text or text == HOLD_UNTIL_NONE:
            return None
        position = _hold_until_position(text)
        name = text.split(".", 1)[1].strip() if position is not None else text
        for index, step in enumerate(self._sibling_steps, start=1):
            if step is self._editing_step or not step.label.strip():
                continue
            if step.label.strip().casefold() == name.casefold():
                return index
        if position is not None and 1 <= position <= len(self._sibling_steps):
            if self._sibling_steps[position - 1] is not self._editing_step:
                return position
        return None

    def _refresh_hold_until_choices(self) -> None:
        """Rebuild the Hold Until combo from the screen's steps, minus the one being edited.

        A step cannot wait for itself: it is what presses the key, so its own completion could only
        ever come after the release, never before it.
        """
        choices = [HOLD_UNTIL_NONE] + [
            hold_until_choice(index, step)
            for index, step in enumerate(self._sibling_steps, start=1)
            if step is not self._editing_step
        ]
        self._replace_combo(self.step_hold_until, choices, HOLD_UNTIL_NONE)

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
        is_key_press = step_type == "Key Press"
        advanced = is_custom and self.step_advanced.isChecked()
        has_point = step_type in POINT_STEP_TYPES or is_drag or is_logic
        holds_until_step = is_key_press and self.step_hold_until.currentText() not in {"", HOLD_UNTIL_NONE}
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
        self._set_visibility("key", is_key_press)
        self._set_visibility("hold_ms", is_key_press)
        self._set_visibility("hold_until", is_key_press)
        self._set_visibility("hold_async", is_key_press)
        # With a target step chosen there is nothing left for either control to decide: continuing
        # is forced (the step that ends the hold is a later one, so blocking here would mean it
        # never runs), and the hold time degrades to a mere upper limit.
        self._field_labels["hold_ms"].setText("Max hold" if holds_until_step else "Hold")
        self.step_hold_async.setEnabled(not holds_until_step)
        if holds_until_step:
            with QSignalBlocker(self.step_hold_async):
                self.step_hold_async.setChecked(True)
        self._set_visibility("on_true", not advanced)
        self._field_labels["on_true"].setText("On True ->" if is_logic else "Then Go To ->")
        self._set_visibility("on_false", is_logic and not advanced)
        self._set_visibility("fallback_enabled", is_logic)
        self._set_visibility("fallback_max", is_logic)
        self._set_visibility("fallback_screen", is_logic)
        self._set_visibility("advanced", is_custom)
        self._set_visibility("outcomes", advanced)
        self._set_visibility("position", has_point)
        self._set_visibility("end_position", is_drag)
        self._set_visibility("test_ocr", is_logic)
        self.test_ocr_button.setVisible(is_logic)
        # A sample is filed under the expected text, so the buttons only make sense on the steps
        # whose Name field IS that expected text. "Detect Map" matches against the map profiles'
        # own expected texts and an Advanced Detection against its outcome names, so on those two a
        # sample saved here would be filed under a key no matcher ever looks up. Samples for them
        # belong next to the fields that really hold their expected text (the map profile window
        # and the advanced outcomes window), which is tracked as its own task.
        step_label_is_expected_text = is_logic and step_type != "Detect Map" and not advanced
        self.save_sample_button.setVisible(step_label_is_expected_text)
        self.choose_sample_button.setVisible(step_label_is_expected_text)
        self.show_position_button.setVisible(has_point)
        self.show_end_position_button.setVisible(is_drag or is_logic)
        self.options_box.setVisible(step_type == "Option Select")
        self.step_fallback_max.setEnabled(is_logic and self.step_fallback_enabled.isChecked())
        self.step_fallback_screen.setEnabled(is_logic and self.step_fallback_enabled.isChecked())
        if self._map_action_mode:
            for key in (
                "label", "seconds", "on_true", "on_false", "fallback_enabled", "fallback_max",
                "fallback_screen", "advanced", "outcomes", "test_ocr",
                "key", "hold_ms", "hold_until", "hold_async",
            ):
                self._set_visibility(key, False)
            self.step_once.setVisible(False)
            self.options_box.setVisible(False)

    def _reset_step_editor(self) -> None:
        with QSignalBlocker(self.step_type):
            self.step_type.setCurrentText("Drag" if self._map_action_mode else "Button Click")
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
        self.step_key.clear()
        self.step_hold_ms.setValue(0)
        self.step_hold_async.setChecked(False)
        self._set_hold_until("")
        self._editing_outcomes_raw = ""
        self._update_field_visibility()

    def _load_step(self, step: StepConfig) -> None:
        self._set_combo(self.step_type, step.type, "Drag" if self._map_action_mode else "Button Click")
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
        self.step_key.setText(step.key)
        self.step_hold_ms.setValue(step.hold_ms)
        self.step_hold_async.setChecked(step.hold_async)
        self._set_hold_until(step.hold_until_step)
        self._editing_outcomes_raw = step.outcomes_raw
        self._update_field_visibility()

    def _set_hold_until(self, value: str) -> None:
        """Select a stored Hold Until target, keeping one that no longer matches a listed step.

        The listed text is built from the target step's Name and position, so renaming or moving
        that step changes it. Falling back to "(hold duration)" then would let the next Save silently
        delete a target the user never touched, so the stored text is added as its own choice
        instead. The engine resolves it by whichever half of it still fits
        (``ResolveHoldUntilStepIndex``), which is exactly why it stores both.
        """
        text = value.strip()
        if text and text != HOLD_UNTIL_NONE and self.step_hold_until.findText(text) < 0:
            self.step_hold_until.addItem(text)
        self._set_combo(self.step_hold_until, text, HOLD_UNTIL_NONE)

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
        if self._map_action_mode:
            # The caller converts these six shared fields into an AdvancedStep.
            return StepConfig(
                type=step_type, x=self.step_x.value(), y=self.step_y.value(),
                end_x=self.step_end_x.value(), end_y=self.step_end_y.value(),
                drag_ms=self.step_drag_ms.value(), on_true_screen="(continue)",
                on_false_screen="(continue)",
            )
        is_logic = step_type in LOGIC_STEP_TYPES
        advanced = step_type == "Custom Detection" and self.step_advanced.isChecked()
        is_key_press = step_type == "Key Press"
        hold_until = self.step_hold_until.currentText() if is_key_press else ""
        if hold_until == HOLD_UNTIL_NONE:
            hold_until = ""
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
            key=self.step_key.text() if is_key_press else "",
            hold_ms=self.step_hold_ms.value() if is_key_press else 0,
            # A target step forces continuing, so store what actually happens rather than whatever
            # the (then disabled) checkbox happened to be left at.
            hold_async=is_key_press and (bool(hold_until) or self.step_hold_async.isChecked()),
            hold_until_step=hold_until,
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

    def _capture_position(
        self, *, target_x: QDoubleSpinBox | None = None, target_y: QDoubleSpinBox | None = None,
    ) -> None:
        # Keyword-only on purpose: QPushButton.clicked emits a bool, so connecting this method
        # straight to it would bind that bool to the first positional parameter and only fail
        # later, at .setValue() on a bool. Both call sites go through an explicit lambda.
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
            (target_x if target_x is not None else self.step_x).setValue(x)
            (target_y if target_y is not None else self.step_y).setValue(y)

    def _current_outcome_names(self) -> list[str]:
        """The outcome names as they stand right now, dialog edits included.

        _editing_outcomes_raw only catches up when the outcomes dialog is accepted, and that dialog
        can be open non-modally (_open_outcomes_for_search), so this window stays clickable while
        it is. Testing against the raw string in that state would silently match the list as it was
        before the user's edits.
        """
        dialog = self._advanced_outcomes_window
        outcomes = dialog.current_outcomes() if dialog is not None else parse_outcomes(self._editing_outcomes_raw)
        return [outcome.name for outcome in outcomes if outcome.name]

    def _ocr_test_target(self) -> tuple[str, str, list[str], str]:
        """What this step's detection actually compares against: (expected, source, candidates, kind).

        Not every Logic step matches a single expected text, and testing one that does not against
        the Name field answered a question the macro never asks. "Detect Map" matches the map
        profiles' own expected texts, which the engine resolves itself so the button and
        DetectMapProfileInRegion cannot disagree about which profiles exist. An Advanced Detection
        matches its outcome names, which travel with the request because they are being edited here
        and may not be saved to config.ini yet.
        """
        step_type = self.step_type.currentText()
        if step_type == "Detect Map":
            return "", OCR_TEST_SOURCE_MAPS, [], "map profile"
        if step_type == "Custom Detection" and self.step_advanced.isChecked():
            return "", OCR_TEST_SOURCE_OUTCOMES, self._current_outcome_names(), "outcome"
        return self.step_label.text(), OCR_TEST_SOURCE_TEXT, [], ""

    def _test_ocr(self) -> None:
        expected, source, candidates, candidate_kind = self._ocr_test_target()
        self.test_ocr_button.setEnabled(False)
        try:
            try:
                ack = self.client.send_command(
                    VERB_TEST_OCR,
                    ocr_test_payload(
                        self.step_x.value(), self.step_y.value(),
                        self.step_end_x.value(), self.step_end_y.value(),
                        expected, source, candidates,
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
            self._message(format_ocr_test_result(
                OcrTestResult.from_ack_data(ack.data), expected, candidate_kind,
            ))
        finally:
            self.test_ocr_button.setEnabled(True)

    def _save_ocr_sample(self) -> None:
        self.save_sample_button.setEnabled(False)
        try:
            try:
                ack = self.client.send_command(
                    VERB_SAVE_OCR_SAMPLE,
                    save_ocr_sample_payload(
                        self.step_x.value(), self.step_y.value(),
                        self.step_end_x.value(), self.step_end_y.value(),
                        self.step_label.text(),
                    ),
                    timeout=25.0,
                    pump=QApplication.processEvents,
                )
            except IpcTimeoutError:
                self._message("SAVE_OCR_SAMPLE: timed out, outcome unknown. Check status before retrying.")
                return
            except IpcBusyError as error:
                self._message(f"SAVE_OCR_SAMPLE: not sent ({error})")
                return
            except Exception as error:
                self._message(f"SAVE_OCR_SAMPLE: failed ({error})")
                return
            if not ack.ok:
                self._message(f"SAVE_OCR_SAMPLE: failed ({ack.message or 'failed'})")
                return
            self._message(f"OCR sample saved: {ack.data.get('path', '')}")
        finally:
            self.save_sample_button.setEnabled(True)

    def _choose_ocr_sample(self) -> None:
        self.choose_sample_button.setEnabled(False)
        try:
            sample_dir = ""
            try:
                ack = self.client.send_command(
                    VERB_GET_OCR_SAMPLE,
                    get_ocr_sample_payload(self.step_label.text()),
                    timeout=25.0,
                    pump=QApplication.processEvents,
                )
            except IpcTimeoutError:
                self._message("GET_OCR_SAMPLE: timed out, outcome unknown. Check status before retrying.")
            except IpcBusyError as error:
                self._message(f"GET_OCR_SAMPLE: not sent ({error})")
            except Exception as error:
                self._message(f"GET_OCR_SAMPLE: failed ({error})")
            else:
                if not ack.ok:
                    self._message(f"GET_OCR_SAMPLE: failed ({ack.message or 'failed'})")
                else:
                    sample_dir = str(ack.data.get("dir", ""))
            source, _ = QFileDialog.getOpenFileName(
                self,
                "Choose OCR Sample",
                sample_dir,
                "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*)",
            )
            if not source:
                return
            try:
                ack = self.client.send_command(
                    VERB_SET_OCR_SAMPLE,
                    set_ocr_sample_payload(self.step_label.text(), source),
                    timeout=25.0,
                    pump=QApplication.processEvents,
                )
            except IpcTimeoutError:
                self._message("SET_OCR_SAMPLE: timed out, outcome unknown. Check status before retrying.")
                return
            except IpcBusyError as error:
                self._message(f"SET_OCR_SAMPLE: not sent ({error})")
                return
            except Exception as error:
                self._message(f"SET_OCR_SAMPLE: failed ({error})")
                return
            if not ack.ok:
                self._message(f"SET_OCR_SAMPLE: failed ({ack.message or 'failed'})")
                return
            self._message(f"OCR sample set: {ack.data.get('path', '')}")
        finally:
            self.choose_sample_button.setEnabled(True)

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
