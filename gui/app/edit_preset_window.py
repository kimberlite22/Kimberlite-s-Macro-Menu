"""In-memory editor for a complete preset and all of its screens and steps."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.option_availability_window import OptionAvailabilityWindow
from app.step_edit_window import LOGIC_STEP_TYPES, POINT_STEP_TYPES, StepEditWindow
from app.widgets import (
    NoScrollComboBox,
    NoScrollDoubleSpinBox,
    NoScrollSpinBox,
    make_independently_minimizable,
)
from ipc.config_reader import OptionConfig, PresetConfig, ScreenConfig, StepConfig
from ipc.config_writer import ConfigValidationError
from ipc.protocol import (
    OptionPayload,
    ScreenPayload,
    StepPayload,
    save_preset_payload,
)


STEP_TABLE_COLUMNS = ["Type", "Label", "X", "Y", "End X", "End Y", "Drag", "Wait", "Flow"]


class EditPresetWindow(QDialog):
    """Edit a preset locally, then write the whole preset to config.ini on Save."""

    saved = Signal()

    def __init__(
        self, preset: PresetConfig, client: Any, other_preset_names: list[str],
        map_profile_names: list[str], parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        make_independently_minimizable(self)
        self.setWindowTitle(f"Edit Preset: {preset.name}")
        self.resize(1050, 850)
        self.client = client
        self.other_preset_names = list(other_preset_names)
        self.preset = deepcopy(preset)
        if not self.preset.screens:
            self.preset.screens.append(ScreenConfig(name="Screen 1"))
        self._current_screen_index = 0
        self._step_edit_window: StepEditWindow | None = None
        self._step_edit_target: tuple[ScreenConfig, int | None] | None = None
        self._build_ui(map_profile_names)
        # Deliberately no Qt parent: see make_independently_minimizable in app/widgets.py -
        # a parented QDialog becomes a native Windows "owned window" that minimizes together
        # with its owner, which is exactly what this window must not do.
        self.option_availability_window = OptionAvailabilityWindow(self.client)
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
        self.step_list.horizontalHeaderItem(STEP_TABLE_COLUMNS.index("Drag")).setToolTip(
            "Drag duration, measured in milliseconds."
        )
        self.step_list.horizontalHeaderItem(STEP_TABLE_COLUMNS.index("Wait")).setToolTip(
            "Wait time after the step, measured in seconds."
        )
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
        self.step_list.cellDoubleClicked.connect(self._edit_step_at_row)
        steps_layout.addWidget(self.step_list, 1)
        step_buttons = QHBoxLayout()
        self.add_step_button = QPushButton("Add Step")
        self.edit_step_button = QPushButton("Edit Step...")
        self.delete_step_button = QPushButton("Delete Selected")
        self.duplicate_step_button = QPushButton("Duplicate")
        for button in (self.add_step_button, self.edit_step_button, self.delete_step_button, self.duplicate_step_button):
            step_buttons.addWidget(button)
        steps_layout.addLayout(step_buttons)
        top.addWidget(steps_box, 2)

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
        self.edit_step_button.clicked.connect(self._edit_selected_step)
        self.delete_step_button.clicked.connect(self._delete_step)
        self.duplicate_step_button.clicked.connect(self._duplicate_step)
        self.save_button.clicked.connect(self._save)
        self.close_button.clicked.connect(self.close)

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
        self._render_steps()

    def _screen_changed(self, row: int) -> None:
        if not 0 <= row < len(self.preset.screens):
            return
        self._current_screen_index = row
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
        fallback_items = ["(none)", "(Stop Macro)", *screen_names]
        self._replace_combo(self.preset_fallback_screen, fallback_items, "(none)")
        self._resync_open_step_editor(screen_names)

    def _resync_open_step_editor(self, screen_names: list[str]) -> None:
        window = self._step_edit_window
        if window is None or self._step_edit_target is None:
            return
        target_screen, target_step = self._step_edit_target
        if target_step is None:
            # A brand-new, not-yet-saved step (Add Step) has no persisted screen reference to
            # resync from yet; only the dropdown choices need to stay current.
            window.set_screen_names(screen_names)
            return
        # A screen rename/delete already migrated an EXISTING step's on_true/on_false/fallback
        # (and outcomes_raw) onto the canonical StepConfig via _replace_targets(), which runs
        # before this method (see _rename_screen/_delete_screen). Reload the editor from that
        # already-migrated step instead of merely refreshing combo choices: leaving the editor's
        # stale widget selections in place would let a later Save silently overwrite the just
        # -migrated data with a "(continue)"/"(none)" fallback, since the old screen name the
        # widgets still show would no longer be a valid choice.
        current_index = next(
            (index for index, step in enumerate(target_screen.steps) if step is target_step), None,
        )
        if current_index is None:
            # Either the step was deleted while the editor was open, or (right after this same
            # editor's own Save) it was already replaced by the freshly saved step - either way
            # there is nothing canonical left to reload from; just keep the dropdown choices
            # current and let Save's own "no longer exists" guard handle the deleted case.
            window.set_screen_names(screen_names)
            return
        window.open_for(target_screen.steps[current_index], screen_names)

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

    def _add_step(self) -> None:
        self._open_step_editor(None)

    def _edit_selected_step(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._current_screen.steps):
            self._message("No step selected.")
            return
        self._open_step_editor(row)

    def _edit_step_at_row(self, row: int, _column: int) -> None:
        self._open_step_editor(row)

    def _open_step_editor(self, row: int | None) -> None:
        if row is not None and not 0 <= row < len(self._current_screen.steps):
            return
        # Track the target by the step's own identity, not its row number: the row is only used
        # once, here, to find that object. While this non-modal editor stays open, the user can
        # still reorder/delete/duplicate rows in the (still-interactive) steps table underneath
        # it, which would silently repoint a row-number target at a different step by the time
        # Save runs. An identity reference survives all of that and is looked back up by
        # _save_step_from_editor / _resync_open_step_editor.
        step = self._current_screen.steps[row] if row is not None else None
        self._step_edit_target = (self._current_screen, step)
        window = self._step_edit_window
        if window is None:
            # Deliberately no Qt parent: see make_independently_minimizable in app/widgets.py -
            # a parented QDialog becomes a native Windows "owned window" that minimizes together
            # with its owner, which is exactly what this window must not do.
            window = StepEditWindow(self.client)
            window.saved.connect(self._save_step_from_editor)
            window.finished.connect(self._clear_step_edit_window)
            self._step_edit_window = window
        window.open_for(step, [screen.name for screen in self.preset.screens])
        window.show()
        window.raise_()
        window.activateWindow()

    def _clear_step_edit_window(self, *_: Any) -> None:
        self._step_edit_window = None
        self._step_edit_target = None

    def _save_step_from_editor(self, step: StepConfig) -> None:
        target = self._step_edit_target
        if target is None:
            return
        target_screen, target_step = target
        screen_index = next(
            (index for index, screen in enumerate(self.preset.screens) if screen is target_screen),
            None,
        )
        if screen_index is None:
            self._message("The screen being edited no longer exists.")
            return
        if target_step is None:
            target_screen.steps.append(step)
            row = len(target_screen.steps) - 1
        else:
            row = next(
                (index for index, existing in enumerate(target_screen.steps) if existing is target_step),
                None,
            )
            if row is not None:
                target_screen.steps[row] = step
            else:
                self._message("The step being edited no longer exists.")
                return
        self._current_screen_index = screen_index
        self._render_screens()
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
        self._replace_targets(old_name, name, name)
        if self.preset.fallback_screen == old_name:
            self.preset.fallback_screen = name
            self._set_combo(self.preset_fallback_screen, name, "(none)")
        self._render_screens()

    def _delete_screen(self) -> None:
        if len(self.preset.screens) <= 1:
            self._message("At least one screen must remain.")
            return
        name = self._current_screen.name
        message = (f"Delete screen '{name}'? Any On True/On False jumps (or Advanced Detection outcomes) "
                   "pointing to it will fall back to '(continue)', and any Logic Fallback Screen "
                   "pointing to it will fall back to '(none)'.")
        if QMessageBox.question(self, "Confirm", message) != QMessageBox.StandardButton.Yes:
            return
        del self.preset.screens[self._current_screen_index]
        self._replace_targets(name, "(continue)", "(none)")
        if self.preset.fallback_screen == name:
            self.preset.fallback_screen = "(none)"
        self._current_screen_index = min(self._current_screen_index, len(self.preset.screens) - 1)
        self._render_screens()
        self._render_steps()

    def _replace_targets(self, old: str, replacement: str, fallback_replacement: str) -> None:
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
            ScreenPayload(screen.name, tuple(
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
            message = self.client.save_config(preset=self._build_payload())
        except ConfigValidationError as error:
            self._message(str(error))
            return
        except (OSError, ValueError) as error:
            self._message(f"Not saved: {error}")
            return
        self._message(message)
        self.saved.emit()

    def _message(self, text: str) -> None:
        self.status_label.setText(text)
