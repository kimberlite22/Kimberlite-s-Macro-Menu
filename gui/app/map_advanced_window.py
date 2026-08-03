"""Editor for a map profile's Drag and Zoom Out camera actions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.capture import capture_point
from app.widgets import (
    NoScrollComboBox,
    NoScrollDoubleSpinBox,
    NoScrollSpinBox,
    make_independently_minimizable,
)
from ipc.config_reader import AdvancedStep, GeneralConfig, MapProfileConfig
from ipc.config_writer import ConfigValidationError
from ipc.protocol import save_adv_map_steps_payload, save_map_profile_payload


STEP_TYPES = ("Drag", "Zoom Out")
GENERAL_TARGET = "General"


class MapAdvancedWindow(QDialog):
    """Keep both effective action lists in memory and explicitly save one of them."""

    saved = Signal()

    def __init__(
        self,
        map_profile_name: str,
        client: Any,
        *,
        profile: MapProfileConfig | None = None,
        general: GeneralConfig | None = None,
        config_source: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        # Deliberately NOT given a Qt parent by its production caller (see
        # make_independently_minimizable): on Windows, a top-level QDialog constructed
        # with a parent widget becomes a native OS "owned window" that auto-hides
        # whenever its owner is minimized, regardless of any window-flag hint, which is
        # exactly the minimize coupling this window must not have. The one genuine data
        # dependency this window used to read off its Qt parent (the live, ever-refreshed
        # config held by MainWindow) is threaded through explicitly instead, via
        # config_source, so the window still sees live data without needing a Qt parent
        # relationship to get it.
        super().__init__(parent)
        make_independently_minimizable(self)
        self._config_source = config_source
        # Captured once, NOT re-read from config_source at save time: this window's `profile`/
        # `general` snapshot already belongs to whichever game was active when it was opened, and
        # this window can sit open across a later game switch elsewhere in the app (see
        # make_independently_minimizable's own note about staying open independently). Using a
        # live active_game at save time would silently write this snapshot's data into a
        # DIFFERENT game's sections after such a switch.
        self._game = getattr(getattr(config_source, "config", None), "active_game", "")
        if map_profile_name != GENERAL_TARGET and profile is None:
            raise ValueError("An actual map profile requires its MapProfileConfig.")
        self.map_profile_name = map_profile_name
        self.client = client
        self.profile = deepcopy(profile) if profile is not None else None
        self._initial_steps_by_section = {
            GENERAL_TARGET: deepcopy(list(general.adv_steps if general is not None else [])),
        }
        if self.profile is not None:
            self._initial_steps_by_section[self._profile_section] = deepcopy(self.profile.adv_steps)
        self._steps_by_section = deepcopy(self._initial_steps_by_section)

        target_label = "shared default" if map_profile_name == GENERAL_TARGET else map_profile_name
        self.setWindowTitle(f"Map Advanced Settings: {target_label}")
        self.resize(760, 620)
        self._build_ui()
        self._load_effective_steps()

    @property
    def _profile_section(self) -> str:
        return f"MapProfile_{self.map_profile_name}"

    @property
    def _effective_section(self) -> str:
        if self.profile is not None and self.custom_camera.isChecked():
            return self._profile_section
        return GENERAL_TARGET

    @property
    def _steps(self) -> list[AdvancedStep]:
        return self._steps_by_section[self._effective_section]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.editing_label = QLabel()
        self.editing_label.setObjectName("map_advanced_editing_label")
        root.addWidget(self.editing_label)

        self.custom_camera = QCheckBox("Use custom camera/zoom settings for this map")
        self.custom_camera.setToolTip(
            "When unchecked, this map uses the shared default camera/zoom settings instead."
        )
        self.custom_camera.setObjectName("map_advanced_custom_camera")
        if self.profile is None:
            self.custom_camera.hide()
        else:
            self.custom_camera.setChecked(self.profile.custom_camera)
            self.custom_camera.toggled.connect(self._custom_camera_toggled)
        root.addWidget(self.custom_camera)

        steps_box = QGroupBox("Map actions")
        steps_layout = QVBoxLayout(steps_box)
        self.step_list = QListWidget()
        self.step_list.setObjectName("map_advanced_step_list")
        self.step_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.step_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.step_list.currentRowChanged.connect(self._step_selected)
        self.step_list.model().rowsMoved.connect(self._step_rows_moved)
        steps_layout.addWidget(self.step_list)
        move_buttons = QHBoxLayout()
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        move_buttons.addWidget(self.move_up_button)
        move_buttons.addWidget(self.move_down_button)
        move_buttons.addStretch(1)
        steps_layout.addLayout(move_buttons)
        root.addWidget(steps_box, 1)

        editor_box = QGroupBox("Step Editor")
        editor = QGridLayout(editor_box)
        self._labels: dict[str, QLabel] = {}
        self._widgets: dict[str, QWidget] = {}
        self.step_type = NoScrollComboBox()
        self.step_type.setObjectName("map_advanced_step_type")
        self.step_type.addItems(STEP_TYPES)
        self.step_x = self._number("map_advanced_step_x")
        self.step_y = self._number("map_advanced_step_y")
        self.step_end_x = self._number("map_advanced_step_end_x")
        self.step_end_y = self._number("map_advanced_step_end_y")
        self.step_drag_ms = self._integer("map_advanced_step_drag_ms", 0, 600000)
        self.step_drag_ms.setValue(500)
        self.capture_start_button = QPushButton("Capture start")
        self.capture_start_button.setObjectName("map_advanced_capture_start_button")
        self.capture_end_button = QPushButton("Capture end")
        self.capture_end_button.setObjectName("map_advanced_capture_end_button")

        self._add_row(editor, 0, "type", "Type", self.step_type)
        self._add_row(editor, 1, "x", "Start X", self.step_x)
        self._add_row(editor, 1, "y", "Start Y", self.step_y, 2)
        self._add_row(editor, 2, "start_capture", "", self.capture_start_button)
        self._add_row(editor, 3, "end_x", "End X", self.step_end_x)
        self._add_row(editor, 3, "end_y", "End Y", self.step_end_y, 2)
        self._add_row(editor, 4, "end_capture", "", self.capture_end_button)
        self._add_row(editor, 4, "drag_ms", "Drag", self.step_drag_ms, 2)
        self._labels["drag_ms"].setToolTip("Measured in milliseconds.")
        self._widgets["drag_ms"].setToolTip("Measured in milliseconds.")
        root.addWidget(editor_box)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add Step")
        self.update_button = QPushButton("Update Selected")
        self.remove_button = QPushButton("Remove Selected")
        for button in (self.add_button, self.update_button, self.remove_button):
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)

        footer = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setObjectName("map_advanced_status")
        self.save_button = QPushButton("Save")
        self.close_button = QPushButton("Close")
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.save_button)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        self.step_type.currentTextChanged.connect(self._update_field_visibility)
        self.capture_start_button.clicked.connect(lambda: self._capture_into(self.step_x, self.step_y))
        self.capture_end_button.clicked.connect(lambda: self._capture_into(self.step_end_x, self.step_end_y))
        self.add_button.clicked.connect(self._add_step)
        self.update_button.clicked.connect(self._update_selected)
        self.remove_button.clicked.connect(self._remove_selected)
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        self.save_button.clicked.connect(self._save)
        self.close_button.clicked.connect(self.close)
        self._update_field_visibility()

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

    def _add_row(self, grid: QGridLayout, row: int, key: str, text: str, widget: QWidget, column: int = 0) -> None:
        label = QLabel(text)
        self._labels[key] = label
        self._widgets[key] = widget
        grid.addWidget(label, row, column)
        grid.addWidget(widget, row, column + 1)

    def _set_visible(self, key: str, visible: bool) -> None:
        self._labels[key].setVisible(visible)
        self._widgets[key].setVisible(visible)

    def _update_field_visibility(self, *_: Any) -> None:
        is_drag = self.step_type.currentText() == "Drag"
        self._labels["x"].setText("Start X" if is_drag else "Ticks")
        for key in ("y", "start_capture", "end_x", "end_y", "end_capture", "drag_ms"):
            self._set_visible(key, is_drag)

    def _custom_camera_toggled(self, _: bool) -> None:
        # By the time this fires, the checkbox's own state has already flipped, so
        # self._effective_section already names the section being ARRIVED at - this resets ITS
        # entry back to its own true last-known-good state (never partially-edited). The section
        # being LEFT keeps whatever was unsaved in it, but that's harmless: toggling back into it
        # later re-fires this same handler and resets IT the same way at that point, and _save()
        # only ever reads self._steps (the currently-effective section) - a not-currently-effective
        # section's stale in-memory edits can never reach the adv_steps save payload. Net effect
        # matches OnMapCustomCameraToggled() in the legacy GUI: no unsaved edit survives a toggle away.
        self._steps_by_section[self._effective_section] = deepcopy(
            self._initial_steps_by_section[self._effective_section]
        )
        self._load_effective_steps()

    def _load_effective_steps(self) -> None:
        if self.profile is None:
            self.editing_label.setText("Editing: shared default (all maps)")
        elif self.custom_camera.isChecked():
            self.editing_label.setText(f"Editing: custom settings for '{self.map_profile_name}'")
        else:
            self.editing_label.setText("Editing: shared default (all maps without custom settings)")
        self._render_steps()

    def _render_steps(self, select_row: int | None = None) -> None:
        with QSignalBlocker(self.step_list):
            self.step_list.clear()
            for index, step in enumerate(self._steps, 1):
                item = QListWidgetItem(self._step_summary(index, step))
                item.setData(Qt.ItemDataRole.UserRole, step)
                self.step_list.addItem(item)
        if select_row is not None and 0 <= select_row < len(self._steps):
            self.step_list.setCurrentRow(select_row)

    @staticmethod
    def _step_summary(index: int, step: AdvancedStep) -> str:
        return (
            f"{index}. {step.type} | {step.x} | {step.y} | {step.end_x} | "
            f"{step.end_y} | {step.drag_ms}"
        )

    def _step_selected(self, row: int) -> None:
        if not 0 <= row < len(self._steps):
            return
        step = self._steps[row]
        with QSignalBlocker(self.step_type):
            self.step_type.setCurrentText(step.type)
        self.step_x.setValue(step.x)
        self.step_y.setValue(step.y)
        self.step_end_x.setValue(step.end_x)
        self.step_end_y.setValue(step.end_y)
        self.step_drag_ms.setValue(step.drag_ms)
        self._update_field_visibility()

    def _step_rows_moved(self, *_: Any) -> None:
        self._steps[:] = [
            self.step_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.step_list.count())
        ]
        for index, step in enumerate(self._steps, 1):
            self.step_list.item(index - 1).setText(self._step_summary(index, step))

    def _step_from_editor(self) -> AdvancedStep:
        return AdvancedStep(
            type=self.step_type.currentText(), x=self.step_x.value(), y=self.step_y.value(),
            end_x=self.step_end_x.value(), end_y=self.step_end_y.value(),
            drag_ms=self.step_drag_ms.value(),
        )

    def _add_step(self) -> None:
        self._steps.append(self._step_from_editor())
        self._render_steps()

    def _update_selected(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._steps):
            self._message("No map action selected.")
            return
        self._steps[row] = self._step_from_editor()
        self._render_steps(row)

    def _remove_selected(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._steps):
            return
        del self._steps[row]
        self._render_steps()

    def _move_selected(self, direction: int) -> None:
        row = self.step_list.currentRow()
        target = row + direction
        if not 0 <= row < len(self._steps) or not 0 <= target < len(self._steps):
            return
        self._steps[row], self._steps[target] = self._steps[target], self._steps[row]
        self._render_steps(target)

    def _capture_into(self, x_field: QDoubleSpinBox, y_field: QDoubleSpinBox) -> None:
        try:
            captured = capture_point(self.client, self)
        except Exception as error:
            self._message(f"Capture failed: {error}")
            return
        if captured is None:
            self._message("Capture cancelled.")
            return
        x, y = captured
        x_field.setValue(x)
        y_field.setValue(y)

    def _current_profile_snapshot(self) -> MapProfileConfig:
        # The map profile save payload is whole-entity with no partial-update form, but this dialog
        # only has UI for customCamera - expected_text/custom_towers/placements are edited on MainWindow's
        # own Map Placement tab. This dialog is modeless and can sit open for a long time, so resending
        # those OTHER fields from `self.profile` (a copy frozen at construction time) would silently
        # revert any edit made to them elsewhere in the meantime. Prefer config_source's live
        # `config.map_profiles` (refreshed whenever a save lands from anywhere, this dialog's own
        # previous saves included) over that frozen snapshot, narrowing the staleness window from
        # "since this dialog was opened" to "since the last config refresh."
        parent_config = getattr(self._config_source, "config", None)
        for candidate in getattr(parent_config, "map_profiles", ()):
            if candidate.name == self.map_profile_name:
                return candidate
        assert self.profile is not None
        return self.profile

    def _build_profile_payload(self) -> dict[str, Any]:
        profile = self._current_profile_snapshot()
        return save_map_profile_payload(
            name=profile.name,
            expected_text=profile.expected_text,
            custom_towers=profile.custom_towers,
            custom_num_placements=profile.custom_num_placements,
            placements=(
                {"customSlot": placement.custom_slot, "x": placement.x, "y": placement.y}
                for placement in profile.placements
            ),
            custom_camera=self.custom_camera.isChecked(),
        )

    def _save(self) -> None:
        # One document, one backup, one atomic replace: the profile's CustomCamera flag (if any)
        # and its camera steps land together, so adv_steps_section (config_writer.py) always reads
        # the CustomCamera value this same save just wrote, never a stale one from a second, separate
        # write.
        payloads: dict[str, Any] = {
            "game": self._game,
            "adv_steps": save_adv_map_steps_payload(
                map_profile_name=self.map_profile_name,
                steps=(
                    {
                        "type": step.type, "x": step.x, "y": step.y,
                        "endX": step.end_x, "endY": step.end_y, "dragMs": step.drag_ms,
                    }
                    for step in self._steps
                ),
            ),
        }
        if self.profile is not None:
            payloads["map_profile"] = self._build_profile_payload()

        try:
            message = self.client.save_config(**payloads)
        except ConfigValidationError as error:
            self._message(str(error))
            return
        except (OSError, ValueError) as error:
            self._message(f"Not saved: {error}")
            return

        if self.profile is not None:
            self.profile.custom_camera = self.custom_camera.isChecked()
        self._initial_steps_by_section[self._effective_section] = deepcopy(self._steps)
        self._message(message)
        self.saved.emit()

    def _message(self, text: str) -> None:
        self.status_label.setText(text)
