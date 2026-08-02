from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.main_window import TOWER_SLOT_CHOICES, TOWER_SLOT_DEFAULT, MainWindow
from app.map_advanced_window import MapAdvancedWindow
from app.remote_agent_tab import RemoteAgentTab
from ipc.client import CommandAck, IpcTimeoutError
from ipc.config_writer import MutationError
from ipc.protocol import (
    GameProcessCandidate,
    VERB_FORCE_GAME_WINDOW,
    VERB_LIST_GAME_PROCESSES,
    VERB_PAUSE,
    VERB_RESUME,
    VERB_START,
    VERB_STOP,
    force_game_window_payload,
    list_game_processes_payload,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _client() -> MagicMock:
    client = MagicMock()
    client.read_status.return_value = None
    client.send_command.return_value = CommandAck("test", True, "accepted", {})
    # config.ini is written by this process now, not by a bridge command, so the fakes have to
    # return real status-bar strings rather than MagicMocks.
    client.save_config.return_value = "Saved: general settings."
    client.create_preset.return_value = "Preset created."
    client.rename_preset.return_value = "Preset renamed."
    client.delete_preset.return_value = "Preset deleted."
    client.export_preset.return_value = "Preset exported."
    client.import_preset.return_value = "Preset imported."
    client.create_map_profile.return_value = "Map profile created."
    client.rename_map_profile.return_value = "Map profile renamed."
    client.delete_map_profile.return_value = "Map profile deleted."
    client.set_option_used_count.return_value = "Option usage count saved."
    client.set_option_max.return_value = "Option maximum saved."
    return client


def test_window_constructs_with_fixture_and_populates_general_values(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    assert window.general_round_wait.value() == 12.5
    assert window.general_click_delay.value() == 150
    assert window.general_game_process.currentText() == "RobloxPlayerBeta.exe"
    assert window.general_remote_bridge_enabled.isChecked()


def test_edit_preset_reuses_existing_window_instead_of_opening_a_duplicate(qtbot, tmp_path: Path) -> None:
    # Regression test: clicking "Edit..." twice used to spawn a second independent in-memory
    # editor for the same preset - whichever one saved last would silently discard the other's edits.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.preset_list.setCurrentRow(0)
    window._edit_preset()
    first = window._edit_preset_windows[window._selected_preset_name]

    window._edit_preset()
    second = window._edit_preset_windows[window._selected_preset_name]
    assert second is first

    first.close()
    assert window._selected_preset_name not in window._edit_preset_windows


def test_map_advanced_reuses_existing_window_instead_of_opening_a_duplicate(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.map_profile_combo.setCurrentText("Forest Map")
    qtbot.mouseClick(window.map_advanced_button, Qt.MouseButton.LeftButton)
    first = window._map_advanced_windows[window._selected_map_profile_name]
    assert isinstance(first, MapAdvancedWindow)

    qtbot.mouseClick(window.map_advanced_button, Qt.MouseButton.LeftButton)
    second = window._map_advanced_windows[window._selected_map_profile_name]
    assert second is first

    first.close()
    assert window._selected_map_profile_name not in window._map_advanced_windows


def test_remote_agent_tab_is_mounted_in_the_tab_bar(qtbot, tmp_path: Path) -> None:
    # Regression guard for the window -> tab conversion: Remote Agent used to be a separate
    # QDialog opened on demand from a bottom-strip button; it is now permanent tab content
    # mounted alongside Preset Settings / Map Placement / General.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    assert isinstance(window.remote_agent_tab, RemoteAgentTab)
    assert window.tabs.indexOf(window.remote_agent_tab) != -1
    assert window.tabs.tabText(window.tabs.indexOf(window.remote_agent_tab)) == "Remote Agent"
    # "Enable remote bridge" moved into this tab; _populate_general()/_general_payload() keep
    # addressing it by the same attribute name they always did.
    assert window.general_remote_bridge_enabled is window.remote_agent_tab.remote_bridge_enabled_checkbox


def test_closing_the_main_window_also_closes_open_secondary_windows(qtbot, tmp_path: Path) -> None:
    # Regression test: Edit Preset / Map Advanced windows are QDialogs shown non-modally, so each
    # one is its own top-level widget for Qt's quitOnLastWindowClosed - leaving any of them open
    # kept the whole process (and the engine it manages) alive after the user closed only the
    # main window. The Remote Agent tab is not part of this sweep - it lives inside MainWindow's
    # own widget tree, not as a separate top-level window - see the next test for its own
    # close-time cleanup.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.preset_list.setCurrentRow(0)
    window._edit_preset()
    edit_preset_window = window._edit_preset_windows[window._selected_preset_name]

    window.map_profile_combo.setCurrentText("Forest Map")
    qtbot.mouseClick(window.map_advanced_button, Qt.MouseButton.LeftButton)
    map_advanced_window = window._map_advanced_windows[window._selected_map_profile_name]

    assert edit_preset_window.isVisible()
    assert map_advanced_window.isVisible()

    window.close()

    assert not edit_preset_window.isVisible()
    assert not map_advanced_window.isVisible()


def test_closing_the_main_window_clears_remote_agent_secret_fields(qtbot, tmp_path: Path) -> None:
    # Defense in depth carried over from when Remote Agent was its own QDialog (it used to clear
    # these on its own .finished signal): closing the main window is now the only "this is done"
    # moment the Remote Agent tab has, so MainWindow.closeEvent clears them explicitly instead.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.remote_agent_tab.password_edit.setText("secret")
    window.remote_agent_tab.totp_edit.setText("123456")

    window.close()

    assert window.remote_agent_tab.password_edit.text() == ""
    assert window.remote_agent_tab.totp_edit.text() == ""


def test_closing_the_main_window_also_closes_windows_nested_inside_secondary_windows(
    qtbot, tmp_path: Path,
) -> None:
    # Regression test: the Option Availability picker is nested inside StepEditWindow, itself
    # inside EditPresetWindow, and shown independently via .open(), not tracked in any MainWindow
    # collection. QDialog.close() does not close its children, so it stayed open (and thus kept
    # the whole process alive) even though closing the main window closed the Edit Preset window.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.preset_list.setCurrentRow(0)
    window._edit_preset()
    edit_preset_window = window._edit_preset_windows[window._selected_preset_name]
    step_editor = edit_preset_window._open_step_editor_for_search()
    step_editor._open_option_availability(0)
    option_availability_window = step_editor.option_availability_window

    assert option_availability_window.isVisible()

    window.close()

    assert not option_availability_window.isVisible()


def test_window_constructs_without_config_and_reports_stopped(qtbot, tmp_path: Path) -> None:
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)

    window._poll_status()
    assert not window.notice_label.isHidden()
    assert window.engine_status_label.text() == "Idle"


def test_refresh_config_keeps_last_known_good_config_after_a_later_transient_failure(
    qtbot, tmp_path: Path,
) -> None:
    # Regression test: a read failure well after startup (e.g. the status-poll timer noticing a
    # config.ini mtime change mid-save) used to blank self.config to defaults unconditionally. If
    # the user hit Save right after, those blanked defaults would overwrite the real config.ini.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()
    assert window.config.general.round_wait_seconds == 12.5

    with patch("app.main_window.read_config", side_effect=OSError(13, "Permission denied")):
        window._refresh_config()

    assert window.config.general.round_wait_seconds == 12.5
    assert not window.notice_label.isHidden()
    assert "last known settings" in window.notice_label.text()


def test_a_failed_first_config_read_recovers_on_a_later_poll(qtbot, tmp_path: Path) -> None:
    # Regression test: change detection has nothing to compare against until one read has
    # succeeded, so a first read that failed (startup sharing violation, config.ini not written
    # yet) used to leave the window showing GeneralConfig() defaults permanently - the file then
    # sat unchanged, so changed() never fired again and _refresh_config was never retried.
    config_path = tmp_path / "config.ini"
    shutil.copyfile(FIXTURE, config_path)
    with patch("app.main_window.read_config", side_effect=PermissionError(13, "Permission denied")):
        window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
        qtbot.addWidget(window)
        window.show()
        # Poll until the change tracker has fully settled on this untouched file, so it now
        # reports "nothing changed". Without that, ConfigChangeTracker's own two-poll mtime
        # debounce would report a change on the next poll anyway and mask the bug under test.
        for _ in range(4):
            window._poll_status()
        assert window.config_tracker.changed(None, config_path) is False
        # The placeholder state: nothing loaded, everything at dataclass defaults.
        assert window.config.general.round_wait_seconds == 0
        assert not window.notice_label.isHidden()

    # config.ini is untouched, so change detection alone reports nothing and would never refresh
    # again - only the never-loaded retry can rescue this.
    window._poll_status()

    assert window.config.general.round_wait_seconds == 12.5
    assert window.notice_label.isHidden()


def test_save_is_blocked_while_no_config_has_ever_loaded(qtbot, tmp_path: Path) -> None:
    # The all-defaults placeholder state must never be submitted: it means "not read", not "these
    # are the settings", and SAVE_GENERAL would write those zeros over an intact config.ini.
    client = _client()
    with patch("app.main_window.read_config", side_effect=PermissionError(13, "Permission denied")):
        window = MainWindow(tmp_path, client=client, auto_refresh_game_processes=False)
        qtbot.addWidget(window)
        window.show()
        client.send_command.reset_mock()

        qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    client.send_command.assert_not_called()
    client.save_config.assert_not_called()
    assert "Not saved" in window.statusBar().currentMessage()


def test_save_writes_the_config_itself_and_start_still_goes_over_the_bridge(
    qtbot, tmp_path: Path
) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)

    # Saving is a local file write: no SAVE_* command may reach the bridge any more.
    verbs = [call.args[0] for call in client.send_command.call_args_list]
    assert VERB_START in verbs
    assert not [verb for verb in verbs if verb.startswith("SAVE_")]

    client.save_config.assert_called_once()
    payloads = client.save_config.call_args.kwargs
    general_payload = payloads["general"]
    assert general_payload["roundWaitSeconds"] == 12.5
    assert len(general_payload["slots"]) == 10
    preset_payload = payloads["preset"]
    assert len(preset_payload["options"]) == 3
    assert preset_payload["screens"] == [{"name": "Alt Screen", "steps": [{
        "type": "Button Click", "label": "Alternate click", "x": 66, "y": 77,
        "endX": 0, "endY": 0, "dragMs": 0, "oncePerCycle": False,
        "seconds": 0, "onTrueScreen": "", "onFalseScreen": "",
        "fallbackEnabled": False, "fallbackMaxAttempts": 0,
        "fallbackScreen": "", "advanced": False, "outcomesRaw": "",
    }]}]


def test_pause_resume_stop_send_expected_commands(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.pause_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.resume_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.stop_button, Qt.MouseButton.LeftButton)

    verbs = [call.args[0] for call in client.send_command.call_args_list]
    assert VERB_PAUSE in verbs
    assert VERB_RESUME in verbs
    assert VERB_STOP in verbs


def test_export_preset_writes_locally_with_the_dialog_chosen_path(qtbot, tmp_path: Path) -> None:
    # Regression test: these buttons used to be permanently disabled with a "not implemented yet"
    # tooltip even though the AHK-side EXPORT_PRESET/IMPORT_PRESET handlers were fully built.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    window.preset_list.setCurrentRow(0)
    preset_name = window._selected_preset_name
    export_path = str(tmp_path / "exported.ini")
    with patch("app.main_window.QFileDialog.getSaveFileName", return_value=(export_path, "")):
        qtbot.mouseClick(window.preset_export_button, Qt.MouseButton.LeftButton)

    client.export_preset.assert_called_once_with(preset_name, export_path)
    client.send_command.assert_not_called()


def test_import_preset_writes_locally_with_the_dialog_chosen_path_and_name(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    import_path = str(tmp_path / "incoming.ini")
    with patch("app.main_window.QFileDialog.getOpenFileName", return_value=(import_path, "")), \
         patch("app.main_window.QInputDialog.getText", return_value=("Imported Preset", True)):
        qtbot.mouseClick(window.preset_import_button, Qt.MouseButton.LeftButton)

    client.import_preset.assert_called_once_with(import_path, "Imported Preset")
    client.send_command.assert_not_called()


def test_new_rename_delete_preset_write_locally_and_refresh(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    with patch("app.main_window.QInputDialog.getText", return_value=("New Preset", True)):
        qtbot.mouseClick(window.preset_new_button, Qt.MouseButton.LeftButton)
    client.create_preset.assert_called_once_with("New Preset")

    window.preset_list.setCurrentRow(0)
    preset_name = window._selected_preset_name
    with patch("app.main_window.QInputDialog.getText", return_value=("Renamed Preset", True)):
        qtbot.mouseClick(window.preset_rename_button, Qt.MouseButton.LeftButton)
    client.rename_preset.assert_called_once_with(preset_name, "Renamed Preset")

    with patch("app.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        qtbot.mouseClick(window.preset_delete_button, Qt.MouseButton.LeftButton)
    client.delete_preset.assert_called_once_with(preset_name)
    assert "Preset deleted." in window.statusBar().currentMessage()
    client.send_command.assert_not_called()


def test_preset_mutation_error_is_shown_without_crashing(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    client.create_preset.side_effect = MutationError("A preset with this name already exists.")
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    with patch("app.main_window.QInputDialog.getText", return_value=("Existing", True)):
        qtbot.mouseClick(window.preset_new_button, Qt.MouseButton.LeftButton)

    assert "already exists" in window.statusBar().currentMessage()


def test_new_rename_delete_map_profile_write_locally(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    with patch("app.main_window.QInputDialog.getText", return_value=("New Map", True)):
        qtbot.mouseClick(window.map_new_button, Qt.MouseButton.LeftButton)
    client.create_map_profile.assert_called_once_with("New Map")

    profile_name = window._selected_map_profile_name
    with patch("app.main_window.QInputDialog.getText", return_value=("Renamed Map", True)):
        qtbot.mouseClick(window.map_rename_button, Qt.MouseButton.LeftButton)
    client.rename_map_profile.assert_called_once_with(profile_name, "Renamed Map")

    with patch("app.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        qtbot.mouseClick(window.map_delete_button, Qt.MouseButton.LeftButton)
    client.delete_map_profile.assert_called_once_with(profile_name)
    client.send_command.assert_not_called()


def test_usage_count_and_max_edits_write_locally_without_refreshing(qtbot, tmp_path: Path) -> None:
    # Deliberately not asserting a refresh happened: _usage_changed must not re-read config.ini on
    # every keystroke (see main_window._usage_changed's own comment).
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    window.preset_list.setCurrentRow(0)
    preset_name = window._selected_preset_name
    window.usage_used[0].setValue(3)
    client.set_option_used_count.assert_called_with(preset_name, 1, 3)

    window.usage_max[0].setValue(9)
    client.set_option_max.assert_called_with(preset_name, 1, 9)
    client.send_command.assert_not_called()


def test_placement_capture_button_populates_its_row(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    button = window.placements_table.cellWidget(3, 3)
    assert button is not None
    with patch("app.main_window.capture_point", return_value=(12.5, 34.25)) as capture:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    capture.assert_called_once_with(client, window)
    assert window.placements_table.item(3, 1).text() == "12.5"
    assert window.placements_table.item(3, 2).text() == "34.25"


def test_placements_table_visibility_tracks_map_and_general_counts(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.map_profile_combo.setCurrentText("Forest Map")
    assert [not window.placements_table.isRowHidden(row) for row in range(3)] == [True] * 3
    assert [window.placements_table.isRowHidden(row) for row in range(3, 10)] == [True] * 7

    window.map_profile_combo.setCurrentText("Desert Map")
    assert [not window.placements_table.isRowHidden(row) for row in range(6)] == [True] * 6
    assert [window.placements_table.isRowHidden(row) for row in range(6, 10)] == [True] * 4


def test_refresh_game_processes_replaces_the_general_process_choices(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    client.read_game_processes.return_value = [
        GameProcessCandidate("Roblox", "RobloxPlayerBeta.exe"),
        GameProcessCandidate("Roblox Alt", "RobloxPlayerBeta-alt.exe"),
    ]
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()
    client.send_command.reset_mock()

    qtbot.mouseClick(window.general_game_process_refresh_button, Qt.MouseButton.LeftButton)

    assert [window.general_game_process.itemText(index) for index in range(window.general_game_process.count())] == [
        "Roblox | RobloxPlayerBeta.exe", "Roblox Alt | RobloxPlayerBeta-alt.exe",
    ]
    client.send_command.assert_called_once_with(
        VERB_LIST_GAME_PROCESSES, list_game_processes_payload(), pump=QApplication.processEvents,
    )


def test_refresh_game_processes_disables_the_button_while_the_command_is_in_flight(
    qtbot, tmp_path: Path,
) -> None:
    # Regression test: a second click during the pumped wait used to queue a duplicate
    # LIST_GAME_PROCESSES that could only ever be rejected as busy, making the status bar look
    # permanently stuck even though any single busy message clears on its own.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    seen_enabled: list[bool] = []

    class RecordingClient:
        def read_status(self):
            return None

        def read_game_processes(self):
            return []

        def send_command(self, verb, payload, timeout=5.0, pump=None):
            seen_enabled.append(window.general_game_process_refresh_button.isEnabled())
            return CommandAck("test", True, "accepted", {})

    client = RecordingClient()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.general_game_process_refresh_button, Qt.MouseButton.LeftButton)

    assert seen_enabled and seen_enabled[-1] is False
    assert window.general_game_process_refresh_button.isEnabled()


def test_refresh_game_processes_ignores_a_reentrant_click_during_the_pumped_wait(
    qtbot, tmp_path: Path,
) -> None:
    # This is the actual reported bug: the pumped wait lets Qt deliver a second click while the
    # first send_command is still in flight. Because the button is disabled by then, Qt never
    # even emits a second clicked signal - send_command must only ever be invoked once.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    call_count = 0

    class ReentrantClient:
        def read_status(self):
            return None

        def read_game_processes(self):
            return []

        def send_command(self, verb, payload, timeout=5.0, pump=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and pump is not None:
                qtbot.mouseClick(window.general_game_process_refresh_button, Qt.MouseButton.LeftButton)
                pump()
            return CommandAck("test", True, "accepted", {})

    client = ReentrantClient()
    window = MainWindow(tmp_path, client=client, auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.general_game_process_refresh_button, Qt.MouseButton.LeftButton)

    assert call_count == 1
    assert window.general_game_process_refresh_button.isEnabled()


def test_refresh_game_processes_reenables_the_button_after_a_failed_send(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")

    class TimingOutClient:
        def read_status(self):
            return None

        def read_game_processes(self):
            return []

        def send_command(self, verb, payload, timeout=5.0, pump=None):
            raise IpcTimeoutError("simulated timeout")

    window = MainWindow(tmp_path, client=TimingOutClient())
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.general_game_process_refresh_button, Qt.MouseButton.LeftButton)

    assert window.general_game_process_refresh_button.isEnabled()


def test_general_tower_slots_offer_the_engines_hotbar_positions(qtbot, tmp_path: Path) -> None:
    # Regression test: these used to be populated from _all_option_names() (the preset's challenge
    # option names), a completely different concept. The dropdown therefore offered choices the
    # engine cannot use, while the real saved slot value was not among them.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()

    for slot in window.general_slots:
        assert [slot.itemText(index) for index in range(slot.count())] == list(TOWER_SLOT_CHOICES)
    assert [slot.currentText() for slot in window.general_slots] == [
        "3", "1", "6", "2", "4", "5", "1", "1", "1", "1",
    ]
    # The saved values must survive a round trip untouched, not be coerced or blanked on save.
    assert window._general_payload()["slots"] == ["3", "1", "6", "2", "4", "5", "1", "1", "1", "1"]


def test_general_tower_slot_falls_back_to_the_engine_default_for_an_unusable_value(
    qtbot, tmp_path: Path,
) -> None:
    # A slot value outside "1".."6" (a leftover name from before this was a fixed list, or an
    # empty key) is meaningless to the engine, which coerces it to "1" via SetDdlTextSafe. Match
    # that instead of showing a value the dropdown cannot represent.
    source = (FIXTURE).read_text(encoding="utf-16")
    (tmp_path / "config.ini").write_text(
        source.replace("Slot1=3", "Slot1=Alpha").replace("Slot2=1", "Slot2="),
        encoding="utf-16",
    )
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()

    assert window.general_slots[0].currentText() == TOWER_SLOT_DEFAULT
    assert window.general_slots[1].currentText() == TOWER_SLOT_DEFAULT


def test_general_tower_slots_are_all_the_same_width(qtbot, tmp_path: Path) -> None:
    # Regression test: "Number of placements:" and "Default slots..." used to sit in only the
    # grid's first one/two columns, forcing those columns (and so general_slots[0]) wider than the
    # rest of the ten slot fields.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()

    widths = [slot.width() for slot in window.general_slots]
    assert len(set(widths)) == 1


def test_pin_button_forces_the_game_window(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()
    client.send_command.reset_mock()

    qtbot.mouseClick(window.pin_button, Qt.MouseButton.LeftButton)

    client.send_command.assert_called_once_with(VERB_FORCE_GAME_WINDOW, force_game_window_payload())
