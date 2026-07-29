from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt

from app.main_window import MainWindow
from ipc.client import CommandAck
from ipc.protocol import VERB_SAVE_GENERAL, VERB_SAVE_PRESET, VERB_START


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


def test_window_constructs_without_config_and_reports_engine_offline(qtbot, tmp_path: Path) -> None:
    window = MainWindow(tmp_path, client=_client())
    qtbot.addWidget(window)

    window._poll_status()
    assert not window.notice_label.isHidden()
    assert window.engine_status_label.text() == "Engine offline"


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
        "type": "Click", "label": "Alternate click", "x": 66, "y": 77,
        "endX": 0, "endY": 0, "dragMs": 0, "oncePerCycle": False,
        "seconds": 0, "onTrueScreen": "", "onFalseScreen": "",
        "fallbackEnabled": False, "fallbackMaxAttempts": 0,
        "fallbackScreen": "", "advanced": False, "outcomesRaw": "",
    }]}]
