"""In-memory editor for a complete preset and all of its screens and steps."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.advanced_outcomes_window import AdvancedOutcomesWindow
from app.capture import capture_point, capture_region
from app.option_availability_window import OptionAvailabilityWindow
from app.widgets import NoScrollComboBox, NoScrollDoubleSpinBox, NoScrollSpinBox
from ipc.client import IpcBusyError, IpcTimeoutError
from ipc.config_reader import OptionConfig, PresetConfig, ScreenConfig, StepConfig
from ipc.protocol import (
    OptionPayload,
    ScreenPayload,
    StepPayload,
    VERB_SAVE_PRESET,
    VERB_TEST_OCR,
    save_preset_payload,
    ocr_test_payload,
)


STEP_TYPES = [
    "Start", "Option Select", "Button Click", "Press Start Button",
    "Restart Stage Button", "Camera Setup", "Place Towers", "Drag", "Zoom Out",
    "Wait", "Detect Map", "Round End Detection", "Ingame Detection", "Custom Detection",
]
LOGIC_STEP_TYPES = {"Detect Map", "Round End Detection", "Ingame Detection", "Custom Detection"}
POINT_STEP_TYPES = {"Button Click", "Press Start Button", "Restart Stage Button"}
SCREEN_DETECTION_TYPES = ["", "Detect Map", "Round End Detection", "Ingame Detection", "Custom Detection"]
STEP_TABLE_COLUMNS = ["Type", "Label", "X", "Y", "End X", "End Y", "Drag (ms)", "Wait (s)", "Flow"]


class EditPresetWindow(QDialog):
    """Edit a preset locally, then send one complete SAVE_PRESET payload on Save."""

    saved = Signal()

    def __init__(
        self, preset: PresetConfig, client: Any, other_preset_names: list[str],
        map_profile_names: list[str], parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Preset: {preset.name}")
        self.resize(1050, 850)
        self.client = client
        self.other_preset_names = list(other_preset_names)
        self.preset = deepcopy(preset)
        if not self.preset.screens:
            self.preset.screens.append(ScreenConfig(name="Screen 1"))
        self._current_screen_index = 0
        self._build_ui(map_profile_names)
        self.option_availability_window = OptionAvailabilityWindow(self.client, self)
        self._render_screens()
        self._select_screen(0)

    def _build_ui(self, map_profile_names: list[str]) -> None:
        root = QVBoxLayout(self)
        self.editor_scroll_area = QScrollArea()
        self.editor_scroll_area.setObjectName("preset_editor_scroll_area")
        self.editor_scroll_area.setWidgetResizable(True)
        editor_content = QWidget()
        content = QVBoxLayout(editor_content)
        self.editor_scroll_area.setWidget(editor_content)
        root.addWidget(self.editor_scroll_area, 1)

        top = QHBoxLayout()
        content.addLayout(top, 1)

        screen_box = QGroupBox("Screens")
        screen_layout = QVBoxLayout(screen_box)
        self.screen_list = QListWidget()
        self.screen_list.setObjectName("preset_screen_list")
        self.screen_list.currentRowChanged.connect(self._screen_changed)
        screen_layout.addWidget(self.screen_list, 1)
        screen_buttons = QGridLayout()
        self.new_screen_button = QPushButton("New")
        self.rename_screen_button = QPushButton("Rename")
        self.delete_screen_button = QPushButton("Delete")
        self.move_screen_up_button = QPushButton("Move Up")
        self.move_screen_down_button = QPushButton("Move Down")
        for index, button in enumerate((self.new_screen_button, self.rename_screen_button, self.delete_screen_button, self.move_screen_up_button, self.move_screen_down_button)):
            screen_buttons.addWidget(button, index // 2, index % 2)
        screen_layout.addLayout(screen_buttons)
        top.addWidget(screen_box, 1)

        steps_box = QGroupBox("Steps")
        steps_layout = QVBoxLayout(steps_box)
        self.step_list = QTableWidget(0, len(STEP_TABLE_COLUMNS))
        self.step_list.setObjectName("preset_step_list")
        self.step_list.setHorizontalHeaderLabels(STEP_TABLE_COLUMNS)
        self.step_list.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.step_list.horizontalHeader().setStretchLastSection(True)
        self.step_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.step_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.step_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Rows reorder by dragging the row-number header, not the row body: QTableWidget's own
        # internal-move drag-drop swaps cell contents between rows instead of truly moving a row,
        # so it would scramble different fields across rows. Moving the header section instead only
        # ever changes visual<->logical row order, never touches cell contents.
        self.step_list.verticalHeader().setSectionsMovable(True)
        self.step_list.verticalHeader().sectionMoved.connect(self._step_row_moved)
        self.step_list.currentCellChanged.connect(self._step_cell_changed)
        steps_layout.addWidget(self.step_list, 1)
        step_buttons = QHBoxLayout()
        self.add_step_button = QPushButton("Add Step")
        self.update_step_button = QPushButton("Update Selected")
        self.delete_step_button = QPushButton("Delete Selected")
        self.duplicate_step_button = QPushButton("Duplicate")
        for button in (self.add_step_button, self.update_step_button, self.delete_step_button, self.duplicate_step_button):
            step_buttons.addWidget(button)
        steps_layout.addLayout(step_buttons)
        top.addWidget(steps_box, 2)

        screen_detection_box = QGroupBox("Screen Detection")
        screen_detection_form = QFormLayout(screen_detection_box)
        self.screen_detection_type = NoScrollComboBox()
        self.screen_detection_type.setObjectName("screen_detection_type")
        self.screen_detection_type.addItems(SCREEN_DETECTION_TYPES)
        self.screen_detection_x = self._number("screen_detection_x")
        self.screen_detection_y = self._number("screen_detection_y")
        self.screen_detection_end_x = self._number("screen_detection_end_x")
        self.screen_detection_end_y = self._number("screen_detection_end_y")
        self.screen_detection_region_button = QPushButton("Select Detection Region")
        self.screen_detection_region_button.setObjectName("screen_detection_region_button")
        self.screen_detection_text = QLineEdit()
        self.screen_detection_text.setObjectName("screen_detection_text")
        self.screen_default_screen = NoScrollComboBox()
        self.screen_default_screen.setObjectName("screen_default_screen")
        screen_detection_form.addRow("Detection Type:", self.screen_detection_type)
        screen_detection_form.addRow("Region1 X:", self.screen_detection_x)
        screen_detection_form.addRow("Region1 Y:", self.screen_detection_y)
        screen_detection_form.addRow("Region2 X:", self.screen_detection_end_x)
        screen_detection_form.addRow("Region2 Y:", self.screen_detection_end_y)
        screen_detection_form.addRow(self.screen_detection_region_button)
        screen_detection_form.addRow("Expected Text:", self.screen_detection_text)
        screen_detection_form.addRow("Default screen on conflict:", self.screen_default_screen)
        content.addWidget(screen_detection_box)

        editor_box = QGroupBox("Step Editor")
        editor = QGridLayout(editor_box)
        content.addWidget(editor_box)
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
        self.step_fallback_enabled = QCheckBox("Fallback after N attempts")
        self.step_fallback_enabled.setObjectName("step_fallback_enabled")
        self.step_fallback_max = self._integer("step_fallback_max", 0, 99999)
        self.step_fallback_screen = NoScrollComboBox()
        self.step_fallback_screen.setObjectName("step_fallback_screen")
        self.step_advanced = QCheckBox("Advanced Detection")
        self.step_advanced.setObjectName("step_advanced")
        self.outcomes_button = QPushButton("Configure Outcomes...")
        self.outcomes_button.setObjectName("configure_outcomes_button")
        self.position_button = QPushButton("Set Position")
        self.position_button.setObjectName("step_position_button")
        self.test_ocr_button = QPushButton("Test OCR")
        self.test_ocr_button.setObjectName("step_test_ocr_button")

        self._add_editor_row(editor, 0, "type", "Type:", self.step_type)
        self._add_editor_row(editor, 0, "label", "Name:", self.step_label, 2)
        self._add_editor_row(editor, 1, "x", "X:", self.step_x)
        self._add_editor_row(editor, 1, "y", "Y:", self.step_y, 2)
        self._add_editor_row(editor, 2, "end_x", "End X:", self.step_end_x)
        self._add_editor_row(editor, 2, "end_y", "End Y:", self.step_end_y, 2)
        self._add_editor_row(editor, 3, "drag_ms", "Drag (ms):", self.step_drag_ms)
        self._add_editor_row(editor, 3, "seconds", "Wait After (s):", self.step_seconds, 2)
        self._add_editor_row(editor, 4, "on_true", "Then Go To ->", self.step_on_true)
        self._add_editor_row(editor, 4, "on_false", "On False ->", self.step_on_false, 2)
        self._add_editor_row(editor, 5, "fallback_enabled", "", self.step_fallback_enabled)
        self._add_editor_row(editor, 5, "fallback_max", "Max attempts:", self.step_fallback_max, 2)
        self._add_editor_row(editor, 6, "fallback_screen", "Fallback Screen ->", self.step_fallback_screen)
        self._add_editor_row(editor, 6, "advanced", "", self.step_advanced, 2)
        self._add_editor_row(editor, 7, "outcomes", "", self.outcomes_button)
        self._add_editor_row(editor, 7, "position", "", self.position_button, 2)
        self._add_editor_row(editor, 8, "test_ocr", "", self.test_ocr_button)
        editor.addWidget(self.step_once, 9, 0, 1, 4)

        self.options_box = QGroupBox("Challenge options")
        options_layout = QHBoxLayout(self.options_box)
        self.option_widgets: list[dict[str, QWidget]] = []
        options = list(self.preset.options) + [OptionConfig() for _ in range(max(0, 3 - len(self.preset.options)))]
        self._options = options[:3]
        for index, option in enumerate(self._options, 1):
            group = QGroupBox(f"Option {index}")
            form = QFormLayout(group)
            widgets: dict[str, QWidget] = {
                "name": QLineEdit(option.name), "x": self._number(f"option_{index}_x"),
                "y": self._number(f"option_{index}_y"), "available": QCheckBox(),
                "priority": self._integer(f"option_{index}_priority", 0, 100),
                "max_uses": self._integer(f"option_{index}_max_uses", 0, 99999),
            }
            widgets["availability"] = QPushButton("Availability Check...")
            widgets["availability"].setObjectName(f"option_{index}_availability_button")
            widgets["x"].setValue(option.x)  # type: ignore[attr-defined]
            widgets["y"].setValue(option.y)  # type: ignore[attr-defined]
            widgets["available"].setChecked(option.available)  # type: ignore[attr-defined]
            widgets["priority"].setValue(option.priority)  # type: ignore[attr-defined]
            widgets["max_uses"].setValue(option.max_uses)  # type: ignore[attr-defined]
            form.addRow("Name:", widgets["name"])
            form.addRow("X:", widgets["x"])
            form.addRow("Y:", widgets["y"])
            form.addRow("Available at start:", widgets["available"])
            form.addRow("Priority:", widgets["priority"])
            form.addRow("Max uses:", widgets["max_uses"])
            form.addRow(widgets["availability"])
            widgets["availability"].clicked.connect(lambda checked=False, option_index=index - 1: self._open_option_availability(option_index))  # type: ignore[attr-defined]
            options_layout.addWidget(group)
            self.option_widgets.append(widgets)
        content.addWidget(self.options_box)

        self.option_select_box = QGroupBox("Option Select and default map")
        preset_form = QFormLayout(self.option_select_box)
        self.default_map = NoScrollComboBox()
        self.default_map.setObjectName("preset_default_map")
        self.default_map.addItems(["(none)", *map_profile_names])
        self._set_combo(self.default_map, self.preset.default_map, "(none)")
        self.back_x = self._number("preset_back_x")
        self.back_y = self._number("preset_back_y")
        self.back_x.setValue(self.preset.back_x)
        self.back_y.setValue(self.preset.back_y)
        self.preset_fallback_screen = NoScrollComboBox()
        self.preset_fallback_screen.setObjectName("preset_fallback_screen")
        # _refresh_targets() (called later, from _render_screens()) repopulates this combo but only
        # PRESERVES whatever's already selected - it has no idea what the preset's real saved
        # fallback screen was. Seed real items + the real selection here, at construction time,
        # before that first _refresh_targets() call, or _set_combo would find no items yet (an empty
        # combo), silently fall back to "(none)", and _refresh_targets() would then "preserve" that
        # wrong value forever - silently clearing every preset's fallback screen on the next Save.
        initial_fallback_items = ["(none)", "(Stop Macro)", *[screen.name for screen in self.preset.screens]]
        self.preset_fallback_screen.addItems(initial_fallback_items)
        self._set_combo(self.preset_fallback_screen, self.preset.fallback_screen, "(none)")
        preset_form.addRow("Default Map:", self.default_map)
        preset_form.addRow("Back X:", self.back_x)
        preset_form.addRow("Back Y:", self.back_y)
        preset_form.addRow("Fallback Screen ->", self.preset_fallback_screen)
        content.addWidget(self.option_select_box)

        footer = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setObjectName("edit_preset_status")
        self.save_button = QPushButton("Save")
        self.close_button = QPushButton("Close")
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.save_button)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        self.new_screen_button.clicked.connect(self._new_screen)
        self.rename_screen_button.clicked.connect(self._rename_screen)
        self.delete_screen_button.clicked.connect(self._delete_screen)
        self.move_screen_up_button.clicked.connect(lambda: self._move_screen(-1))
        self.move_screen_down_button.clicked.connect(lambda: self._move_screen(1))
        self.add_step_button.clicked.connect(self._add_step)
        self.update_step_button.clicked.connect(self._update_step)
        self.delete_step_button.clicked.connect(self._delete_step)
        self.duplicate_step_button.clicked.connect(self._duplicate_step)
        self.step_type.currentTextChanged.connect(self._update_field_visibility)
        self.step_advanced.toggled.connect(self._update_field_visibility)
        self.step_fallback_enabled.toggled.connect(self._update_field_visibility)
        self.outcomes_button.clicked.connect(self._edit_outcomes)
        self.position_button.clicked.connect(self._capture_position)
        self.screen_detection_region_button.clicked.connect(self._capture_screen_detection_region)
        self.test_ocr_button.clicked.connect(self._test_ocr)
        self.save_button.clicked.connect(self._save)
        self.close_button.clicked.connect(self.close)
        self.screen_detection_type.currentTextChanged.connect(self._save_screen_detection)
        self.screen_detection_x.valueChanged.connect(self._save_screen_detection)
        self.screen_detection_y.valueChanged.connect(self._save_screen_detection)
        self.screen_detection_end_x.valueChanged.connect(self._save_screen_detection)
        self.screen_detection_end_y.valueChanged.connect(self._save_screen_detection)
        self.screen_detection_text.textChanged.connect(self._save_screen_detection)
        self.screen_default_screen.currentTextChanged.connect(self._save_screen_detection)
        self._reset_step_editor()

    def _add_editor_row(self, grid: QGridLayout, row: int, key: str, label: str, widget: QWidget, column: int = 0) -> None:
        field_label = QLabel(label)
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

    @property
    def _current_screen(self) -> ScreenConfig:
        return self.preset.screens[self._current_screen_index]

    def _render_screens(self) -> None:
        current = self._current_screen_index
        with QSignalBlocker(self.screen_list):
            self.screen_list.clear()
            self.screen_list.addItems([screen.name for screen in self.preset.screens])
        self._refresh_targets()
        if self.preset.screens:
            self.screen_list.setCurrentRow(min(current, len(self.preset.screens) - 1))

    def _select_screen(self, index: int) -> None:
        self._current_screen_index = index
        self.screen_list.setCurrentRow(index)
        self._load_screen_detection()
        self._render_steps()

    def _screen_changed(self, row: int) -> None:
        if not 0 <= row < len(self.preset.screens):
            return
        self._current_screen_index = row
        self._load_screen_detection()
        self._render_steps()

    def _render_steps(self, select_row: int | None = None) -> None:
        with QSignalBlocker(self.step_list):
            self.step_list.setRowCount(0)
            self.step_list.setRowCount(len(self._current_screen.steps))
            for row, step in enumerate(self._current_screen.steps):
                for column, text in enumerate(self._step_row_texts(step)):
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, step)
                    self.step_list.setItem(row, column, item)
        if select_row is not None and 0 <= select_row < len(self._current_screen.steps):
            self.step_list.setCurrentCell(select_row, 0)
        else:
            self._reset_step_editor()

    @staticmethod
    def _step_row_texts(step: StepConfig) -> list[str]:
        is_drag = step.type == "Drag"
        is_logic = step.type in LOGIC_STEP_TYPES
        is_zoom = step.type == "Zoom Out"
        has_point = step.type in POINT_STEP_TYPES or is_drag or is_logic
        x_text = f"{step.x} ticks" if is_zoom else (str(step.x) if has_point else "")
        y_text = str(step.y) if has_point else ""
        end_x_text = str(step.end_x) if (is_drag or is_logic) else ""
        end_y_text = str(step.end_y) if (is_drag or is_logic) else ""
        drag_ms_text = str(step.drag_ms) if is_drag else ""
        wait_text = f"{step.seconds}s" if step.seconds else ""
        flow_parts: list[str] = []
        if is_logic:
            if step.type == "Custom Detection" and step.advanced:
                flow_parts.append("advanced")
            else:
                flow_parts.append(f"true: {step.on_true_screen or '(continue)'}")
                flow_parts.append(f"false: {step.on_false_screen or '(continue)'}")
            if step.fallback_enabled:
                flow_parts.append(f"fallback after {step.fallback_max_attempts}: {step.fallback_screen or '(none)'}")
        elif step.on_true_screen and step.on_true_screen != "(continue)":
            flow_parts.append(f"-> {step.on_true_screen}")
        return [step.type, step.label, x_text, y_text, end_x_text, end_y_text, drag_ms_text, wait_text, "; ".join(flow_parts)]

    def _step_selected(self, row: int) -> None:
        if 0 <= row < len(self._current_screen.steps):
            self._load_step(self._current_screen.steps[row])

    def _step_cell_changed(self, current_row: int, current_column: int, previous_row: int, previous_column: int) -> None:
        self._step_selected(current_row)

    def _sync_steps_order(self) -> None:
        header = self.step_list.verticalHeader()
        self._current_screen.steps = [
            self.step_list.item(header.logicalIndex(visual), 0).data(Qt.ItemDataRole.UserRole)
            for visual in range(self.step_list.rowCount())
        ]

    def _step_row_moved(self, *args: Any) -> None:
        current_row = self.step_list.currentRow()
        selected_step = self.step_list.item(current_row, 0).data(Qt.ItemDataRole.UserRole) if current_row >= 0 else None
        self._sync_steps_order()
        select_row = next((index for index, step in enumerate(self._current_screen.steps) if step is selected_step), None)
        self._render_steps(select_row)

    def _refresh_targets(self) -> None:
        screen_names = [screen.name for screen in self.preset.screens]
        self._replace_combo(self.step_on_true, ["(continue)", "(Repeat)", *screen_names], "(continue)")
        self._replace_combo(self.step_on_false, ["(continue)", "(Repeat)", *screen_names], "(continue)")
        fallback_items = ["(none)", "(Stop Macro)", *screen_names]
        self._replace_combo(self.step_fallback_screen, fallback_items, "(none)")
        self._replace_combo(self.preset_fallback_screen, fallback_items, "(none)")
        self._replace_combo(self.screen_default_screen, ["", *screen_names], "")

    def _load_screen_detection(self) -> None:
        screen = self._current_screen
        widgets = (
            self.screen_detection_type, self.screen_detection_x, self.screen_detection_y,
            self.screen_detection_end_x, self.screen_detection_end_y, self.screen_detection_text,
            self.screen_default_screen,
        )
        blockers = [QSignalBlocker(widget) for widget in widgets]
        self._set_combo(self.screen_detection_type, screen.detection_type, "")
        self.screen_detection_x.setValue(screen.detection_x)
        self.screen_detection_y.setValue(screen.detection_y)
        self.screen_detection_end_x.setValue(screen.detection_end_x)
        self.screen_detection_end_y.setValue(screen.detection_end_y)
        self.screen_detection_text.setText(screen.detection_text)
        self._set_combo(self.screen_default_screen, screen.default_screen, "")
        del blockers

    def _save_screen_detection(self, *args: Any) -> None:
        if not 0 <= self._current_screen_index < len(self.preset.screens):
            return
        screen = self._current_screen
        screen.detection_type = self.screen_detection_type.currentText()
        screen.detection_x = self.screen_detection_x.value()
        screen.detection_y = self.screen_detection_y.value()
        screen.detection_end_x = self.screen_detection_end_x.value()
        screen.detection_end_y = self.screen_detection_end_y.value()
        screen.detection_text = self.screen_detection_text.text()
        screen.default_screen = self.screen_default_screen.currentText()

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
        self.step_fallback_max.setEnabled(is_logic and self.step_fallback_enabled.isChecked())
        self.step_fallback_screen.setEnabled(is_logic and self.step_fallback_enabled.isChecked())
        option_select = step_type == "Option Select"
        self.options_box.setVisible(option_select)
        self.option_select_box.setVisible(option_select)

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

    def _add_step(self) -> None:
        self._current_screen.steps.append(self._step_from_editor())
        self._render_steps()

    def _update_step(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._current_screen.steps):
            self._message("No step selected.")
            return
        self._current_screen.steps[row] = self._step_from_editor()
        self._render_steps(row)

    def _delete_step(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._current_screen.steps):
            return
        del self._current_screen.steps[row]
        self._render_steps(min(row, len(self._current_screen.steps) - 1))

    def _duplicate_step(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._current_screen.steps):
            self._message("No step selected.")
            return
        self._current_screen.steps.insert(row + 1, deepcopy(self._current_screen.steps[row]))
        self._render_steps(row + 1)

    def _edit_outcomes(self) -> None:
        dialog = AdvancedOutcomesWindow(self._editing_outcomes_raw, [screen.name for screen in self.preset.screens], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._editing_outcomes_raw = dialog.result_outcomes_raw

    def _capture_position(self) -> None:
        # The button relabels itself ("Set Position" / "Select Region", see _update_field_visibility)
        # depending on whether the current step type needs one point or two corners - capture the
        # matching shape rather than always just a point.
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

    def _capture_screen_detection_region(self) -> None:
        try:
            captured = capture_region(self.client, self)
        except Exception as error:
            self._message(f"Capture failed: {error}")
            return
        if captured is None:
            self._message("Capture cancelled.")
            return
        x1, y1, x2, y2 = captured
        self.screen_detection_x.setValue(x1)
        self.screen_detection_y.setValue(y1)
        self.screen_detection_end_x.setValue(x2)
        self.screen_detection_end_y.setValue(y2)

    def _test_ocr(self) -> None:
        # Disabled for the whole call, not just left to the GUI looking unresponsive: pump=... below
        # keeps Qt events flowing during the up-to-~21s wait (cold OCR-server start plus its own
        # response timeout), so a second click during that same wait must not race a fresh TEST_OCR
        # command against the first one's still-pending acknowledgement (single-slot command file).
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

    def _open_option_availability(self, index: int) -> None:
        self.option_availability_window.set_target(index, self._options)
        self.option_availability_window.open()

    def _new_screen(self) -> None:
        name, accepted = QInputDialog.getText(self, "New Screen", "Enter a name for the new screen:")
        name = name.strip()
        if not accepted or not name:
            return
        if any(screen.name == name for screen in self.preset.screens):
            self._message("A screen with this name already exists in this preset.")
            return
        self.preset.screens.append(ScreenConfig(name=name))
        self._current_screen_index = len(self.preset.screens) - 1
        self._render_screens()
        self._render_steps()

    def _rename_screen(self) -> None:
        old_name = self._current_screen.name
        name, accepted = QInputDialog.getText(self, "Rename Screen", f"Rename screen '{old_name}' to:", text=old_name)
        name = name.strip()
        if not accepted or not name or name == old_name:
            return
        if any(screen.name == name for screen in self.preset.screens):
            self._message("A screen with this name already exists in this preset.")
            return
        self._current_screen.name = name
        self._replace_targets(old_name, name, name, name)
        if self.preset.fallback_screen == old_name:
            self.preset.fallback_screen = name
            self._set_combo(self.preset_fallback_screen, name, "(none)")
        self._render_screens()
        row = self.step_list.currentRow()
        if 0 <= row < len(self._current_screen.steps):
            self._load_step(self._current_screen.steps[row])

    def _delete_screen(self) -> None:
        if len(self.preset.screens) <= 1:
            self._message("At least one screen must remain.")
            return
        name = self._current_screen.name
        message = (f"Delete screen '{name}'? Any On True/On False jumps (or Advanced Detection outcomes) "
                   "pointing to it will fall back to '(continue)', and any Logic Fallback Screen "
                   "or default screen pointing to it will be cleared.")
        if QMessageBox.question(self, "Confirm", message) != QMessageBox.StandardButton.Yes:
            return
        del self.preset.screens[self._current_screen_index]
        self._replace_targets(name, "(continue)", "(none)", "")
        if self.preset.fallback_screen == name:
            self.preset.fallback_screen = "(none)"
        self._current_screen_index = min(self._current_screen_index, len(self.preset.screens) - 1)
        self._render_screens()
        self._render_steps()

    def _replace_targets(self, old: str, replacement: str, fallback_replacement: str, default_replacement: str) -> None:
        from app.advanced_outcomes_window import parse_outcomes, serialize_outcomes
        for screen in self.preset.screens:
            for step in screen.steps:
                if step.on_true_screen == old:
                    step.on_true_screen = replacement
                if step.on_false_screen == old:
                    step.on_false_screen = replacement
                if step.fallback_screen == old:
                    step.fallback_screen = fallback_replacement
                if step.outcomes_raw:
                    step.outcomes_raw = serialize_outcomes([
                        outcome if outcome.screen != old else type(outcome)(outcome.name, replacement)
                        for outcome in parse_outcomes(step.outcomes_raw)
                    ])
            if screen.default_screen == old:
                screen.default_screen = default_replacement

    def _move_screen(self, direction: int) -> None:
        target = self._current_screen_index + direction
        if not 0 <= target < len(self.preset.screens):
            return
        self.preset.screens[self._current_screen_index], self.preset.screens[target] = self.preset.screens[target], self.preset.screens[self._current_screen_index]
        self._current_screen_index = target
        self._render_screens()
        self._render_steps()

    def _build_payload(self) -> dict[str, Any]:
        self._sync_steps_order()
        screens = [
            ScreenPayload(
                name=screen.name,
                detection_type=screen.detection_type,
                detection_x=screen.detection_x,
                detection_y=screen.detection_y,
                detection_end_x=screen.detection_end_x,
                detection_end_y=screen.detection_end_y,
                detection_text=screen.detection_text,
                default_screen=screen.default_screen,
                steps=tuple(
                StepPayload(
                    type=step.type, label=step.label, x=step.x, y=step.y,
                    end_x=step.end_x, end_y=step.end_y, drag_ms=step.drag_ms,
                    once_per_cycle=step.once_per_cycle, seconds=step.seconds,
                    on_true_screen=step.on_true_screen, on_false_screen=step.on_false_screen,
                    fallback_enabled=step.fallback_enabled, fallback_max_attempts=step.fallback_max_attempts,
                    fallback_screen=step.fallback_screen, advanced=step.advanced, outcomes_raw=step.outcomes_raw,
                ) for step in screen.steps
            )) for screen in self.preset.screens
        ]
        options: list[OptionPayload] = []
        for config, widgets in zip(self._options, self.option_widgets):
            options.append(OptionPayload(
                name=widgets["name"].text(), x=widgets["x"].value(), y=widgets["y"].value(),
                available=widgets["available"].isChecked(), priority=widgets["priority"].value(),
                max_uses=widgets["max_uses"].value(), det_x=config.det_x, det_y=config.det_y,
                det_end_x=config.det_end_x, det_end_y=config.det_end_y, det_text=config.det_text,
                det_invert=config.det_invert,
            ))
        return save_preset_payload(
            name=self.preset.name, screens=screens, options=options,
            default_map=self.default_map.currentText(), back_x=self.back_x.value(), back_y=self.back_y.value(),
            fallback_screen=self.preset_fallback_screen.currentText(),
        )

    def _save(self) -> None:
        try:
            ack = self.client.send_command(VERB_SAVE_PRESET, self._build_payload())
        except IpcTimeoutError:
            self._message("SAVE_PRESET: timed out, outcome unknown. Check status before retrying.")
            return
        except IpcBusyError as error:
            self._message(f"SAVE_PRESET: not sent ({error})")
            return
        except Exception as error:
            self._message(f"SAVE_PRESET: failed ({error})")
            return
        result = "OK" if ack.ok else "failed"
        self._message(f"SAVE_PRESET: {result} ({ack.message or result})")
        if ack.ok:
            self.saved.emit()

    def _message(self, text: str) -> None:
        self.status_label.setText(text)
