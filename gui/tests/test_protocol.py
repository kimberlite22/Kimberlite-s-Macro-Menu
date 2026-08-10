from __future__ import annotations

from ipc import protocol


def test_payload_builders_use_documented_camel_case_shapes() -> None:
    step = protocol.StepPayload(type="Click", label="A | B", end_x=3, outcomes_raw="yes|no")
    screen = protocol.ScreenPayload("Lobby", (step,))
    option = protocol.OptionPayload(name="Tower", max_uses=2, det_invert=True)

    preset = protocol.save_preset_payload(
        name="Main", screens=[screen], options=[option, option, option],
        default_map="Map", back_x=1, back_y=2, fallback_screen="Lobby",
    )

    assert preset["screens"][0]["steps"][0]["outcomesRaw"] == "yes|no"
    general = protocol.save_general_payload(
        slots=tuple(str(i) for i in range(10)), private_server_link="https://www.roblox.com/share?code=abc&type=Server",
        remote_bridge_enabled=True,
    )
    assert len(general["slots"]) == 10 and general["remoteBridgeEnabled"] is True
    assert general["privateServerLink"] == "https://www.roblox.com/share?code=abc&type=Server"
    assert preset["options"][0] == {
        "name": "Tower", "x": 0, "y": 0, "available": False, "priority": 0,
        "maxUses": 2, "detX": 0, "detY": 0, "detEndX": 0, "detEndY": 0,
        "detText": "", "detInvert": True,
    }
    assert protocol.save_map_profile_payload(name="Map", placements=[{"customSlot": "A", "x": 1, "y": 2}])["customCamera"] is False
    assert protocol.save_adv_map_steps_payload(map_profile_name="General", steps=[{"type": "Zoom Out"}]) == {"mapProfileName": "General", "steps": [{"type": "Zoom Out"}]}
    assert protocol.set_active_preset_payload("P") == {"name": "P"}
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


def test_local_status_parses_live_stats_fields_tolerantly() -> None:
    full = protocol.LocalStatus.from_json_dict({
        "sessionId": "session", "sessionTimeMs": "1234", "currentStepTimeMs": 5678,
        "screenTimeMs": {"Lobby": 1000, "Battle": "2000", "Bad": "nope"},
        "stepTimeMs": {"Lobby - Start": 3000},
    })

    assert full.session_id == "session"
    assert full.session_time_ms == 1234
    assert full.current_step_time_ms == 5678
    assert full.screen_time_ms == {"Lobby": 1000, "Battle": 2000}
    assert full.step_time_ms == {"Lobby - Start": 3000}

    sparse = protocol.LocalStatus.from_json_dict({"screenTimeMs": "malformed"})
    assert sparse.current_step_time_ms == -1
    assert sparse.screen_time_ms == {}


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
    assert protocol.show_point_preview_payload(1, 2) == {"x": 1, "y": 2}
    assert protocol.ocr_test_payload(1, 2, 3, 4) == {
        "x1": 1, "y1": 2, "x2": 3, "y2": 4, "expected": "",
    }
    assert protocol.ocr_test_payload(1, 2, 3, 4, "Ready") == {
        "x1": 1, "y1": 2, "x2": 3, "y2": 4, "expected": "Ready",
    }

    candidates = protocol.parse_game_process_candidates({
        "processes": [
            {"title": "Roblox", "process": "RobloxPlayerBeta.exe"},
            "malformed",
        ],
    })
    assert candidates == [protocol.GameProcessCandidate("Roblox", "RobloxPlayerBeta.exe")]
    assert protocol.parse_game_process_candidates({}) == []


def test_ocr_test_result_reads_ahk_integer_flags_as_booleans() -> None:
    # AHK has no boolean type, so LocalBridgeAckValueJson emits flags as the numbers 1 and 0.
    matched = protocol.OcrTestResult.from_ack_data({
        "detected": 1, "text": "Victory!", "padPct": 25, "padColor": "white",
        "stagesTried": 4, "stagesTotal": 7, "capped": 0, "maxSide": 750,
    })
    assert matched.detected is True and matched.capped is False
    assert (matched.pad_pct, matched.pad_color) == (25, "white")

    # A stale engine that predates these fields must degrade to "not detected", not crash.
    assert protocol.OcrTestResult.from_ack_data({"text": "Found"}) == protocol.OcrTestResult(
        detected=False, text="Found",
    )


def test_ocr_test_result_message_names_the_verdict_and_the_border_it_needed() -> None:
    def result(**kwargs) -> protocol.OcrTestResult:
        base = dict(stages_tried=7, stages_total=7, max_side=750)
        return protocol.OcrTestResult(**{**base, **kwargs})

    # Matched on rung 0: the point is that NO border was needed, not that a rung is unnamed.
    assert protocol.format_ocr_test_result(
        result(detected=True, text="Victory!", pad_pct=0, pad_color="", stages_tried=1), "Victory",
    ) == (
        'DETECTED: "Victory" matched from the raw capture, with no border added '
        '(framing 1 of 7). Read: "Victory!"'
    )

    assert protocol.format_ocr_test_result(
        result(detected=True, text="Victory!", pad_pct=10, pad_color="black", stages_tried=2),
        "Victory",
    ) == (
        'DETECTED: "Victory" matched from a black border of 10% per side (framing 2 of 7). '
        'Read: "Victory!"'
    )

    # Read something, but not the expected text: the misread itself is the useful part.
    assert protocol.format_ocr_test_result(result(text="Vlctory"), "Victory") == (
        'NOT DETECTED: "Victory" was not found in any framing. Best read: "Vlctory". '
        "All 7 framings were tried."
    )

    assert protocol.format_ocr_test_result(result(), "Victory") == (
        "NOT DETECTED: the region read nothing at all. All 7 framings were tried."
    )

    # Cut short by the size cap: saying "all framings" here would be a lie the user acts on.
    assert protocol.format_ocr_test_result(
        result(text="Vlctory", stages_tried=3, capped=True), "Victory",
    ) == (
        'NOT DETECTED: "Victory" was not found in any framing. Best read: "Vlctory". '
        "Only 3 of 7 framings were tried: the wider borders would push this region past the "
        "750 px scan limit."
    )

    # No expected text: the question is only whether the region reads at all.
    assert protocol.format_ocr_test_result(
        result(detected=True, text="Victory!", pad_pct=50, pad_color="white"), "",
    ) == (
        'No expected text set. The region reads "Victory!" from a white border of 50% per side '
        "(framing 7 of 7)."
    )

    assert protocol.format_ocr_test_result(result(), "") == (
        "No expected text set, and the region read nothing. All 7 framings were tried."
    )
