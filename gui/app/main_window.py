"""The main PySide6 window for the local AHK GUI bridge."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Protocol

from PySide6.QtCore import QSignalBlocker, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.edit_preset_window import EditPresetWindow
from app.capture import capture_point
from app.launcher_paths import APP_NAME
from app.map_advanced_window import MapAdvancedWindow
from app.remote_agent_tab import RemoteAgentTab
from app.widgets import NoScrollComboBox, NoScrollDoubleSpinBox, NoScrollSpinBox

from ipc.client import CommandAck, ConfigChangeTracker, IpcBusyError, IpcTimeoutError, LocalIpcClient
from ipc.config_writer import ConfigValidationError, MutationError
from ipc.config_reader import (
    AppConfig,
    GeneralConfig,
    OptionConfig,
    PresetConfig,
    read_config,
)
from ipc.protocol import (
    GameProcessCandidate,
    LocalStatus,
    OptionPayload,
    ScreenPayload,
    StepPayload,
    VERB_FORCE_GAME_WINDOW,
    VERB_LIST_GAME_PROCESSES,
    VERB_SET_ACTIVE_PRESET,
    VERB_SHOW_REGION_PREVIEW,
    VERB_PAUSE,
    VERB_RESUME,
    VERB_START,
    VERB_STOP,
    VERB_TEST_OCR,
    force_game_window_payload,
    list_game_processes_payload,
    save_general_payload,
    save_map_profile_payload,
    save_preset_payload,
    set_active_preset_payload,
    pause_payload,
    resume_payload,
    start_payload,
    stop_payload,
)


STATUS_POLL_INTERVAL_MS = 250
STALE_STATUS_SECONDS = 3.0

# A tower loadout slot is the game's own hotbar position, NOT a preset option name. Mirror the
# engine exactly: macro/tower_defense_macro_gui.ahk builds both the General tab's GeneralSlotDdls
# and the per-map customSlotDdls as DropDownLists over ["1".."6"], and reads them back with
# SetDdlTextSafe(..., Cfg(..., "1"), "1"), i.e. anything not in that list falls back to "1".
TOWER_SLOT_CHOICES = ("1", "2", "3", "4", "5", "6")
TOWER_SLOT_DEFAULT = "1"


class IpcClient(Protocol):
    """The narrow bridge surface used by the window and its tests."""

    def read_status(self) -> LocalStatus | None: ...

    def read_game_processes(self) -> list[GameProcessCandidate]: ...

    def send_command(self, verb: str, payload: dict[str, Any]) -> CommandAck: ...

    def save_config(self, **payloads: Any) -> str: ...

    def create_preset(self, name: str) -> str: ...

    def rename_preset(self, old_name: str, new_name: str) -> str: ...

    def delete_preset(self, name: str) -> str: ...

    def export_preset(self, name: str, file_path: str) -> str: ...

    def import_preset(self, file_path: str, new_name: str) -> str: ...

    def create_map_profile(self, name: str) -> str: ...

    def rename_map_profile(self, old_name: str, new_name: str) -> str: ...

    def delete_map_profile(self, name: str) -> str: ...

    def set_option_used_count(self, preset_name: str, option_index: int, count: int) -> str: ...

    def set_option_max(self, preset_name: str, option_index: int, maximum: int) -> str: ...


def preset_config_to_screens_payload(preset: PresetConfig) -> list[dict[str, Any]]:
    """Convert immutable config screens to the complete preset-save wire shape.

    The screen editor is intentionally not part of this milestone. Passing this
    full, unedited representation into the preset save payload keeps the write
    safe for presets which already contain screens and steps.
    """
    return [
        ScreenPayload(
            name=screen.name,
            steps=tuple(
                StepPayload(
                    type=step.type,
                    label=step.label,
                    x=step.x,
                    y=step.y,
                    end_x=step.end_x,
                    end_y=step.end_y,
                    drag_ms=step.drag_ms,
                    once_per_cycle=step.once_per_cycle,
                    seconds=step.seconds,
                    on_true_screen=step.on_true_screen,
                    on_false_screen=step.on_false_screen,
                    fallback_enabled=step.fallback_enabled,
                    fallback_max_attempts=step.fallback_max_attempts,
                    fallback_screen=step.fallback_screen,
                    advanced=step.advanced,
                    outcomes_raw=step.outcomes_raw,
                )
                for step in screen.steps
            ),
        ).to_dict()
        for screen in preset.screens
    ]


class MainWindow(QMainWindow):
    """Read config.ini, display the three main tabs, and talk to the bridge."""

    _NONE_CHOICE = "(none)"

    def __init__(
        self,
        data_dir: str | Path,
        client: IpcClient | None = None,
        *,
        poll_interval_ms: int = STATUS_POLL_INTERVAL_MS,
        auto_refresh_game_processes: bool = True,
    ) -> None:
        super().__init__()
        self.data_dir = Path(data_dir)
        self.config_path = self.data_dir / "config.ini"
        self.client: IpcClient = client if client is not None else LocalIpcClient(self.data_dir)
        self.config = AppConfig(general=GeneralConfig())
        # Set on the first successful _refresh_config(). Distinguishes "never loaded a real
        # config yet" (a read failure means defaults are genuinely all we have) from "a later
        # read failed transiently" (self.config still holds the last known-good values, which
        # must survive the failure - see _refresh_config).
        self._config_loaded_once = False
        self.config_tracker = ConfigChangeTracker()
        self._selected_preset_name = ""
        self._selected_map_profile_name = ""
        self._last_timestamp: str | None = None
        self._last_seen_wall_time: float | None = None
        # Keyed by preset name so a second "Edit..." click on the SAME preset re-focuses the
        # existing editor instead of opening a duplicate - two independent in-memory editors for
        # one preset would let whichever saves last silently discard the other's edits. Editors for
        # DIFFERENT presets may still be open at once; they touch different config sections.
        self._edit_preset_windows: dict[str, EditPresetWindow] = {}
        self._map_advanced_windows: dict[str, MapAdvancedWindow] = {}

        self.setWindowTitle(APP_NAME)
        self.resize(1080, 860)
        self._build_ui()
        self._refresh_config()
        # Deferred (not called directly): this is a real IPC round-trip, and the engine very likely
        # is not running yet the moment this window is first constructed - QTimer.singleShot(0, ...)
        # lets the window actually appear (main.py's show() runs right after this constructor returns)
        # before this potentially slow, no-op-if-nothing-answers refresh kicks in. main.py disables
        # only this automatic request when a previous GUI's command is still pending.
        if auto_refresh_game_processes:
            QTimer.singleShot(0, self._refresh_game_processes)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_status)
        self.status_timer.start(poll_interval_ms)
        self._poll_status()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 8)
        root.setSpacing(10)

        self.notice_label = QLabel()
        self.notice_label.setObjectName("config_notice_label")
        self.notice_label.setWordWrap(True)
        self.notice_label.setStyleSheet("color: #f0c674; padding: 6px;")
        self.notice_label.hide()
        root.addWidget(self.notice_label)

        status_box = QGroupBox("Engine status")
        status_layout = QHBoxLayout(status_box)
        self.engine_status_label = QLabel("Idle")
        self.engine_status_label.setObjectName("engine_status_label")
        self.engine_status_label.setStyleSheet("font-weight: 700; color: #aeb8ca;")
        status_layout.addWidget(self.engine_status_label)
        status_layout.addStretch(1)
        root.addWidget(status_box)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_preset_tab(), "Preset Settings")
        self.tabs.addTab(self._build_map_tab(), "Map Placement")
        self.tabs.addTab(self._build_general_tab(), "General")
        self.remote_agent_tab = RemoteAgentTab(self.config.general, self.client)
        # Alias so _populate_general()/_general_payload() keep addressing the checkbox by the
        # same attribute name they used before it moved here - it is still one General setting
        # (persisted under [General] like the others), just presented inside this tab now.
        self.general_remote_bridge_enabled = self.remote_agent_tab.remote_bridge_enabled_checkbox
        self.tabs.addTab(self.remote_agent_tab, "Remote Agent")
        self.general_num_placements.valueChanged.connect(self._update_placements_table_layout)
        root.addWidget(self.tabs, 1)

        controls = QHBoxLayout()
        controls.addStretch(1)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("save_button")
        self.save_button.clicked.connect(self._save)
        self.pin_button = QPushButton("Pin")
        self.pin_button.setObjectName("pin_button")
        self.pin_button.clicked.connect(self._force_game_window)
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("start_button")
        self.start_button.clicked.connect(self._start)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._pause)
        self.resume_button = QPushButton("Resume")
        self.resume_button.clicked.connect(self._resume)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop)
        controls.addWidget(self.save_button)
        controls.addWidget(self.pin_button)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.resume_button)
        controls.addWidget(self.stop_button)
        root.addLayout(controls)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))

    def _build_preset_tab(self) -> QWidget:
        page, layout = self._scrollable_page()
        selector_box = QGroupBox("Presets")
        selector_layout = QHBoxLayout(selector_box)
        self.preset_list = QListWidget()
        self.preset_list.setObjectName("preset_list")
        self.preset_list.currentTextChanged.connect(self._preset_selected)
        selector_layout.addWidget(self.preset_list, 1)
        buttons = QVBoxLayout()
        self.preset_new_button = self._button("New", self._new_preset)
        self.preset_rename_button = self._button("Rename", self._rename_preset)
        self.preset_delete_button = self._button("Delete", self._delete_preset)
        self.preset_edit_button = self._button("Edit...", self._edit_preset)
        self.preset_export_button = self._button("Export...", self._export_preset)
        self.preset_import_button = self._button("Import...", self._import_preset)
        for button in (
            self.preset_new_button, self.preset_rename_button, self.preset_delete_button,
            self.preset_edit_button, self.preset_export_button, self.preset_import_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        selector_layout.addLayout(buttons)
        layout.addWidget(selector_box)

        active_layout = QHBoxLayout()
        self.active_preset_label = QLabel("Runs on Start: -")
        self.active_preset_label.setObjectName("active_preset_label")
        self.active_preset_label.setStyleSheet("font-weight: 700; color: #8ce99a;")
        self.set_active_button = self._button("Set as Active", self._set_active_preset)
        active_layout.addWidget(self.active_preset_label)
        active_layout.addStretch(1)
        active_layout.addWidget(self.set_active_button)
        layout.addLayout(active_layout)

        metadata_box = QGroupBox("Preset settings")
        metadata_form = QFormLayout(metadata_box)
        self.preset_default_map = NoScrollComboBox()
        self.preset_default_map.setObjectName("preset_default_map")
        self.preset_back_x = self._number("preset_back_x")
        self.preset_back_y = self._number("preset_back_y")
        self.preset_fallback_screen = NoScrollComboBox()
        self.preset_fallback_screen.setObjectName("preset_fallback_screen")
        metadata_form.addRow("Default map:", self.preset_default_map)
        metadata_form.addRow("Back X:", self.preset_back_x)
        metadata_form.addRow("Back Y:", self.preset_back_y)
        metadata_form.addRow("Fallback screen:", self.preset_fallback_screen)
        layout.addWidget(metadata_box)

        options_box = QGroupBox("Challenge option basics")
        options_layout = QGridLayout(options_box)
        options_layout.addWidget(QLabel("Option"), 0, 0)
        options_layout.addWidget(QLabel("Name"), 0, 1)
        options_layout.addWidget(QLabel("X"), 0, 2)
        options_layout.addWidget(QLabel("Y"), 0, 3)
        options_layout.addWidget(QLabel("Available"), 0, 4)
        options_layout.addWidget(QLabel("Priority"), 0, 5)
        self.preset_option_names: list[QLineEdit] = []
        self.preset_option_x: list[QDoubleSpinBox] = []
        self.preset_option_y: list[QDoubleSpinBox] = []
        self.preset_option_available: list[QCheckBox] = []
        self.preset_option_priority: list[QSpinBox] = []
        for index in range(3):
            name = QLineEdit()
            name.setObjectName(f"preset_option_{index + 1}_name")
            x = self._number(f"preset_option_{index + 1}_x")
            y = self._number(f"preset_option_{index + 1}_y")
            available = QCheckBox()
            available.setObjectName(f"preset_option_{index + 1}_available")
            priority = self._integer(f"preset_option_{index + 1}_priority", 0, 100)
            self.preset_option_names.append(name)
            self.preset_option_x.append(x)
            self.preset_option_y.append(y)
            self.preset_option_available.append(available)
            self.preset_option_priority.append(priority)
            options_layout.addWidget(QLabel(str(index + 1)), index + 1, 0)
            options_layout.addWidget(name, index + 1, 1)
            options_layout.addWidget(x, index + 1, 2)
            options_layout.addWidget(y, index + 1, 3)
            options_layout.addWidget(available, index + 1, 4, alignment=Qt.AlignmentFlag.AlignCenter)
            options_layout.addWidget(priority, index + 1, 5)
        layout.addWidget(options_box)

        usage_box = QGroupBox("Today's Challenge Usage")
        usage_layout = QGridLayout(usage_box)
        usage_layout.addWidget(QLabel("Option"), 0, 0)
        usage_layout.addWidget(QLabel("Used"), 0, 1)
        usage_layout.addWidget(QLabel("Daily limit (0 = unlimited)"), 0, 2)
        self.usage_used: list[QSpinBox] = []
        self.usage_max: list[QSpinBox] = []
        for index in range(3):
            used = self._integer(f"usage_option_{index + 1}_used", 0, 1_000_000)
            maximum = self._integer(f"usage_option_{index + 1}_max", 0, 1_000_000)
            used.valueChanged.connect(lambda value, i=index: self._usage_changed(i, value, False))
            maximum.valueChanged.connect(lambda value, i=index: self._usage_changed(i, value, True))
            self.usage_used.append(used)
            self.usage_max.append(maximum)
            usage_layout.addWidget(QLabel(f"Option {index + 1}"), index + 1, 0)
            usage_layout.addWidget(used, index + 1, 1)
            usage_layout.addWidget(maximum, index + 1, 2)
        layout.addWidget(usage_box)
        layout.addStretch(1)
        return page

    def _build_map_tab(self) -> QWidget:
        page, layout = self._scrollable_page()
        profile_box = QGroupBox("Map profiles")
        profile_layout = QHBoxLayout(profile_box)
        self.map_profile_combo = NoScrollComboBox()
        self.map_profile_combo.setObjectName("map_profile_combo")
        self.map_profile_combo.currentTextChanged.connect(self._map_profile_selected)
        profile_layout.addWidget(self.map_profile_combo, 1)
        self.map_new_button = self._button("New", self._new_map_profile)
        self.map_rename_button = self._button("Rename", self._rename_map_profile)
        self.map_delete_button = self._button("Delete", self._delete_map_profile)
        profile_layout.addWidget(self.map_new_button)
        profile_layout.addWidget(self.map_rename_button)
        profile_layout.addWidget(self.map_delete_button)
        layout.addWidget(profile_box)

        settings_box = QGroupBox("Map placement settings")
        settings_form = QFormLayout(settings_box)
        self.map_expected_text = QLineEdit()
        self.map_expected_text.setObjectName("map_expected_text")
        self.map_custom_towers = QCheckBox("Use custom tower slots for this map")
        self.map_custom_towers.setObjectName("map_custom_towers")
        self.map_num_placements = self._integer("map_num_placements", 0, 10)
        self.map_custom_camera = QCheckBox("Use custom camera actions for this map")
        self.map_custom_camera.setObjectName("map_custom_camera")
        self.map_custom_towers.toggled.connect(self._update_placements_table_layout)
        self.map_num_placements.valueChanged.connect(self._update_placements_table_layout)
        settings_form.addRow("Expected map text:", self.map_expected_text)
        settings_form.addRow("", self.map_custom_towers)
        settings_form.addRow("Number of placements:", self.map_num_placements)
        settings_form.addRow("", self.map_custom_camera)
        layout.addWidget(settings_box)

        placements_box = QGroupBox("Coordinates for this map's tower placements")
        placements_layout = QVBoxLayout(placements_box)
        self.placements_table = QTableWidget(10, 4)
        self.placements_table.setObjectName("placements_table")
        self.placements_table.setHorizontalHeaderLabels(["Custom slot", "X", "Y", "Capture"])
        self.placements_table.setVerticalHeaderLabels([str(index) for index in range(1, 11)])
        column_widths = (90, 70, 70, 90)
        for column, width in enumerate(column_widths):
            self.placements_table.setColumnWidth(column, width)
        self.placements_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.placements_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table_width = sum(column_widths) + self.placements_table.verticalHeader().width()
        table_width += self.placements_table.frameWidth() * 2 + 4
        self.placements_table.setFixedWidth(table_width)
        for row in range(self.placements_table.rowCount()):
            button = QPushButton("Capture")
            button.setObjectName(f"placement_capture_button_{row}")
            button.clicked.connect(lambda _checked=False, target_row=row: self._capture_placement(target_row))
            self.placements_table.setCellWidget(row, 3, button)
        placements_layout.addWidget(self.placements_table, alignment=Qt.AlignmentFlag.AlignLeft)
        self.map_advanced_button = self._button("Map Advanced Settings...", self._open_map_advanced)
        self.map_advanced_button.setObjectName("map_advanced_button")
        placements_layout.addWidget(self.map_advanced_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(placements_box, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _build_general_tab(self) -> QWidget:
        page, layout = self._scrollable_page()
        timing = QGroupBox("Timing")
        timing_form = QFormLayout(timing)
        self.general_round_wait = self._number("general_round_wait")
        self.general_click_delay = self._integer("general_click_delay", 0, 1_000_000)
        self.general_place_tower_delay = self._integer("general_place_tower_delay", 0, 1_000_000)
        self.general_max_rounds = self._integer("general_max_rounds", 0, 1_000_000)
        self.general_marker_size = self._integer("general_marker_size", 0, 100_000)
        timing_form.addRow("Extra wait after each full cycle (sec):", self.general_round_wait)
        timing_form.addRow("Click delay (ms):", self.general_click_delay)
        timing_form.addRow("Tower placement delay (ms):", self.general_place_tower_delay)
        timing_form.addRow("Max cycles (0 = unlimited):", self.general_max_rounds)
        timing_form.addRow("Position marker size (px):", self.general_marker_size)
        layout.addWidget(timing)

        loadout = QGroupBox("Tower Loadout")
        loadout_layout = QGridLayout(loadout)
        self.general_num_placements = self._integer("general_num_placements", 0, 10)
        num_placements_row = QHBoxLayout()
        num_placements_row.addWidget(QLabel("Number of placements:"))
        num_placements_row.addWidget(self.general_num_placements)
        num_placements_row.addStretch(1)
        loadout_layout.addLayout(num_placements_row, 0, 0, 1, 10)
        loadout_layout.addWidget(QLabel("Default slots (position 1 through 10):"), 1, 0, 1, 10)
        self.general_slots: list[QComboBox] = []
        for index in range(10):
            slot = NoScrollComboBox()
            slot.setObjectName(f"general_slot_{index + 1}")
            self.general_slots.append(slot)
            loadout_layout.addWidget(QLabel(str(index + 1)), 2, index)
            loadout_layout.addWidget(slot, 3, index)
        for column in range(10):
            loadout_layout.setColumnStretch(column, 1)
        self.general_after_place_click = QCheckBox("Click after each tower placed")
        self.general_after_place_click.setObjectName("general_after_place_click")
        self.general_after_place_x = self._number("general_after_place_x")
        self.general_after_place_y = self._number("general_after_place_y")
        loadout_layout.addWidget(self.general_after_place_click, 4, 0, 1, 3)
        loadout_layout.addWidget(QLabel("X:"), 4, 3)
        loadout_layout.addWidget(self.general_after_place_x, 4, 4, 1, 2)
        loadout_layout.addWidget(QLabel("Y:"), 4, 6)
        loadout_layout.addWidget(self.general_after_place_y, 4, 7, 1, 2)
        layout.addWidget(loadout)

        game = QGroupBox("Game Window")
        game_form = QFormLayout(game)
        self.general_game_process = self._editable_combo("general_game_process")
        self.general_game_process_refresh_button = self._button("Refresh", self._refresh_game_processes)
        self.general_hole_x = self._number("general_hole_x")
        self.general_hole_y = self._number("general_hole_y")
        self.general_hole_w = self._number("general_hole_w")
        self.general_hole_h = self._number("general_hole_h")
        game_process_layout = QHBoxLayout()
        game_process_layout.addWidget(self.general_game_process)
        game_process_layout.addWidget(self.general_game_process_refresh_button)
        game_form.addRow("Process:", game_process_layout)
        game_form.addRow("Opening offset X:", self.general_hole_x)
        game_form.addRow("Opening offset Y:", self.general_hole_y)
        game_form.addRow("Opening width:", self.general_hole_w)
        game_form.addRow("Opening height:", self.general_hole_h)
        layout.addWidget(game)

        disconnect = QGroupBox("Disconnect Detection (Auto-Reconnect)")
        disconnect_form = QFormLayout(disconnect)
        self.general_disconnect_enabled = QCheckBox("Enable automatic reconnect")
        self.general_disconnect_enabled.setObjectName("general_disconnect_enabled")
        self.general_disconnect_x1 = self._number("general_disconnect_x1")
        self.general_disconnect_y1 = self._number("general_disconnect_y1")
        self.general_disconnect_x2 = self._number("general_disconnect_x2")
        self.general_disconnect_y2 = self._number("general_disconnect_y2")
        self.general_disconnect_text = QLineEdit()
        self.general_disconnect_text.setObjectName("general_disconnect_text")
        self.general_disconnect_reconnect_x = self._number("general_disconnect_reconnect_x")
        self.general_disconnect_reconnect_y = self._number("general_disconnect_reconnect_y")
        self.general_disconnect_interval = self._number("general_disconnect_interval")
        disconnect_form.addRow("", self.general_disconnect_enabled)
        disconnect_form.addRow("Region 1 X:", self.general_disconnect_x1)
        disconnect_form.addRow("Region 1 Y:", self.general_disconnect_y1)
        disconnect_form.addRow("Region 2 X:", self.general_disconnect_x2)
        disconnect_form.addRow("Region 2 Y:", self.general_disconnect_y2)
        disconnect_form.addRow("Expected text:", self.general_disconnect_text)
        disconnect_form.addRow("Reconnect X:", self.general_disconnect_reconnect_x)
        disconnect_form.addRow("Reconnect Y:", self.general_disconnect_reconnect_y)
        disconnect_form.addRow("Check every (sec):", self.general_disconnect_interval)
        layout.addWidget(disconnect)

        # "Enable remote bridge" lives in the Remote Agent tab now (see remote_agent_tab.py),
        # alongside the pairing/start/stop controls it gates - self.general_remote_bridge_enabled
        # is aliased to that checkbox in _build_ui.
        layout.addStretch(1)
        return page

    def _scrollable_page(self) -> tuple[QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        scroll.setWidget(inner)
        return scroll, layout

    @staticmethod
    def _button(text: str, callback: Any) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _number(object_name: str) -> QDoubleSpinBox:
        widget = NoScrollDoubleSpinBox()
        widget.setObjectName(object_name)
        widget.setRange(-1_000_000.0, 1_000_000.0)
        widget.setDecimals(4)
        widget.setSingleStep(1.0)
        return widget

    @staticmethod
    def _integer(object_name: str, minimum: int, maximum: int) -> QSpinBox:
        widget = NoScrollSpinBox()
        widget.setObjectName(object_name)
        widget.setRange(minimum, maximum)
        return widget

    @staticmethod
    def _editable_combo(object_name: str) -> QComboBox:
        widget = NoScrollComboBox()
        widget.setObjectName(object_name)
        widget.setEditable(True)
        return widget

    def _refresh_config(self) -> None:
        try:
            config = read_config(self.config_path)
        except (OSError, UnicodeError) as error:
            if self._config_loaded_once:
                # A config has already loaded successfully before; this failure is a later,
                # presumably transient read error (e.g. a sharing violation config_reader's own
                # retries didn't clear). Keep showing - and keep Save submitting - the last
                # known-good config instead of blanking it to defaults, which would otherwise get
                # written right back over the real config.ini on the next save.
                self.notice_label.setText(
                    f"config.ini could not be read just now ({error}). Showing the last known settings."
                )
            else:
                self.config = AppConfig(general=GeneralConfig())
                self.notice_label.setText(
                    f"config.ini in {self.data_dir} could not be read yet, so the fields below are "
                    f"placeholders, not your settings - saving is blocked until a read succeeds. "
                    f"Retrying every {STATUS_POLL_INTERVAL_MS} ms. ({error})"
                )
            self.notice_label.show()
        else:
            self.config = config
            self._config_loaded_once = True
            self.notice_label.hide()
        self._apply_config()

    def _apply_config(self) -> None:
        general = self.config.general
        with QSignalBlocker(self.preset_list), QSignalBlocker(self.map_profile_combo):
            self.preset_list.clear()
            self.preset_list.addItems([preset.name for preset in self.config.presets])
            self.map_profile_combo.clear()
            self.map_profile_combo.addItems([profile.name for profile in self.config.map_profiles])

        self._populate_general(general)
        self._populate_preset_choices()
        self._populate_map_profile_choices()
        self.active_preset_label.setText(f"Runs on Start: {self.config.active_preset or '-'}")

    def _all_option_names(self) -> list[str]:
        names: list[str] = []
        for preset in self.config.presets:
            for option in preset.options:
                if option.name and option.name not in names:
                    names.append(option.name)
        return names

    def _populate_general(self, general: GeneralConfig) -> None:
        widgets_and_values: list[tuple[Any, Any]] = [
            (self.general_round_wait, general.round_wait_seconds),
            (self.general_click_delay, general.click_delay_ms),
            (self.general_place_tower_delay, general.place_tower_delay_ms),
            (self.general_after_place_click, general.after_place_click),
            (self.general_after_place_x, general.after_place_click_x),
            (self.general_after_place_y, general.after_place_click_y),
            (self.general_max_rounds, general.max_rounds),
            (self.general_marker_size, general.marker_size),
            (self.general_num_placements, general.num_placements),
            (self.general_game_process, general.game_process),
            (self.general_hole_x, general.hole_x), (self.general_hole_y, general.hole_y),
            (self.general_hole_w, general.hole_w), (self.general_hole_h, general.hole_h),
            (self.general_disconnect_enabled, general.disconnect_enabled),
            (self.general_disconnect_x1, general.disconnect_x1), (self.general_disconnect_y1, general.disconnect_y1),
            (self.general_disconnect_x2, general.disconnect_x2), (self.general_disconnect_y2, general.disconnect_y2),
            (self.general_disconnect_text, general.disconnect_text),
            (self.general_disconnect_reconnect_x, general.disconnect_reconnect_x),
            (self.general_disconnect_reconnect_y, general.disconnect_reconnect_y),
            (self.general_disconnect_interval, general.disconnect_interval_sec),
            (self.general_remote_bridge_enabled, general.remote_bridge_enabled),
        ]
        for widget, value in widgets_and_values:
            self._set_widget_value(widget, value)
        # Deliberately NOT _all_option_names(): those are the preset's challenge option names, a
        # completely different concept that offered the wrong choices here and left a perfectly
        # valid saved slot looking unset. See TOWER_SLOT_CHOICES.
        for slot in self.general_slots:
            self._replace_combo_items(slot, list(TOWER_SLOT_CHOICES))
        for slot, value in zip(self.general_slots, general.slots):
            self._set_combo_text(slot, value if value in TOWER_SLOT_CHOICES else TOWER_SLOT_DEFAULT)

    def _populate_preset_choices(self) -> None:
        names = [preset.name for preset in self.config.presets]
        selected = self._selected_preset_name if self._selected_preset_name in names else self.config.active_preset
        if selected not in names:
            selected = names[0] if names else ""
        self._selected_preset_name = selected
        with QSignalBlocker(self.preset_list):
            matches = self.preset_list.findItems(selected, Qt.MatchFlag.MatchExactly)
            self.preset_list.setCurrentItem(matches[0] if matches else None)
        self._load_selected_preset()

    def _populate_map_profile_choices(self) -> None:
        names = [profile.name for profile in self.config.map_profiles]
        selected = self._selected_map_profile_name if self._selected_map_profile_name in names else self.config.active_map_profile
        if selected not in names:
            selected = names[0] if names else ""
        self._selected_map_profile_name = selected
        with QSignalBlocker(self.map_profile_combo):
            self.map_profile_combo.setCurrentText(selected)
        self._load_selected_map_profile()

    def _preset_selected(self, name: str) -> None:
        self._selected_preset_name = name
        self._load_selected_preset()

    def _map_profile_selected(self, name: str) -> None:
        self._selected_map_profile_name = name
        self._load_selected_map_profile()

    def _load_selected_preset(self) -> None:
        preset = self._selected_preset()
        map_names = [profile.name for profile in self.config.map_profiles]
        self._replace_combo_items(self.preset_default_map, [self._NONE_CHOICE, *map_names])
        if preset is None:
            self._set_widget_value(self.preset_back_x, 0)
            self._set_widget_value(self.preset_back_y, 0)
            self._set_combo_text(self.preset_default_map, self._NONE_CHOICE)
            self._set_combo_text(self.preset_fallback_screen, self._NONE_CHOICE)
            options = [OptionConfig() for _ in range(3)]
        else:
            self._set_widget_value(self.preset_back_x, preset.back_x)
            self._set_widget_value(self.preset_back_y, preset.back_y)
            self._set_combo_text(self.preset_default_map, preset.default_map or self._NONE_CHOICE)
            self._replace_combo_items(
                self.preset_fallback_screen, [self._NONE_CHOICE, *[screen.name for screen in preset.screens]]
            )
            self._set_combo_text(self.preset_fallback_screen, preset.fallback_screen or self._NONE_CHOICE)
            options = list(preset.options)
            options.extend(OptionConfig() for _ in range(3 - len(options)))
        for index, option in enumerate(options[:3]):
            for widget, value in (
                (self.preset_option_names[index], option.name),
                (self.preset_option_x[index], option.x),
                (self.preset_option_y[index], option.y),
                (self.preset_option_available[index], option.available),
                (self.preset_option_priority[index], option.priority),
                (self.usage_used[index], option.used_count),
                (self.usage_max[index], option.max_uses),
            ):
                self._set_widget_value(widget, value)

    def _load_selected_map_profile(self) -> None:
        profile = next((item for item in self.config.map_profiles if item.name == self._selected_map_profile_name), None)
        if profile is None:
            values = ("", False, 0, False)
            placements = []
        else:
            values = (profile.expected_text, profile.custom_towers, profile.custom_num_placements, profile.custom_camera)
            placements = profile.placements
        for widget, value in zip(
            (self.map_expected_text, self.map_custom_towers, self.map_num_placements, self.map_custom_camera), values,
        ):
            self._set_widget_value(widget, value)
        for row in range(10):
            placement = placements[row] if row < len(placements) else None
            row_values = (
                placement.custom_slot if placement else "",
                placement.x if placement else 0,
                placement.y if placement else 0,
            )
            for column, value in enumerate(row_values):
                self.placements_table.setItem(row, column, QTableWidgetItem(str(value)))
        self._update_placements_table_layout()

    def _update_placements_table_layout(self) -> None:
        count = self.map_num_placements.value() if self.map_custom_towers.isChecked() else self.general_num_placements.value()
        count = max(0, min(count, self.placements_table.rowCount()))
        for row in range(self.placements_table.rowCount()):
            self.placements_table.setRowHidden(row, row >= count)
        table_height = self.placements_table.horizontalHeader().height()
        table_height += self.placements_table.rowHeight(0) * count
        table_height += self.placements_table.frameWidth() * 2 + 2
        self.placements_table.setFixedHeight(table_height)

    def _poll_status(self) -> None:
        status = self.client.read_status()
        now = time.monotonic()
        if status is not None and status.timestamp != self._last_timestamp:
            self._last_timestamp = status.timestamp
            self._last_seen_wall_time = now
        self._update_status_area(status, now)
        # `or not self._config_loaded_once`: until ONE read has succeeded there is nothing to
        # detect a change against, so a first read that failed (a startup sharing violation while
        # the engine is still writing, a config.ini that does not exist yet) would otherwise leave
        # the window showing GeneralConfig() defaults permanently - change detection alone never
        # fires again if the file then sits unchanged. Keep retrying until one read lands; the
        # retry stops by itself the moment it does.
        # `or not self._config_loaded_once`: until ONE read has succeeded there is nothing to
        # detect a change against, so a first read that failed (a startup sharing violation while
        # the engine is still writing, a config.ini that does not exist yet) would otherwise leave
        # the window showing GeneralConfig() defaults permanently - change detection alone never
        # fires again once the file then sits unchanged. Keep retrying until one read lands; the
        # retry stops by itself the moment it does.
        if self.config_tracker.changed(status, self.config_path) or not self._config_loaded_once:
            self._refresh_config()

    def _update_status_area(self, status: LocalStatus | None, now: float) -> None:
        # Minimal run-state indicator only (Idle/Running/Paused): the detailed per-run fields
        # (active/running/queued preset, current map/screen/step, cycle and repeat counters,
        # victory/defeat counts) used to be spelled out here too, but were removed from this strip
        # outright (see tasklist/done/engine-status-remove-fields.md) as noise the user did not
        # want at the top of the window. The underlying LocalStatus fields are untouched: other
        # consumers (the remote website/agent, a future detailed-stats display) still read them.
        stale = self._last_seen_wall_time is None or now - self._last_seen_wall_time > STALE_STATUS_SECONDS
        if status is None or stale or not status.running:
            self.engine_status_label.setText("Idle")
            self.engine_status_label.setStyleSheet("font-weight: 700; color: #aeb8ca;")
        elif status.paused:
            self.engine_status_label.setText("Paused")
            self.engine_status_label.setStyleSheet("font-weight: 700; color: #f0c674;")
        else:
            self.engine_status_label.setText("Running")
            self.engine_status_label.setStyleSheet("font-weight: 700; color: #8ce99a;")

    def _save(self) -> None:
        # Refuse to save while no config has ever loaded: every widget is then showing a
        # GeneralConfig() default (all zeros, empty slots) that stands for "not read", NOT for a
        # real setting, so submitting them would overwrite a config.ini that is very likely
        # perfectly intact and merely unreadable at this moment. The already-loaded-once case is
        # deliberately still allowed - there the widgets hold the last known-good values.
        if not self._config_loaded_once:
            self._show_message(
                "Not saved: config.ini has not been read successfully yet, so the fields below are "
                "placeholders, not your settings. Saving now would overwrite your real config."
            )
            return

        preset = self._selected_preset()
        payloads: dict[str, Any] = {"general": self._general_payload()}
        if self._selected_map_profile_name:
            payloads["map_profile"] = self._map_profile_payload()
        if preset is not None:
            payloads["preset"] = self._preset_payload(preset)

        # One document, one backup, one atomic replace - see ipc/config_writer.save_config. The
        # three parts used to be three separate bridge commands, any of which could time out or be
        # rejected as busy on its own and leave the file half saved.
        try:
            message = self.client.save_config(**payloads)
        except ConfigValidationError as error:
            self._show_message(str(error))
            return
        except (OSError, ValueError) as error:
            self._show_message(f"Not saved: {error}")
            return
        self._adopt_saved_config()
        self._show_message(message)

    def _adopt_saved_config(self) -> None:
        """Re-read what was just written and stop the poll from re-applying it.

        The file this process wrote is complete the instant os.replace returns, so the config is
        refreshed here directly. Telling the tracker about the new mtime keeps the next poll from
        repopulating every widget from disk, which is what used to overwrite an edit the user made
        in the moments after pressing Save.
        """
        self._refresh_config()
        self.config_tracker.adopt(self.config_path)

    def _start(self) -> None:
        self._show_message(self._send(VERB_START, start_payload()))

    def _pause(self) -> None:
        self._show_message(self._send(VERB_PAUSE, pause_payload()))

    def _resume(self) -> None:
        self._show_message(self._send(VERB_RESUME, resume_payload()))

    def _stop(self) -> None:
        self._show_message(self._send(VERB_STOP, stop_payload()))

    def _refresh_game_processes(self) -> None:
        # Also runs once at startup (deferred, see __init__) before any engine may even be running -
        # pump Qt events during the wait so a slow/absent response never freezes the window solid,
        # matching the precedent already established for PAIR_REMOTE_AGENT's similarly long wait.
        # Disabling the button for the whole call (not just relying on the GUI being unresponsive)
        # matters once that wait pumps Qt events: a second click during the same wait must not
        # queue a duplicate LIST_GAME_PROCESSES with a fresh token while the first may still be in
        # flight - it would only ever be rejected as busy, but each rejection re-shows its own
        # message, which is what made this look permanently stuck. Mirrors RemoteAgentTab's
        # pair_button and the "Test OCR" buttons.
        self.general_game_process_refresh_button.setEnabled(False)
        try:
            message = self._send(
                VERB_LIST_GAME_PROCESSES, list_game_processes_payload(), pump=QApplication.processEvents
            )
        finally:
            self.general_game_process_refresh_button.setEnabled(True)
        self._show_message(message)
        if not message.startswith(f"{VERB_LIST_GAME_PROCESSES}: OK"):
            # local_game_processes.json has no token and persists across runs - reading it after a
            # failed/timed-out/busy send would risk showing a stale list from an earlier successful
            # refresh (possibly even an earlier session) as if it were fresh.
            return
        candidates = self.client.read_game_processes()
        self._replace_combo_items(
            self.general_game_process,
            [f"{candidate.title} | {candidate.process}" for candidate in candidates],
        )

    def _force_game_window(self) -> None:
        self._show_message(self._send(VERB_FORCE_GAME_WINDOW, force_game_window_payload()))

    def _general_payload(self) -> dict[str, Any]:
        return save_general_payload(
            round_wait_seconds=self.general_round_wait.value(),
            click_delay_ms=self.general_click_delay.value(),
            place_tower_delay_ms=self.general_place_tower_delay.value(),
            after_place_click=self.general_after_place_click.isChecked(),
            after_place_click_x=self.general_after_place_x.value(),
            after_place_click_y=self.general_after_place_y.value(),
            max_rounds=self.general_max_rounds.value(),
            marker_size=self.general_marker_size.value(),
            num_placements=self.general_num_placements.value(),
            slots=tuple(self._closed_combo_value(slot) for slot in self.general_slots),
            game_process=self._game_process_name_from_combo_text(self.general_game_process.currentText()),
            hole_x=self.general_hole_x.value(), hole_y=self.general_hole_y.value(),
            hole_w=self.general_hole_w.value(), hole_h=self.general_hole_h.value(),
            disconnect_enabled=self.general_disconnect_enabled.isChecked(),
            disconnect_x1=self.general_disconnect_x1.value(), disconnect_y1=self.general_disconnect_y1.value(),
            disconnect_x2=self.general_disconnect_x2.value(), disconnect_y2=self.general_disconnect_y2.value(),
            disconnect_text=self.general_disconnect_text.text(),
            disconnect_reconnect_x=self.general_disconnect_reconnect_x.value(),
            disconnect_reconnect_y=self.general_disconnect_reconnect_y.value(),
            disconnect_interval_sec=self.general_disconnect_interval.value(),
            remote_bridge_enabled=self.general_remote_bridge_enabled.isChecked(),
        )

    def _map_profile_payload(self) -> dict[str, Any]:
        placements: list[dict[str, Any]] = []
        for row in range(self.placements_table.rowCount()):
            def cell(column: int) -> str:
                item = self.placements_table.item(row, column)
                return item.text() if item is not None else ""

            placements.append({
                "customSlot": cell(0),
                "x": self._table_number(cell(1)),
                "y": self._table_number(cell(2)),
            })
        return save_map_profile_payload(
            name=self._selected_map_profile_name,
            expected_text=self.map_expected_text.text(),
            custom_towers=self.map_custom_towers.isChecked(),
            custom_num_placements=self.map_num_placements.value(),
            placements=placements,
            custom_camera=self.map_custom_camera.isChecked(),
        )

    def _capture_placement(self, row: int) -> None:
        try:
            captured = capture_point(self.client, self)
        except Exception as error:
            self._show_message(f"Capture failed: {error}")
            return
        if captured is None:
            self._show_message("Capture cancelled.")
            return
        x, y = captured
        self.placements_table.setItem(row, 1, QTableWidgetItem(str(x)))
        self.placements_table.setItem(row, 2, QTableWidgetItem(str(y)))

    def _preset_payload(self, preset: PresetConfig) -> dict[str, Any]:
        saved_options: list[OptionPayload] = []
        existing_options = list(preset.options)
        existing_options.extend(OptionConfig() for _ in range(3 - len(existing_options)))
        for index, option in enumerate(existing_options[:3]):
            saved_options.append(
                OptionPayload(
                    name=self.preset_option_names[index].text(),
                    x=self.preset_option_x[index].value(),
                    y=self.preset_option_y[index].value(),
                    available=self.preset_option_available[index].isChecked(),
                    priority=self.preset_option_priority[index].value(),
                    max_uses=self.usage_max[index].value(),
                    det_x=option.det_x, det_y=option.det_y,
                    det_end_x=option.det_end_x, det_end_y=option.det_end_y,
                    det_text=option.det_text, det_invert=option.det_invert,
                )
            )
        return save_preset_payload(
            name=preset.name,
            screens=preset_config_to_screens_payload(preset),
            options=saved_options,
            default_map=self._closed_combo_value(self.preset_default_map),
            back_x=self.preset_back_x.value(),
            back_y=self.preset_back_y.value(),
            fallback_screen=self._closed_combo_value(self.preset_fallback_screen),
        )

    def _usage_changed(self, index: int, value: int, is_maximum: bool) -> None:
        # Deliberately not routed through _run_local_mutation(): this fires on every spin-box edit,
        # and refreshing every widget from disk after each keystroke would fight the user's typing
        # the same way a naive Save-button poll used to (see ConfigChangeTracker's docstring).
        preset = self._selected_preset()
        if preset is None:
            return
        try:
            if is_maximum:
                message = self.client.set_option_max(preset.name, index + 1, value)
            else:
                message = self.client.set_option_used_count(preset.name, index + 1, value)
        except (MutationError, OSError) as error:
            self._show_message(f"Not saved: {error}")
            return
        self._show_message(message)

    def _new_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, "New Preset", "Preset name:")
        if accepted and name.strip():
            self._run_local_mutation(lambda: self.client.create_preset(name.strip()))

    def _rename_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self._show_message("Select a preset first.")
            return
        name, accepted = QInputDialog.getText(self, "Rename Preset", "New preset name:", text=preset.name)
        if accepted and name.strip() and name.strip() != preset.name:
            self._run_local_mutation(lambda: self.client.rename_preset(preset.name, name.strip()))

    def _delete_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self._show_message("Select a preset first.")
            return
        answer = QMessageBox.question(self, "Delete Preset", f"Delete preset '{preset.name}'?")
        if answer == QMessageBox.StandardButton.Yes:
            self._run_local_mutation(lambda: self.client.delete_preset(preset.name))

    def _export_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self._show_message("Select a preset first.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Preset", f"{preset.name}.ini", "Preset files (*.ini)",
        )
        if not file_path:
            return
        self._run_local_mutation(lambda: self.client.export_preset(preset.name, file_path))

    def _import_preset(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Preset", "", "Preset files (*.ini);;All files (*)",
        )
        if not file_path:
            return
        default_name = Path(file_path).stem
        new_name, accepted = QInputDialog.getText(
            self, "Import Preset", "New preset name:", text=default_name,
        )
        if accepted and new_name.strip():
            self._run_local_mutation(lambda: self.client.import_preset(file_path, new_name.strip()))

    def _set_active_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self._show_message("Select a preset first.")
            return
        self._run_mutation(VERB_SET_ACTIVE_PRESET, set_active_preset_payload(preset.name))

    def _edit_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self._show_message("Select a preset first.")
            return
        existing = self._edit_preset_windows.get(preset.name)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        # Deliberately no Qt parent: see make_independently_minimizable in app/widgets.py -
        # a parented QDialog becomes a native Windows "owned window" that minimizes together
        # with the main window, which is exactly what this window must not do.
        window = EditPresetWindow(
            preset, self.client, [item.name for item in self.config.presets],
            [item.name for item in self.config.map_profiles],
        )
        window.saved.connect(self._refresh_config)
        window.finished.connect(lambda *_: self._edit_preset_windows.pop(preset.name, None))
        self._edit_preset_windows[preset.name] = window
        window.show()

    def _open_map_advanced(self) -> None:
        profile = next(
            (item for item in self.config.map_profiles if item.name == self._selected_map_profile_name),
            None,
        )
        if profile is None:
            self._show_message("Select a map profile first.")
            return
        existing = self._map_advanced_windows.get(profile.name)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        # A profile with custom camera OFF edits the SHARED "General" action list, not its own -
        # two different profiles both currently non-custom would otherwise get two independent
        # editors for that SAME underlying data, and whichever saves last would silently discard
        # the other's changes. Reuse whichever already-open window is presently editing the same
        # effective section (which can change at runtime if that window's own checkbox is toggled),
        # not just one keyed by this exact profile name.
        target_section = f"MapProfile_{profile.name}" if profile.custom_camera else "General"
        for other in self._map_advanced_windows.values():
            if other._effective_section == target_section:
                other.show()
                other.raise_()
                other.activateWindow()
                return
        # Deliberately no Qt parent: see make_independently_minimizable in app/widgets.py -
        # a parented QDialog becomes a native Windows "owned window" that minimizes together
        # with the main window, which is exactly what this window must not do. config_source
        # replaces the parent as this window's way to reach MainWindow's live config.
        window = MapAdvancedWindow(
            profile.name, self.client, profile=profile, general=self.config.general, config_source=self,
        )
        window.saved.connect(self._refresh_config)
        window.finished.connect(lambda *_: self._map_advanced_windows.pop(profile.name, None))
        self._map_advanced_windows[profile.name] = window
        window.show()

    def _new_map_profile(self) -> None:
        name, accepted = QInputDialog.getText(self, "New Map Profile", "Map profile name:")
        if accepted and name.strip():
            self._run_local_mutation(lambda: self.client.create_map_profile(name.strip()))

    def _rename_map_profile(self) -> None:
        profile = self._selected_map_profile_name
        if not profile:
            self._show_message("Select a map profile first.")
            return
        name, accepted = QInputDialog.getText(self, "Rename Map Profile", "New map profile name:", text=profile)
        if accepted and name.strip() and name.strip() != profile:
            self._run_local_mutation(lambda: self.client.rename_map_profile(profile, name.strip()))

    def _delete_map_profile(self) -> None:
        profile = self._selected_map_profile_name
        if not profile:
            self._show_message("Select a map profile first.")
            return
        answer = QMessageBox.question(self, "Delete Map Profile", f"Delete map profile '{profile}'?")
        if answer == QMessageBox.StandardButton.Yes:
            self._run_local_mutation(lambda: self.client.delete_map_profile(profile))

    def _run_mutation(self, verb: str, payload: dict[str, Any]) -> None:
        message = self._send(verb, payload)
        self._show_message(message)
        if message.startswith(f"{verb}: OK"):
            self._refresh_config()

    def _run_local_mutation(self, action: Callable[[], str]) -> None:
        """Run a structural config.ini mutation (create/rename/delete/export/import) locally.

        Counterpart of _run_mutation() for the operations config_writer.py now performs directly
        instead of sending a bridge command - see create_preset()/rename_preset()/etc. there.
        """
        try:
            message = action()
        except (MutationError, OSError) as error:
            self._show_message(f"Not saved: {error}")
            return
        self._show_message(message)
        self._refresh_config()

    def _send(self, verb: str, payload: dict[str, Any], *, pump: Any = None) -> str:
        # `pump` is only forwarded when given, not passed through as an explicit pump=None on every
        # call - existing tests assert send_command's exact call args (verb, payload) with no kwargs.
        kwargs = {"pump": pump} if pump is not None else {}
        try:
            ack = self.client.send_command(verb, payload, **kwargs)
        except IpcTimeoutError:
            # A timeout means unknown outcome, not "definitely failed" (see IpcTimeoutError's
            # docstring) - AHK may still apply the command after this returns. Say so explicitly
            # rather than showing the same wording as a real rejection, so a user isn't misled
            # into confidently retrying a mutation (rename/delete) that might still land.
            return f"{verb}: timed out - outcome unknown, check status before retrying"
        except IpcBusyError as error:
            return f"{verb}: not sent ({error})"
        except Exception as error:
            return f"{verb}: failed ({error})"
        result = "OK" if ack.ok else "failed"
        suffix = ack.message or result
        return f"{verb}: {result} ({suffix})"

    def _show_message(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    def _selected_preset(self) -> PresetConfig | None:
        return next((preset for preset in self.config.presets if preset.name == self._selected_preset_name), None)

    @staticmethod
    def _set_widget_value(widget: Any, value: Any) -> None:
        with QSignalBlocker(widget):
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(value)
            elif isinstance(widget, QComboBox):
                MainWindow._set_combo_text(widget, str(value))

    @staticmethod
    def _set_combo_text(widget: QComboBox, value: str) -> None:
        with QSignalBlocker(widget):
            if value and widget.findText(value) < 0:
                widget.addItem(value)
            widget.setCurrentText(value)

    @classmethod
    def _closed_combo_value(cls, widget: QComboBox) -> str:
        """Read back a select-only combo populated with the `_NONE_CHOICE` placeholder.

        `_set_combo_text` shows an empty saved value as `_NONE_CHOICE` because a non-editable
        combo can't otherwise display or re-select "" from its item list; translate it back to
        "" here so the placeholder text never leaks into config.ini.
        """
        text = widget.currentText()
        return "" if text == cls._NONE_CHOICE else text

    @staticmethod
    def _game_process_name_from_combo_text(text: str) -> str:
        """Recover the bare process name from a "<title> | <process>" combo entry.

        general_game_process is populated with "<title> | <process>" so a user can tell
        apart windows sharing a generic title, but only the process name half is ever
        meaningful to save - AHK's ForceGameWindow() matches it against a real running
        process' executable name. A manually typed value (no " | " present, e.g. the
        combo's own game process isn't currently running) is used as-is.
        """
        text = text.strip()
        return text.rsplit(" | ", 1)[-1].strip() if " | " in text else text

    @staticmethod
    def _replace_combo_items(widget: QComboBox, values: list[str]) -> None:
        current = widget.currentText()
        with QSignalBlocker(widget):
            widget.clear()
            widget.addItems(values)
            widget.setCurrentText(current)

    @staticmethod
    def _table_number(value: str) -> int | float:
        try:
            number = float(value.strip().replace(",", "."))
        except ValueError:
            return 0
        return int(number) if number.is_integer() else number

    def closeEvent(self, event: Any) -> None:
        self.status_timer.stop()
        # Defense in depth: the Remote Agent tab is part of this window's own widget tree now
        # (not a separate top-level QDialog), so it is not reached by the sweep below - clear any
        # password/2FA text still sitting in its fields explicitly before the process exits.
        self.remote_agent_tab._clear_secret_fields()
        # Edit Preset / Map Advanced windows are QDialogs shown non-modally (.show()), so each
        # one is its own top-level widget as far as Qt's quitOnLastWindowClosed is concerned. Left
        # open, any one of them would keep the whole process - and the engine it manages - alive
        # after the user closes only the main window. Sweeping every top-level widget (not just
        # the collections this class tracks directly) also reaches windows nested a level deeper,
        # like EditPresetWindow's own Option Availability picker: that dialog is shown
        # independently via .open() and is never closed by its parent's close(), so leaving it
        # open kept the process alive with no visible window left for the user to think to close.
        for widget in QApplication.topLevelWidgets():
            if widget is not self and widget.isVisible():
                widget.close()
        super().closeEvent(event)
