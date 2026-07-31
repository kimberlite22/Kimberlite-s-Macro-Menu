from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.main_window import TOWER_SLOT_CHOICES, TOWER_SLOT_DEFAULT, MainWindow
from app.map_advanced_window import MapAdvancedWindow
from app.remote_agent_window import RemoteAgentWindow
from ipc.client import CommandAck, IpcTimeoutError
from ipc.protocol import (
    GameProcessCandidate,
    VERB_EXPORT_PRESET,
    VERB_FORCE_GAME_WINDOW,
    VERB_IMPORT_PRESET,
    VERB_LIST_GAME_PROCESSES,
    VERB_PAUSE,
    VERB_RESUME,
    VERB_SAVE_GENERAL,
    VERB_SAVE_PRESET,
    VERB_START,
    VERB_STOP,
    export_preset_payload,
    force_game_window_payload,
    import_preset_payload,
    list_game_processes_payload,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _client() -> MagicMock:
    client = MagicMock()
    client.read_status.return_value = None
    client.send_command.return_value = CommandAck("test", True, "accepted", {})
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


def test_remote_agent_setup_reuses_its_existing_window(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.remote_agent_setup_button, Qt.MouseButton.LeftButton)
    first = window._remote_agent_window
    assert isinstance(first, RemoteAgentWindow)

    qtbot.mouseClick(window.remote_agent_setup_button, Qt.MouseButton.LeftButton)
    assert window._remote_agent_window is first

    first.close()
    assert window._remote_agent_window is None


def test_closing_the_main_window_also_closes_open_secondary_windows(qtbot, tmp_path: Path) -> None:
    # Regression test: Edit Preset / Map Advanced / Remote Agent windows are QDialogs shown
    # non-modally, so each one is its own top-level widget for Qt's quitOnLastWindowClosed -
    # leaving any of them open kept the whole process (and the engine it manages) alive after the
    # user closed only the main window.
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

    qtbot.mouseClick(window.remote_agent_setup_button, Qt.MouseButton.LeftButton)
    remote_agent_window = window._remote_agent_window

    assert edit_preset_window.isVisible()
    assert map_advanced_window.isVisible()
    assert remote_agent_window.isVisible()

    window.close()

    assert not edit_preset_window.isVisible()
    assert not map_advanced_window.isVisible()
    assert not remote_agent_window.isVisible()


def test_window_constructs_without_config_and_reports_stopped(qtbot, tmp_path: Path) -> None:
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)

    window._poll_status()
    assert not window.notice_label.isHidden()
    assert window.engine_status_label.text() == "Stopped"


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


def test_save_and_start_send_expected_commands(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)

    calls = client.send_command.call_args_list
    verbs = [call.args[0] for call in calls]
    assert VERB_SAVE_GENERAL in verbs
    assert VERB_SAVE_PRESET in verbs
    assert VERB_START in verbs
    general_payload = next(call.args[1] for call in calls if call.args[0] == VERB_SAVE_GENERAL)
    assert general_payload["roundWaitSeconds"] == 12.5
    assert len(general_payload["slots"]) == 10
    preset_payload = next(call.args[1] for call in calls if call.args[0] == VERB_SAVE_PRESET)
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


def test_export_preset_sends_export_command_with_the_dialog_chosen_path(qtbot, tmp_path: Path) -> None:
    # Regression test: these buttons used to be permanently disabled with a "not implemented yet"
    # tooltip even though the AHK-side EXPORT_PRESET/IMPORT_PRESET handlers were fully built.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()
    client.send_command.reset_mock()

    window.preset_list.setCurrentRow(0)
    preset_name = window._selected_preset_name
    export_path = str(tmp_path / "exported.ini")
    with patch("app.main_window.QFileDialog.getSaveFileName", return_value=(export_path, "")):
        qtbot.mouseClick(window.preset_export_button, Qt.MouseButton.LeftButton)

    client.send_command.assert_called_once_with(
        VERB_EXPORT_PRESET, export_preset_payload(preset_name, export_path),
    )


def test_import_preset_sends_import_command_with_the_dialog_chosen_path_and_name(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()
    client.send_command.reset_mock()

    import_path = str(tmp_path / "incoming.ini")
    with patch("app.main_window.QFileDialog.getOpenFileName", return_value=(import_path, "")), \
         patch("app.main_window.QInputDialog.getText", return_value=("Imported Preset", True)):
        qtbot.mouseClick(window.preset_import_button, Qt.MouseButton.LeftButton)

    client.send_command.assert_called_once_with(
        VERB_IMPORT_PRESET, import_preset_payload(import_path, "Imported Preset"),
    )


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


def test_pin_button_forces_the_game_window(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()
    client.send_command.reset_mock()

    qtbot.mouseClick(window.pin_button, Qt.MouseButton.LeftButton)

    client.send_command.assert_called_once_with(VERB_FORCE_GAME_WINDOW, force_game_window_payload())
