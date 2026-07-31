from __future__ import annotations

from ipc import protocol


def test_payload_builders_use_documented_camel_case_shapes() -> None:
    step = protocol.StepPayload(type="Click", label="A | B", end_x=3, outcomes_raw="yes|no")
    screen = protocol.ScreenPayload(
        "Lobby", (step,), detection_type="Custom Detection", detection_x=1,
        detection_y=2, detection_end_x=3, detection_end_y=4, detection_text="Ready",
        default_screen="Battle", use_global_detection=True,
    )
    option = protocol.OptionPayload(name="Tower", max_uses=2, det_invert=True)

    preset = protocol.save_preset_payload(
        name="Main", screens=[screen], options=[option, option, option],
        default_map="Map", back_x=1, back_y=2, fallback_screen="Lobby",
    )

    assert preset["screens"][0]["steps"][0]["outcomesRaw"] == "yes|no"
    assert preset["screens"][0] == {
        "name": "Lobby", "steps": [step.to_dict()], "detectionType": "Custom Detection",
        "detectionX": 1, "detectionY": 2, "detectionEndX": 3, "detectionEndY": 4,
        "detectionText": "Ready", "defaultScreen": "Battle", "useGlobalDetection": True,
    }
    general = protocol.save_general_payload(slots=tuple(str(i) for i in range(10)), remote_bridge_enabled=True)
    assert len(general["slots"]) == 10 and general["remoteBridgeEnabled"] is True
    assert preset["options"][0] == {
        "name": "Tower", "x": 0, "y": 0, "available": False, "priority": 0,
        "maxUses": 2, "detX": 0, "detY": 0, "detEndX": 0, "detEndY": 0,
        "detText": "", "detInvert": True,
    }
    assert protocol.save_map_profile_payload(name="Map", placements=[{"customSlot": "A", "x": 1, "y": 2}])["customCamera"] is False
    assert protocol.save_adv_map_steps_payload(map_profile_name="General", steps=[{"type": "Zoom Out"}]) == {"mapProfileName": "General", "steps": [{"type": "Zoom Out"}]}
    assert protocol.new_preset_payload("P") == {"name": "P"}
    assert protocol.rename_map_profile_payload("Old", "New") == {"oldName": "Old", "newName": "New"}
    assert protocol.rename_screen_payload("P", "Old", "New") == {"presetName": "P", "oldName": "Old", "newName": "New"}
    assert protocol.save_global_screen_detection_payload(
        screen_name="Battle", detection_type="Ingame Detection", detection_x=1, detection_y=2,
        detection_end_x=3, detection_end_y=4, detection_text="Victory",
    ) == {
        "screenName": "Battle", "detectionType": "Ingame Detection", "detectionX": 1,
        "detectionY": 2, "detectionEndX": 3, "detectionEndY": 4, "detectionText": "Victory",
    }
    assert protocol.set_option_max_payload("P", 3, 5) == {"presetName": "P", "optionIndex": 3, "max": 5}
    assert protocol.start_payload() == {"startScreen": "", "startStep": 0, "useActive": True}


def test_ack_parser_and_json_keep_pipes_in_payload() -> None:
    assert protocol.parse_ack_line('token|{"ok":true,"message":"A | B"}') == ("token", {"ok": True, "message": "A | B"})
    assert protocol.dumps_payload({"text": "A | B"}) == '{"text":"A | B"}'


def test_local_status_parses_full_and_sparse_snapshots() -> None:
    full = protocol.LocalStatus.from_json_dict({
        "schema": 1, "timestamp": "2026-07-29 12:34:56", "running": True, "paused": True,
        "dryRun": True, "activePreset": "A", "runningPreset": "B", "queuedPreset": "C",
        "currentMap": "Map", "currentScreen": "Screen", "currentStep": "Step", "cycleCount": 1,
        "stepRepeatCount": 2, "startRepeatCount": 3, "victoryCount": 4, "defeatCount": 5,
        "configVersion": 6, "captureActive": True, "captureFieldId": "field",
    })
    assert full.running and full.dry_run and full.config_version == 6
    assert full.capture_field_id == "field"

    sparse = protocol.LocalStatus.from_json_dict({"running": "1", "unknown": "ignored"})
    assert sparse.running is True
    assert sparse.timestamp == ""
    assert sparse.config_version == 0


def test_capture_payloads_and_results_match_the_bridge_shapes() -> None:
    assert protocol.start_capture_payload("field") == {"fieldId": "field"}
    assert protocol.start_capture_region_payload(["x1", "y1", "x2", "y2"]) == {
        "fieldIds": ["x1", "y1", "x2", "y2"],
    }
    assert protocol.pair_remote_agent_payload("agent.exe", "https://example.test", "login", "a@b.test", "creds") == {
        "agentPath": "agent.exe", "serverUrl": "https://example.test", "mode": "login",
        "email": "a@b.test", "credentialsFile": "creds",
    }
    assert protocol.start_remote_agent_payload("agent.exe") == {"agentPath": "agent.exe"}
    assert protocol.stop_remote_agent_payload("agent.exe") == {"agentPath": "agent.exe"}
    point = protocol.CaptureResult.from_json_dict({"mode": "point", "fieldId": "field", "x": 1, "y": 2.5})
    assert point.field_id == "field" and (point.x, point.y) == (1.0, 2.5)
    region = protocol.CaptureResult.from_json_dict({"mode": "region", "fieldIds": ["x1", "y1", "x2", "y2"], "cancelled": True})
    assert region.field_ids == ("x1", "y1", "x2", "y2") and region.cancelled

    import pytest

    with pytest.raises(ValueError, match="exactly four strings"):
        protocol.start_capture_region_payload(["x1", "y1", "x2"])


def test_game_process_payloads_and_candidates_match_the_bridge_shapes() -> None:
    assert protocol.list_game_processes_payload() == {}
    assert protocol.force_game_window_payload() == {}
    assert protocol.show_region_preview_payload(1, 2, 3, 4) == {
        "x1": 1, "y1": 2, "x2": 3, "y2": 4,
    }
    assert protocol.ocr_test_payload(1, 2, 3, 4) == {
        "x1": 1, "y1": 2, "x2": 3, "y2": 4,
    }

    candidates = protocol.parse_game_process_candidates({
        "processes": [
            {"title": "Roblox", "process": "RobloxPlayerBeta.exe"},
            "malformed",
        ],
    })
    assert candidates == [protocol.GameProcessCandidate("Roblox", "RobloxPlayerBeta.exe")]
    assert protocol.parse_game_process_candidates({}) == []
