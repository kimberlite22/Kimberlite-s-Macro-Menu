from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.map_advanced_window import MapAdvancedWindow
from ipc.client import IpcTimeoutError
from ipc.config_reader import AdvancedStep, GeneralConfig, MapProfileConfig, PlacementConfig, read_config
from ipc.protocol import VERB_SHOW_POINT_PREVIEW, show_point_preview_payload


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _client() -> MagicMock:
    client = MagicMock()
    client.save_config.return_value = "Saved: map profile Forest Map, camera steps (MapProfile_Forest Map)."
    return client


def _window(qtbot, tmp_path: Path, profile_name: str = "Forest Map") -> tuple[MapAdvancedWindow, MagicMock]:
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    config = read_config(tmp_path / "config.ini")
    profile = next(item for item in config.map_profiles if item.name == profile_name)
    client = _client()
    window = MapAdvancedWindow(profile.name, client, profile=profile, general=config.general)
    qtbot.addWidget(window)
    window.show()
    return window, client


def _save_open_editor(
    qtbot, window: MapAdvancedWindow, *, step_type: str = "Drag", x: float = 0,
    y: float = 0, end_x: float = 0, end_y: float = 0, drag_ms: int = 500,
) -> None:
    editor = window._step_edit_window
    assert editor is not None
    assert editor._map_action_mode
    editor.step_type.setCurrentText(step_type)
    editor.step_x.setValue(x)
    editor.step_y.setValue(y)
    editor.step_end_x.setValue(end_x)
    editor.step_end_y.setValue(end_y)
    editor.step_drag_ms.setValue(drag_ms)
    qtbot.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._step_edit_window is None)


def test_populates_custom_profile_steps_and_toggle_reloads_effective_steps(qtbot, tmp_path: Path) -> None:
    window, _ = _window(qtbot, tmp_path)

    assert window.custom_camera.isChecked()
    assert window.step_list.rowCount() == 2
    assert window.step_list.item(0, 0).text() == "Camera Drag"

    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    _save_open_editor(qtbot, window, x=1, y=2, end_x=3, end_y=4, drag_ms=250)
    assert window.step_list.rowCount() == 3

    qtbot.mouseClick(window.custom_camera, Qt.MouseButton.LeftButton)
    assert not window.custom_camera.isChecked()
    assert window.step_list.rowCount() == 3
    assert window.step_list.item(1, 0).text() == "Zoom Out"

    qtbot.mouseClick(window.custom_camera, Qt.MouseButton.LeftButton)
    assert window.custom_camera.isChecked()
    assert window.step_list.rowCount() == 2

    desert, _ = _window(qtbot, tmp_path, "Desert Map")
    assert not desert.custom_camera.isChecked()
    assert desert.step_list.rowCount() == 3
    qtbot.mouseClick(desert.custom_camera, Qt.MouseButton.LeftButton)
    assert desert.step_list.rowCount() == 0


def test_window_has_independent_minimize_button(qtbot, tmp_path: Path) -> None:
    # Regression guard, see make_independently_minimizable: MapAdvancedWindow would otherwise
    # have no minimize button of its own, and its caller (MainWindow) deliberately constructs
    # it with no Qt parent (live config now reaches it via config_source instead) since a
    # parented QDialog would be a native Windows owned window that auto-hides with its owner.
    window, _ = _window(qtbot, tmp_path)
    assert window.windowFlags() & Qt.WindowMinimizeButtonHint


def test_shared_editor_show_buttons_preview_current_start_and_end_coordinates(qtbot, tmp_path: Path) -> None:
    window, client = _window(qtbot, tmp_path)
    client.send_command.return_value.ok = True
    client.send_command.return_value.message = "accepted"
    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None
    editor.step_type.setCurrentText("Drag")
    editor.step_x.setValue(10.5)
    editor.step_y.setValue(20.25)
    editor.step_end_x.setValue(30.75)
    editor.step_end_y.setValue(40.5)

    qtbot.mouseClick(editor.show_position_button, Qt.MouseButton.LeftButton)
    client.send_command.assert_called_once_with(
        VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(10.5, 20.25),
    )

    client.send_command.reset_mock()
    qtbot.mouseClick(editor.show_end_position_button, Qt.MouseButton.LeftButton)
    client.send_command.assert_called_once_with(
        VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(30.75, 40.5),
    )
    editor.reject()


def test_shared_editor_show_buttons_follow_drag_visibility(qtbot, tmp_path: Path) -> None:
    window, _ = _window(qtbot, tmp_path)
    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None

    editor.step_type.setCurrentText("Zoom Out")
    assert not editor.show_position_button.isVisible()
    assert not editor.show_end_position_button.isVisible()

    editor.step_type.setCurrentText("Drag")
    assert editor.show_position_button.isVisible()
    assert editor.show_end_position_button.isVisible()
    editor.reject()


def test_shared_editor_show_point_preview_timeout_is_reported(qtbot, tmp_path: Path) -> None:
    window, client = _window(qtbot, tmp_path)
    client.send_command.side_effect = IpcTimeoutError("timed out")
    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None

    qtbot.mouseClick(editor.show_position_button, Qt.MouseButton.LeftButton)

    assert editor.status_label.text() == (
        "SHOW_POINT_PREVIEW: timed out, outcome unknown. Check status before retrying."
    )
    editor.reject()


def test_zoom_out_row_renders_ticks_and_no_coordinate_fields(qtbot, tmp_path: Path) -> None:
    window, _ = _window(qtbot, tmp_path)
    # Forest Map's own actions are "Camera Drag" and "Zoom In"; the shared default list is the one
    # carrying a "Zoom Out", so untick custom camera to render that list instead.
    qtbot.mouseClick(window.custom_camera, Qt.MouseButton.LeftButton)
    zoom_row = next(
        row for row in range(window.step_list.rowCount())
        if window.step_list.item(row, 0).text() == "Zoom Out"
    )

    assert window.step_list.item(zoom_row, 1).text() == "-3 ticks"
    assert [window.step_list.item(zoom_row, column).text() for column in range(2, 6)] == ["", "", "", ""]


def test_custom_camera_toggle_closes_an_open_action_editor(qtbot, tmp_path: Path) -> None:
    # The toggle already resets the arrived-at section to its last known good state, so no unsaved
    # edit survives it. An in-flight edit in the non-modal child editor has to go the same way:
    # _save() only ever serializes the currently-effective section, so an editor left open against
    # the other one would let the user finish an edit that could never reach the save payload.
    window, _ = _window(qtbot, tmp_path)
    assert window.custom_camera.isChecked()
    custom_section = window._profile_section
    custom_before = len(window._steps_by_section[custom_section])
    shared_before = len(window._steps_by_section["General"])

    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    assert window._step_edit_window is not None
    qtbot.mouseClick(window.custom_camera, Qt.MouseButton.LeftButton)

    assert window._step_edit_window is None
    assert window._step_edit_target is None
    assert len(window._steps_by_section[custom_section]) == custom_before
    assert len(window._steps_by_section["General"]) == shared_before


def test_closing_the_window_closes_an_open_action_editor(qtbot, tmp_path: Path) -> None:
    # The editor is deliberately parentless (see _open_step_editor), so nothing closes it for us.
    # Left behind it is an orphan whose Save writes into a model the user can no longer reach.
    window, _ = _window(qtbot, tmp_path)
    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    editor = window._step_edit_window
    assert editor is not None

    window.close()

    assert window._step_edit_window is None
    assert window._step_edit_target is None
    assert not editor.isVisible()


def test_legacy_action_types_still_render_their_stored_coordinates(qtbot, tmp_path: Path) -> None:
    # Real configs hold action types this editor never offers ("Camera Drag", "Zoom In", "Click"),
    # so only "Zoom Out" is special-cased and every other type shows all six stored values. Blanking
    # cells for an unrecognized type would hide data the user actually has.
    window, _ = _window(qtbot, tmp_path)

    assert window.step_list.item(0, 0).text() == "Camera Drag"
    assert [window.step_list.item(0, column).text() for column in range(1, 6)] == [
        "15", "25", "35", "45", "600",
    ]


def test_dormant_adv_steps_survive_while_custom_camera_is_off(qtbot) -> None:
    # Regression test: config_reader used to only populate adv_steps while custom_camera was true,
    # so re-enabling it here showed an empty list and Save would have permanently overwritten real
    # dormant steps still sitting in the profile's own ini section with nothing.
    profile = MapProfileConfig(
        name="Dormant Map", expected_text="Dormant", custom_towers=False, custom_num_placements=0,
        placements=[PlacementConfig("", 0, 0) for _ in range(10)], custom_camera=False,
        adv_steps=[AdvancedStep(type="Drag", x=1, y=2, end_x=3, end_y=4, drag_ms=100)],
    )
    general = GeneralConfig(adv_steps=[])
    window = MapAdvancedWindow("Dormant Map", _client(), profile=profile, general=general)
    qtbot.addWidget(window)
    window.show()

    assert window.step_list.rowCount() == 0  # starts on the shared (empty) General list
    qtbot.mouseClick(window.custom_camera, Qt.MouseButton.LeftButton)
    assert window.step_list.rowCount() == 1
    assert window.step_list.item(0, 0).text() == "Drag"


def test_save_uses_live_parent_profile_data_not_the_open_time_snapshot(qtbot, tmp_path: Path) -> None:
    # Regression test: the map profile save used to resend expected_text/custom_towers/placements
    # from the snapshot frozen when this modeless dialog was opened - any edit made to those fields
    # elsewhere in the meantime (e.g. MainWindow's own Map Placement tab, or an earlier save from
    # this same dialog) would be silently reverted the next time this dialog's own Save ran.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    config = read_config(tmp_path / "config.ini")
    profile = next(item for item in config.map_profiles if item.name == "Forest Map")
    client = _client()

    # A plain stand-in for "whatever object holds the live config" (MainWindow in production),
    # passed as config_source rather than as a Qt parent: see make_independently_minimizable,
    # this window must not be given a Qt parent, so its live-config lookup no longer goes
    # through self.parent().
    config_source = SimpleNamespace(config=config)
    window = MapAdvancedWindow(
        "Forest Map", client, profile=profile, general=config.general, config_source=config_source,
    )
    qtbot.addWidget(window)
    window.show()

    # Simulate the config source being refreshed with a newer expected_text (as if the user
    # had just saved a change on MainWindow's Map Placement tab after this dialog was opened).
    updated = next(item for item in config.map_profiles if item.name == "Forest Map")
    updated.expected_text = "Updated From Main Window"

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    profile_payload = client.save_config.call_args.kwargs["map_profile"]
    assert profile_payload["expectedText"] == "Updated From Main Window"


def test_add_edit_duplicate_and_delete_change_only_the_in_memory_list(qtbot, tmp_path: Path) -> None:
    window, _ = _window(qtbot, tmp_path)

    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    _save_open_editor(qtbot, window, x=1, y=2, end_x=3, end_y=4, drag_ms=250)
    assert window.step_list.rowCount() == 3
    assert window._steps[-1].drag_ms == 250

    window.step_list.setCurrentCell(2, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    _save_open_editor(qtbot, window, x=8, y=2, end_x=3, end_y=4, drag_ms=250)
    assert window._steps[2].x == 8

    qtbot.mouseClick(window.duplicate_step_button, Qt.MouseButton.LeftButton)
    assert window.step_list.rowCount() == 4
    assert window._steps[3].x == 8
    assert window._steps[3] is not window._steps[2]

    with patch("app.map_advanced_window.QMessageBox") as message_box:
        message_box.StandardButton = QMessageBox.StandardButton
        message_box.Icon = QMessageBox.Icon
        message_box.return_value.exec.return_value = QMessageBox.StandardButton.Yes
        qtbot.mouseClick(window.delete_step_button, Qt.MouseButton.LeftButton)
    assert message_box.called
    assert window.step_list.rowCount() == 3
    assert window._steps[2].x == 8


def test_reordering_vertical_header_rewrites_order_without_scrambling_fields(qtbot) -> None:
    profile = MapProfileConfig(
        name="Ordered Map", expected_text="Ordered", custom_towers=False, custom_num_placements=0,
        placements=[PlacementConfig("", 0, 0) for _ in range(10)], custom_camera=True,
        adv_steps=[
            AdvancedStep(type="Drag", x=1, y=2, end_x=3, end_y=4, drag_ms=100),
            AdvancedStep(type="Drag", x=10, y=20, end_x=30, end_y=40, drag_ms=200),
            AdvancedStep(type="Drag", x=100, y=200, end_x=300, end_y=400, drag_ms=300),
        ],
    )
    window = MapAdvancedWindow("Ordered Map", _client(), profile=profile, general=GeneralConfig(adv_steps=[]))
    qtbot.addWidget(window)
    window.show()

    window.step_list.verticalHeader().moveSection(0, 2)

    assert [(step.x, step.y, step.end_x, step.end_y, step.drag_ms) for step in window._steps] == [
        (10, 20, 30, 40, 200),
        (100, 200, 300, 400, 300),
        (1, 2, 3, 4, 100),
    ]
    assert [window.step_list.item(row, 1).text() for row in range(3)] == ["10", "100", "1"]


def test_edit_saved_after_underlying_row_moves_updates_the_same_action(qtbot) -> None:
    profile = MapProfileConfig(
        name="Identity Map", expected_text="Identity", custom_towers=False, custom_num_placements=0,
        placements=[PlacementConfig("", 0, 0) for _ in range(10)], custom_camera=True,
        adv_steps=[
            AdvancedStep(type="Drag", x=1, y=2, end_x=3, end_y=4, drag_ms=100),
            AdvancedStep(type="Drag", x=10, y=20, end_x=30, end_y=40, drag_ms=200),
        ],
    )
    window = MapAdvancedWindow("Identity Map", _client(), profile=profile, general=GeneralConfig(adv_steps=[]))
    qtbot.addWidget(window)
    window.show()

    window.step_list.setCurrentCell(0, 0)
    qtbot.mouseClick(window.edit_step_button, Qt.MouseButton.LeftButton)
    window.step_list.verticalHeader().moveSection(0, 1)
    _save_open_editor(qtbot, window, x=99, y=98, end_x=97, end_y=96, drag_ms=95)

    assert [(step.x, step.y, step.end_x, step.end_y, step.drag_ms) for step in window._steps] == [
        (10, 20, 30, 40, 200),
        (99, 98, 97, 96, 95),
    ]


def test_save_sends_profile_flag_and_current_advanced_steps_in_one_write(qtbot, tmp_path: Path) -> None:
    window, client = _window(qtbot, tmp_path)
    qtbot.mouseClick(window.add_step_button, Qt.MouseButton.LeftButton)
    _save_open_editor(qtbot, window, x=9)

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    client.save_config.assert_called_once()
    payloads = client.save_config.call_args.kwargs
    assert payloads["map_profile"]["name"] == "Forest Map"
    payload = payloads["adv_steps"]
    assert payload["mapProfileName"] == "Forest Map"
    assert payload["steps"][-1] == {
        "type": "Drag", "x": 9.0, "y": 0.0,
        "endX": 0.0, "endY": 0.0, "dragMs": 500,
    }
    assert "camera steps (MapProfile_Forest Map)" in window.status_label.text()
