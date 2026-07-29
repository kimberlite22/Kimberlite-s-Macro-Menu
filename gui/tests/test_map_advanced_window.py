from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt

from app.map_advanced_window import MapAdvancedWindow
from ipc.client import CommandAck
from ipc.config_reader import AdvancedStep, GeneralConfig, MapProfileConfig, PlacementConfig, read_config
from ipc.protocol import VERB_SAVE_ADV_MAP_STEPS, VERB_SAVE_MAP_PROFILE


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _client() -> MagicMock:
    client = MagicMock()
    client.send_command.return_value = CommandAck(
        "test", True, "Map advanced steps saved.", {"section": "MapProfile_Forest Map"},
    )
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
    # Regression test: SAVE_MAP_PROFILE used to resend expected_text/custom_towers/placements from
    # the snapshot frozen when this modeless dialog was opened - any edit made to those fields
    # elsewhere in the meantime (e.g. MainWindow's own Map Placement tab, or an earlier save from
    # this same dialog) would be silently reverted the next time this dialog's own Save ran.
    shutil.copyfile(FIXTURE, tmp_path / "config.ini")
    config = read_config(tmp_path / "config.ini")
    profile = next(item for item in config.map_profiles if item.name == "Forest Map")
    client = _client()

    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.config = config
    window = MapAdvancedWindow("Forest Map", client, profile=profile, general=config.general, parent=parent)
    qtbot.addWidget(window)
    window.show()

    # Simulate the parent's own config being refreshed with a newer expected_text (as if the user
    # had just saved a change on MainWindow's Map Placement tab after this dialog was opened).
    updated = next(item for item in config.map_profiles if item.name == "Forest Map")
    updated.expected_text = "Updated From Main Window"

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    profile_payload = client.send_command.call_args_list[0].args[1]
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


def test_save_sends_profile_flag_then_current_advanced_steps_payload(qtbot, tmp_path: Path) -> None:
    window, client = _window(qtbot, tmp_path)
    window.step_type.setCurrentText("Drag")
    window.step_x.setValue(9)
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)

    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)

    assert [call.args[0] for call in client.send_command.call_args_list] == [
        VERB_SAVE_MAP_PROFILE, VERB_SAVE_ADV_MAP_STEPS,
    ]
    payload = client.send_command.call_args_list[1].args[1]
    assert payload["mapProfileName"] == "Forest Map"
    assert payload["steps"][-1] == {
        "type": "Drag", "x": 9.0, "y": 0.0,
        "endX": 0.0, "endY": 0.0, "dragMs": 500,
    }
    assert "section: MapProfile_Forest Map" in window.status_label.text()
