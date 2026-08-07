"""Editor for a map profile's Drag and Zoom Out camera actions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.step_edit_window import StepEditWindow
from app.widgets import make_independently_minimizable
from ipc.config_reader import AdvancedStep, GeneralConfig, MapProfileConfig, StepConfig
from ipc.config_writer import ConfigValidationError
from ipc.protocol import (
    save_adv_map_steps_payload,
    save_map_profile_payload,
)


STEP_TABLE_COLUMNS = ["Type", "X", "Y", "End X", "End Y", "Drag"]
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
        self._step_edit_window: StepEditWindow | None = None
        self._step_edit_target: tuple[str, AdvancedStep | None] | None = None
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
        self.step_list = QTableWidget(0, len(STEP_TABLE_COLUMNS))
        self.step_list.setObjectName("map_advanced_step_list")
        self.step_list.setHorizontalHeaderLabels(STEP_TABLE_COLUMNS)
        self.step_list.horizontalHeaderItem(STEP_TABLE_COLUMNS.index("Drag")).setToolTip(
            "Drag duration, measured in milliseconds."
        )
        self.step_list.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.step_list.horizontalHeader().setStretchLastSection(True)
        self.step_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.step_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.step_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Rows reorder by dragging the row-number header rather than the row body. QTableWidget's
        # internal move swaps cell contents between rows instead of moving a complete row, which
        # could combine fields from different actions. Header movement only changes visual order.
        self.step_list.verticalHeader().setSectionsMovable(True)
        self.step_list.verticalHeader().sectionMoved.connect(self._step_row_moved)
        self.step_list.cellDoubleClicked.connect(self._edit_step_at_row)
        steps_layout.addWidget(self.step_list, 1)
        step_buttons = QHBoxLayout()
        self.add_step_button = QPushButton("Add Step")
        self.edit_step_button = QPushButton("Edit Step...")
        self.delete_step_button = QPushButton("Delete Selected")
        self.duplicate_step_button = QPushButton("Duplicate")
        for button in (
            self.add_step_button, self.edit_step_button, self.delete_step_button,
            self.duplicate_step_button,
        ):
            step_buttons.addWidget(button)
        steps_layout.addLayout(step_buttons)
        root.addWidget(steps_box, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setObjectName("map_advanced_status")
        self.save_button = QPushButton("Save")
        self.close_button = QPushButton("Close")
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.save_button)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        self.add_step_button.clicked.connect(self._add_step)
        self.edit_step_button.clicked.connect(self._edit_selected_step)
        self.delete_step_button.clicked.connect(self._delete_step)
        self.duplicate_step_button.clicked.connect(self._duplicate_step)
        self.save_button.clicked.connect(self._save)
        self.close_button.clicked.connect(self.close)
        self._step_shortcuts = [
            self._shortcut(self.step_list, key, handler)
            for key, handler in (
                ("Delete", self._delete_step),
                ("Backspace", self._delete_step),
                ("Ctrl+D", self._duplicate_step),
                ("Ctrl+N", self._add_step),
                ("F2", self._edit_selected_step),
            )
        ]

    @staticmethod
    def _shortcut(widget: QWidget, key: str, handler: Any) -> QShortcut:
        shortcut = QShortcut(QKeySequence(key), widget)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(handler)
        return shortcut

    def _custom_camera_toggled(self, _: bool) -> None:
        # By the time this fires, the checkbox's own state has already flipped, so
        # self._effective_section already names the section being ARRIVED at - this resets ITS
        # entry back to its own true last-known-good state (never partially-edited). The section
        # being LEFT keeps whatever was unsaved in it, but that's harmless: toggling back into it
        # later re-fires this same handler and resets IT the same way at that point, and _save()
        # only ever reads self._steps (the currently-effective section) - a not-currently-effective
        # section's stale in-memory edits can never reach the adv_steps save payload. Net effect
        # matches OnMapCustomCameraToggled() in the legacy GUI: no unsaved edit survives a toggle away.
        #
        # An open action editor is closed for exactly that reason. It was started against one
        # section, and _save() only ever serializes the currently-effective one, so letting it
        # survive the toggle would let the user complete an edit that silently never reaches the
        # save payload. Discarding an in-flight edit here is the same rule the reset above applies
        # to the list itself, just extended to the edit that has not landed in it yet.
        self._close_step_editor()
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
            self.step_list.setRowCount(0)
            self.step_list.setRowCount(len(self._steps))
            for row, step in enumerate(self._steps):
                for column, text in enumerate(self._step_row_texts(step)):
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, step)
                    self.step_list.setItem(row, column, item)
        if select_row is not None and 0 <= select_row < len(self._steps):
            self.step_list.setCurrentCell(select_row, 0)

    @staticmethod
    def _step_row_texts(step: AdvancedStep) -> list[str]:
        # Only "Zoom Out" is special-cased, and every other type falls through showing all six
        # stored values. Real configs hold action types this editor does not offer ("Camera Drag",
        # "Zoom In", "Click" all appear in existing configs), and blanking cells per type the way
        # the preset editor's own _step_row_texts does would hide data those rows really have.
        if step.type == "Zoom Out":
            return [step.type, f"{step.x} ticks", "", "", "", ""]
        return [
            step.type, str(step.x), str(step.y), str(step.end_x), str(step.end_y), str(step.drag_ms),
        ]

    def _sync_steps_order(self) -> None:
        header = self.step_list.verticalHeader()
        self._steps[:] = [
            self.step_list.item(header.logicalIndex(visual), 0).data(Qt.ItemDataRole.UserRole)
            for visual in range(self.step_list.rowCount())
        ]

    def _step_row_moved(self, *_: Any) -> None:
        current_row = self.step_list.currentRow()
        selected_step = (
            self.step_list.item(current_row, 0).data(Qt.ItemDataRole.UserRole)
            if current_row >= 0 else None
        )
        self._sync_steps_order()
        select_row = next(
            (index for index, step in enumerate(self._steps) if step is selected_step), None,
        )
        self._render_steps(select_row)

    def _add_step(self) -> None:
        self._open_step_editor(None)

    def _edit_selected_step(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._steps):
            self._message("No map action selected.")
            return
        self._open_step_editor(row)

    def _edit_step_at_row(self, row: int, _column: int) -> None:
        self._open_step_editor(row)

    def _open_step_editor(self, row: int | None) -> None:
        if row is not None and not 0 <= row < len(self._steps):
            return
        # An action whose stored type is neither "Drag" nor "Zoom Out" ("Camera Drag", "Zoom In"
        # and "Click" all exist in older configs) loads into the editor as "Drag", because those
        # are the only two types it offers, and saving therefore rewrites the type. That is
        # deliberate rather than data loss: the engine dispatches on exactly those two strings
        # (RunMapAdvSteps in tower_defense_macro_gui.ahk), so any other type is an action it
        # silently skips, and it only ever changes when the user opens that row and presses Save.
        #
        # Keep the action object rather than its row number. The non-modal editor leaves this
        # table interactive, so a reorder, delete, or duplicate could otherwise make a later Save
        # overwrite a different action. The saved handler finds this same object by identity.
        # The section is captured alongside it for the same reason: the custom camera checkbox is
        # still live while the editor is open, and _effective_section would otherwise name a
        # DIFFERENT list by the time Save runs, appending a new action to the wrong one (or failing
        # to find the edited one at all). This mirrors the preset editor keeping target_screen.
        step = self._steps[row] if row is not None else None
        self._step_edit_target = (self._effective_section, step)
        window = self._step_edit_window
        if window is None:
            # Deliberately no Qt parent: see make_independently_minimizable in app/widgets.py -
            # a parented QDialog becomes a native Windows owned window that minimizes together
            # with its owner, which is exactly what this window must not do.
            window = StepEditWindow(self.client, map_action_mode=True)
            window.saved.connect(self._save_step_from_editor)
            window.finished.connect(self._clear_step_edit_window)
            self._step_edit_window = window
        window.open_for_map_action(step)
        window.show()
        window.raise_()
        window.activateWindow()

    def _clear_step_edit_window(self, *_: Any) -> None:
        self._step_edit_window = None
        self._step_edit_target = None

    def _close_step_editor(self) -> None:
        """Shut the shared action editor and forget what it was editing.

        The editor is deliberately parentless (see _open_step_editor), so nothing closes it on
        our behalf. Left open it becomes an orphan whose Save writes into a model the user can
        no longer see or persist.
        """
        window = self._step_edit_window
        if window is not None:
            window.reject()
        self._clear_step_edit_window()

    def closeEvent(self, event: Any) -> None:
        self._close_step_editor()
        super().closeEvent(event)

    def _save_step_from_editor(self, step: StepConfig) -> None:
        if self._step_edit_target is None:
            return
        section, target = self._step_edit_target
        # Write into the section this edit was STARTED in, not whichever one is effective now.
        steps = self._steps_by_section[section]
        action = AdvancedStep(
            type=step.type, x=step.x, y=step.y, end_x=step.end_x, end_y=step.end_y,
            drag_ms=step.drag_ms,
        )
        if target is None:
            steps.append(action)
            row = len(steps) - 1
        else:
            row = next((index for index, existing in enumerate(steps) if existing is target), None)
            if row is None:
                self._message("The map action being edited no longer exists.")
                return
            steps[row] = action
        # Only re-render when that section is the one on screen; otherwise the table is showing a
        # different list and selecting `row` in it would highlight an unrelated action.
        if section == self._effective_section:
            self._render_steps(row)

    def _delete_step(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._steps):
            return
        step = self._steps[row]
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Confirm")
        confirmation.setText(f"Delete map action '{step.type}'?")
        confirmation.setIcon(QMessageBox.Icon.NoIcon)
        confirmation.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirmation.exec() != QMessageBox.StandardButton.Yes:
            return
        del self._steps[row]
        self._render_steps(min(row, len(self._steps) - 1))

    def _duplicate_step(self) -> None:
        row = self.step_list.currentRow()
        if not 0 <= row < len(self._steps):
            self._message("No map action selected.")
            return
        self._steps.insert(row + 1, deepcopy(self._steps[row]))
        self._render_steps(row + 1)

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
