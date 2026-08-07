from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import Qt

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


def test_populates_custom_profile_steps_and_toggle_reloads_effective_steps(qtbot, tmp_path: Path) -> None:
    window, _ = _window(qtbot, tmp_path)

    assert window.custom_camera.isChecked()
    assert window.step_list.count() == 2
    assert "Camera Drag" in window.step_list.item(0).text()

    window.step_type.setCurrentText("Drag")
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert window.step_list.count() == 3

    qtbot.mouseClick(window.custom_camera, Qt.MouseButton.LeftButton)
    assert not window.custom_camera.isChecked()
    assert window.step_list.count() == 3
    assert "Zoom Out" in window.step_list.item(1).text()

    qtbot.mouseClick(window.custom_camera, Qt.MouseButton.LeftButton)
    assert window.custom_camera.isChecked()
    assert window.step_list.count() == 2

    desert, _ = _window(qtbot, tmp_path, "Desert Map")
    assert not desert.custom_camera.isChecked()
    assert desert.step_list.count() == 3
    qtbot.mouseClick(desert.custom_camera, Qt.MouseButton.LeftButton)
    assert desert.step_list.count() == 0


def test_window_has_independent_minimize_button(qtbot, tmp_path: Path) -> None:
    # Regression guard, see make_independently_minimizable: MapAdvancedWindow would otherwise
    # have no minimize button of its own, and its caller (MainWindow) deliberately constructs
    # it with no Qt parent (live config now reaches it via config_source instead) since a
    # parented QDialog would be a native Windows "owned window" that auto-hides with its owner.
    window, _ = _window(qtbot, tmp_path)
    assert window.windowFlags() & Qt.WindowMinimizeButtonHint


def test_show_buttons_preview_current_start_and_end_coordinates(qtbot, tmp_path: Path) -> None:
    window, client = _window(qtbot, tmp_path)
    assert window.show_start_button.objectName() == "map_advanced_show_start_button"
    assert window.show_end_button.objectName() == "map_advanced_show_end_button"
    client.send_command.return_value.ok = True
    client.send_command.return_value.message = "accepted"
    window.step_type.setCurrentText("Drag")
    window.step_x.setValue(10.5)
    window.step_y.setValue(20.25)
    window.step_end_x.setValue(30.75)
    window.step_end_y.setValue(40.5)

    qtbot.mouseClick(window.show_start_button, Qt.MouseButton.LeftButton)
    client.send_command.assert_called_once_with(
        VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(10.5, 20.25),
    )

    client.send_command.reset_mock()
    qtbot.mouseClick(window.show_end_button, Qt.MouseButton.LeftButton)
    client.send_command.assert_called_once_with(
        VERB_SHOW_POINT_PREVIEW, show_point_preview_payload(30.75, 40.5),
    )


def test_show_buttons_follow_drag_visibility(qtbot, tmp_path: Path) -> None:
    window, _ = _window(qtbot, tmp_path)

    window.step_type.setCurrentText("Zoom Out")
    assert not window.show_start_button.isVisible()
    assert not window.show_end_button.isVisible()

    window.step_type.setCurrentText("Drag")
    assert window.show_start_button.isVisible()
    assert window.show_end_button.isVisible()


def test_show_point_preview_timeout_is_reported(qtbot, tmp_path: Path) -> None:
    window, client = _window(qtbot, tmp_path)
    client.send_command.side_effect = IpcTimeoutError("timed out")
    window.step_type.setCurrentText("Drag")

    qtbot.mouseClick(window.show_start_button, Qt.MouseButton.LeftButton)

    assert window.status_label.text() == (
        "SHOW_POINT_PREVIEW: timed out, outcome unknown. Check status before retrying."
    )


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

    assert window.step_list.count() == 0  # starts on the shared (empty) General list
    qtbot.mouseClick(window.custom_camera, Qt.MouseButton.LeftButton)
    assert window.step_list.count() == 1
    assert "Drag" in window.step_list.item(0).text()


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


def test_add_update_remove_and_move_change_only_the_in_memory_list(qtbot, tmp_path: Path) -> None:
    window, _ = _window(qtbot, tmp_path)
    window.step_type.setCurrentText("Zoom Out")
    assert not window.capture_start_button.isVisible()
    assert not window.capture_end_button.isVisible()
    window.step_type.setCurrentText("Drag")
    window.step_x.setValue(1)
    window.step_y.setValue(2)
    window.step_end_x.setValue(3)
    window.step_end_y.setValue(4)
    window.step_drag_ms.setValue(250)

    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert window.step_list.count() == 3
    assert window._steps[-1].drag_ms == 250

    window.step_list.setCurrentRow(2)
    qtbot.mouseClick(window.move_up_button, Qt.MouseButton.LeftButton)
    assert window._steps[1].x == 1
    qtbot.mouseClick(window.move_down_button, Qt.MouseButton.LeftButton)
    assert window._steps[2].x == 1

    window.step_x.setValue(8)
    qtbot.mouseClick(window.update_button, Qt.MouseButton.LeftButton)
    assert window._steps[2].x == 8
    qtbot.mouseClick(window.remove_button, Qt.MouseButton.LeftButton)
    assert window.step_list.count() == 2


def test_save_sends_profile_flag_and_current_advanced_steps_in_one_write(qtbot, tmp_path: Path) -> None:
    window, client = _window(qtbot, tmp_path)
    window.step_type.setCurrentText("Drag")
    window.step_x.setValue(9)
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)

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
