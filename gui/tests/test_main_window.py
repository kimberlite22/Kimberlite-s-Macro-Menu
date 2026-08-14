from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from app import engine_process
from app.launcher_paths import APP_NAME
from app.live_stats_tab import LiveStatsTab
from app.main_window import TOWER_SLOT_CHOICES, TOWER_SLOT_DEFAULT, MainWindow
from app.map_advanced_window import MapAdvancedWindow
from app.remote_agent_tab import RemoteAgentTab
from ipc.client import CommandAck, IpcTimeoutError
from ipc.config_writer import MutationError
from ipc.protocol import (
    GameProcessCandidate,
    LocalStatus,
    VERB_FORCE_GAME_WINDOW,
    VERB_LIST_GAME_PROCESSES,
    VERB_PAUSE,
    VERB_RESUME,
    VERB_RUN_CAMERA_ACTION,
    VERB_SHOW_POINT_PREVIEW,
    VERB_START,
    VERB_STOP,
    force_game_window_payload,
    list_game_processes_payload,
    run_camera_action_payload,
    show_point_preview_payload,
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


def test_window_title_uses_the_entry_file_version_and_provenance(qtbot, tmp_path: Path) -> None:
    entry_file = tmp_path / "bundle" / "main.py"
    entry_file.parent.mkdir()
    entry_file.with_name("VERSION").write_text("1.2.3\n", encoding="utf-8")
    window = MainWindow(tmp_path, client=_client(), entry_file=entry_file)
    qtbot.addWidget(window)

    assert window.windowTitle() == f"{APP_NAME} v1.2.3 (source)"


def test_window_title_defaults_to_the_plain_app_name(qtbot, tmp_path: Path) -> None:
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)

    assert window.windowTitle() == APP_NAME


def test_window_constructs_with_fixture_and_populates_general_values(qtbot, tmp_path: Path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        FIXTURE.read_text(encoding="utf-16").replace(
            "RemoteBridgeEnabled=1", "PrivateServerLink=https://www.roblox.com/share?code=abc&type=Server\nRemoteBridgeEnabled=1"
        ),
        encoding="utf-16",
    )
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    assert window.general_round_wait.value() == 12.5
    assert window.general_click_delay.value() == 150
    assert window.general_ocr_threshold.value() == 60
    assert window.general_game_process.currentText() == "RobloxPlayerBeta.exe"
    assert window.general_private_server_link.text() == "https://www.roblox.com/share?code=abc&type=Server"
    assert window.general_remote_bridge_enabled.isChecked()
    assert window._general_payload()["ocrMatchThreshold"] == 0.6


def test_the_opening_values_are_editable_while_the_screen_is_not_used(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()

    assert window.general_fullscreen_opening.isChecked() is False
    assert window.general_hole_w.isEnabled() is True


def test_using_the_whole_screen_greys_the_four_opening_values_out(qtbot, tmp_path: Path) -> None:
    """They are what the engine stops reading, so leaving them editable would be a lie."""
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()
    before = window.general_hole_w.value()

    window.general_fullscreen_opening.setChecked(True)

    for field_widget in (
        window.general_hole_x, window.general_hole_y, window.general_hole_w, window.general_hole_h
    ):
        assert field_widget.isEnabled() is False
    # Kept, not cleared: unticking has to give the user back the opening they had.
    assert window.general_hole_w.value() == before
    window.general_fullscreen_opening.setChecked(False)
    assert window.general_hole_w.isEnabled() is True
    assert window.general_hole_w.value() == before


def test_a_config_that_already_uses_the_screen_renders_that_way_without_a_toggle(
    qtbot, tmp_path: Path
) -> None:
    """Setting the box to the value it already has emits no signal, so the render is explicit."""
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        FIXTURE.read_text(encoding="utf-16").replace(
            "RemoteBridgeEnabled=1", "FullscreenOpening=1\nRemoteBridgeEnabled=1"
        ),
        encoding="utf-16",
    )
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()

    assert window.general_fullscreen_opening.isChecked() is True
    assert window.general_hole_w.isEnabled() is False


def test_the_screen_opening_choice_is_saved(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client(), auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()

    window.general_fullscreen_opening.setChecked(True)

    assert window._general_payload()["fullscreenOpening"] is True


def test_placement_show_button_uses_the_current_row_coordinates(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client, auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()
    window.placements_table.item(0, 1).setText("12.5")
    window.placements_table.item(0, 2).setText("34.25")
    client.send_command.reset_mock()

    qtbot.mouseClick(window.placements_table.cellWidget(0, 4), Qt.MouseButton.LeftButton)

    client.send_command.assert_called_once_with(
        VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(12.5, 34.25),
    )


def test_edit_preset_reuses_existing_window_instead_of_opening_a_duplicate(qtbot, tmp_path: Path) -> None:
    # Regression test: clicking "Edit..." twice used to spawn a second independent in-memory
    # editor for the same preset - whichever one saved last would silently discard the other's edits.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.preset_list.setCurrentRow(0)
    window._edit_preset()
    first = window._edit_preset_windows[(window.config.active_game, window._selected_preset_name)]

    window._edit_preset()
    second = window._edit_preset_windows[(window.config.active_game, window._selected_preset_name)]
    assert second is first

    first.close()
    assert (window.config.active_game, window._selected_preset_name) not in window._edit_preset_windows


def test_map_advanced_reuses_existing_window_instead_of_opening_a_duplicate(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.map_profile_combo.setCurrentText("Forest Map")
    qtbot.mouseClick(window.map_advanced_button, Qt.MouseButton.LeftButton)
    first = window._map_advanced_windows[(window.config.active_game, window._selected_map_profile_name)]
    assert isinstance(first, MapAdvancedWindow)

    qtbot.mouseClick(window.map_advanced_button, Qt.MouseButton.LeftButton)
    second = window._map_advanced_windows[(window.config.active_game, window._selected_map_profile_name)]
    assert second is first

    first.close()
    assert (window.config.active_game, window._selected_map_profile_name) not in window._map_advanced_windows


def test_run_camera_action_button_sends_selected_map_profile(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    window.map_profile_combo.setCurrentText("Forest Map")
    client.send_command.reset_mock()
    qtbot.mouseClick(window.map_run_camera_button, Qt.MouseButton.LeftButton)

    client.send_command.assert_called_once_with(
        VERB_RUN_CAMERA_ACTION, run_camera_action_payload("Forest Map"),
    )


def test_run_camera_action_requires_selected_map_profile(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    window.map_profile_combo.setCurrentIndex(-1)
    client.send_command.reset_mock()
    qtbot.mouseClick(window.map_run_camera_button, Qt.MouseButton.LeftButton)

    assert window.statusBar().currentMessage() == "Select a map profile first."
    client.send_command.assert_not_called()


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


def test_live_stats_tab_is_mounted_and_receives_polled_status(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    client.read_status.return_value = LocalStatus(
        timestamp="2026-08-08 12:00:00", running=True, running_preset="Main Preset",
        current_map="Map", session_time_ms=61_000, screen_time_ms={"Lobby": 2_000},
    )
    window = MainWindow(tmp_path, client=client, auto_refresh_game_processes=False)
    qtbot.addWidget(window)
    window.show()

    window._poll_status()

    assert isinstance(window.live_stats_tab, LiveStatsTab)
    assert window.tabs.tabText(window.tabs.indexOf(window.live_stats_tab)) == "Live Stats"
    assert window.live_stats_tab.findChild(QLabel, "stat_value_map").text() == "Map"
    assert [window.live_stats_tab.screen_time_table.item(row, 0).text() for row in range(2)] == [
        "Lobby", "Battle",
    ]
    assert window.live_stats_tab.screen_time_table.item(0, 1).text() == "0:02"


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
    edit_preset_window = window._edit_preset_windows[(window.config.active_game, window._selected_preset_name)]

    window.map_profile_combo.setCurrentText("Forest Map")
    qtbot.mouseClick(window.map_advanced_button, Qt.MouseButton.LeftButton)
    map_advanced_window = window._map_advanced_windows[(window.config.active_game, window._selected_map_profile_name)]

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
    edit_preset_window = window._edit_preset_windows[(window.config.active_game, window._selected_preset_name)]
    step_editor = edit_preset_window._open_step_editor_for_search()
    step_editor._open_option_availability(0)
    option_availability_window = step_editor.option_availability_window

    assert option_availability_window.isVisible()

    window.close()

    assert not option_availability_window.isVisible()


def test_closing_the_main_window_quits_the_application_outright(qtbot, tmp_path: Path) -> None:
    # Regression test: two earlier, narrower fixes here each closed every window they could find
    # (first three tracked collections, then every visible top-level widget) and the process still
    # kept running afterward in a case the user hit - because both relied on Qt's own
    # quitOnLastWindowClosed noticing the visible-window count reached zero, rather than closeEvent
    # stating outright "closing the main window quits the app". Assert the actual signal that ends
    # the process fires, not just that windows became invisible.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    # No qtbot test here ever calls app.exec(), so aboutToQuit itself never fires (nothing is
    # tearing down a running event loop) regardless of whether quit() was requested - assert the
    # request itself was made, which is what actually matters once a real event loop is running.
    with patch.object(QApplication, "quit") as quit_mock:
        window.close()

    quit_mock.assert_called_once()


def test_closing_the_main_window_tolerates_an_already_deleted_top_level_widget(
    qtbot, tmp_path: Path,
) -> None:
    # Regression test: the sweep in closeEvent iterates QApplication.topLevelWidgets() and calls
    # close() on each. A transient Qt-owned top-level widget whose underlying C++ object is
    # already gone by the time the loop reaches it (isVisible()/close() raising RuntimeError) used
    # to abort the loop outright, leaving every widget after it in the list unclosed.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.map_profile_combo.setCurrentText("Forest Map")
    qtbot.mouseClick(window.map_advanced_button, Qt.MouseButton.LeftButton)
    map_advanced_window = window._map_advanced_windows[(window.config.active_game, window._selected_map_profile_name)]

    already_deleted = MagicMock()
    already_deleted.isVisible.side_effect = RuntimeError(
        "wrapped C/C++ object of type QWidget has been deleted"
    )
    real_widgets = QApplication.topLevelWidgets()
    ordered = [w for w in real_widgets if w is not window and w is not map_advanced_window]
    ordered += [already_deleted, map_advanced_window]

    with patch.object(QApplication, "topLevelWidgets", return_value=ordered):
        window.close()

    assert not map_advanced_window.isVisible()


def test_window_constructs_without_config_and_reports_stopped(qtbot, tmp_path: Path) -> None:
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)

    window._poll_status()
    assert not window.notice_label.isHidden()
    assert window.engine_status_label.text() == "Idle"


# ---------------------------------------------------------------------------------------------
# The "Background session" flag next to the engine status
# ---------------------------------------------------------------------------------------------


def _engine_appears(window: MainWindow, client: MagicMock) -> None:
    """Make one poll see a live engine where the poll before it saw none."""
    client.read_status.return_value = LocalStatus(timestamp="1")
    window._poll_status()


def test_an_engine_starting_in_another_session_raises_the_flag(qtbot, tmp_path: Path, monkeypatch) -> None:
    # The whole point of making this live: pressing Start on the Background Session tab, or a session
    # started outside this app, used to leave the top strip claiming the engine was local until the
    # app was restarted.
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    # Shown, because a child widget reports itself invisible while any ancestor of it is hidden.
    window.show()
    assert window.background_session_label.isVisible() is False
    monkeypatch.setattr(engine_process, "engine_is_in_another_session", lambda: True)

    _engine_appears(window, client)

    assert window.background_session_label.isVisible() is True


def test_the_flag_is_left_alone_when_where_the_engine_runs_cannot_be_read(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """It changes what closing this window does to a running macro, so a failed query may not guess."""
    client = _client()
    window = MainWindow(tmp_path, client=client, engine_in_background_session=True)
    qtbot.addWidget(window)
    window.show()
    assert window.background_session_label.isVisible() is True
    monkeypatch.setattr(engine_process, "engine_is_in_another_session", lambda: None)

    _engine_appears(window, client)

    assert window.background_session_label.isVisible() is True


def test_the_first_poll_does_not_re_ask_what_startup_already_resolved(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """main.py runs the same query before the window exists, and it costs a tasklist.exe spawn."""
    asked = MagicMock(return_value=True)
    monkeypatch.setattr(engine_process, "engine_is_in_another_session", asked)

    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)

    asked.assert_not_called()


def test_the_tab_acting_on_the_session_refreshes_the_flag(qtbot, tmp_path: Path, monkeypatch) -> None:
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(engine_process, "engine_is_in_another_session", lambda: True)

    window.background_session_tab.session_changed.emit()

    assert window.background_session_label.isVisible() is True


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
    window.general_private_server_link.setText("https://www.roblox.com/share?code=abc&type=Server")

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
    assert general_payload["privateServerLink"] == "https://www.roblox.com/share?code=abc&type=Server"
    assert len(general_payload["slots"]) == 10
    preset_payload = payloads["preset"]
    assert len(preset_payload["options"]) == 3
    assert preset_payload["screens"] == [{"name": "Alt Screen", "steps": [{
        "type": "Button Click", "label": "Alternate click", "x": 66, "y": 77,
        "endX": 0, "endY": 0, "dragMs": 0, "oncePerCycle": False,
        "seconds": 0, "onTrueScreen": "", "onFalseScreen": "",
        "fallbackEnabled": False, "fallbackMaxAttempts": 0,
        "fallbackScreen": "", "advanced": False, "outcomesRaw": "",
        "key": "", "holdMs": 0, "holdAsync": False, "holdUntilStep": "",
    }]}]


def test_save_preserves_selected_preset_navigation_fields_without_main_window_widgets(
    qtbot, tmp_path: Path,
) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    preset = window._selected_preset()
    assert preset is not None
    assert (preset.back_x, preset.back_y, preset.fallback_screen) == (1, 2, "Alt Screen")

    window.preset_default_map.setCurrentText("Forest Map")
    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    payload = client.save_config.call_args.kwargs["preset"]
    assert (payload["backX"], payload["backY"], payload["fallbackScreen"]) == (1, 2, "Alt Screen")


def test_save_refuses_an_invalid_private_server_link_without_writing(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()
    window.general_private_server_link.setText("https://roblox.com.evil.example/share?code=abc&type=Server")

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    client.save_config.assert_not_called()
    assert "roblox.com host" in window.statusBar().currentMessage()


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

    client.export_preset.assert_called_once_with(preset_name, export_path, game="Anime Expedition")
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

    client.import_preset.assert_called_once_with(import_path, "Imported Preset", game="Anime Expedition")
    client.send_command.assert_not_called()


def test_new_rename_delete_preset_write_locally_and_refresh(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    client = _client()
    window = MainWindow(tmp_path, client=client)
    qtbot.addWidget(window)
    window.show()

    with patch("app.main_window.QInputDialog.getText", return_value=("New Preset", True)):
        qtbot.mouseClick(window.preset_new_button, Qt.MouseButton.LeftButton)
    client.create_preset.assert_called_once_with("New Preset", game="Anime Expedition")

    window.preset_list.setCurrentRow(0)
    preset_name = window._selected_preset_name
    with patch("app.main_window.QInputDialog.getText", return_value=("Renamed Preset", True)):
        qtbot.mouseClick(window.preset_rename_button, Qt.MouseButton.LeftButton)
    client.rename_preset.assert_called_once_with(preset_name, "Renamed Preset", game="Anime Expedition")

    with patch("app.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        qtbot.mouseClick(window.preset_delete_button, Qt.MouseButton.LeftButton)
    client.delete_preset.assert_called_once_with(preset_name, game="Anime Expedition")
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
    client.create_map_profile.assert_called_once_with("New Map", game="Anime Expedition")

    profile_name = window._selected_map_profile_name
    with patch("app.main_window.QInputDialog.getText", return_value=("Renamed Map", True)):
        qtbot.mouseClick(window.map_rename_button, Qt.MouseButton.LeftButton)
    client.rename_map_profile.assert_called_once_with(profile_name, "Renamed Map", game="Anime Expedition")

    with patch("app.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        qtbot.mouseClick(window.map_delete_button, Qt.MouseButton.LeftButton)
    client.delete_map_profile.assert_called_once_with(profile_name, game="Anime Expedition")
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
    client.set_option_used_count.assert_called_with(preset_name, 1, 3, game="Anime Expedition")

    window.usage_max[0].setValue(9)
    client.set_option_max.assert_called_with(preset_name, 1, 9, game="Anime Expedition")
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


def test_placement_remove_button_shifts_rows_and_decrements_count(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.map_profile_combo.setCurrentText("Forest Map")
    for column, value in enumerate(("Delta", "41", "42")):
        window.placements_table.item(3, column).setText(value)
    window.map_num_placements.setValue(4)
    button = window.placements_table.cellWidget(1, 5)
    assert button is not None
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert [window.placements_table.item(1, column).text() for column in range(3)] == ["Gamma", "31", "32"]
    assert [window.placements_table.item(2, column).text() for column in range(3)] == ["Delta", "41", "42"]
    assert [window.placements_table.item(9, column).text() for column in range(3)] == ["", "0", "0"]
    assert window.map_num_placements.value() == 3
    assert [not window.placements_table.isRowHidden(row) for row in range(10)] == [True] * 3 + [False] * 7


def test_placement_remove_column_tracks_custom_tower_setting(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.map_profile_combo.setCurrentText("Desert Map")
    assert window.placements_table.isColumnHidden(5)

    window.map_profile_combo.setCurrentText("Forest Map")
    assert not window.placements_table.isColumnHidden(5)


def test_placement_remove_at_zero_does_not_make_count_negative(qtbot, tmp_path: Path) -> None:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)
    window.show()

    window.map_num_placements.setValue(0)
    window._remove_placement(0)

    assert window.map_num_placements.value() == 0


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
