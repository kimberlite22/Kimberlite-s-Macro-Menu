from __future__ import annotations

from pathlib import Path

from ipc.config_reader import read_config


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def test_reader_consumes_utf16le_bom_fixture_and_general_fields() -> None:
    assert FIXTURE.read_bytes().startswith(b"\xff\xfe")
    config = read_config(FIXTURE)
    general = config.general
    assert general.round_wait_seconds == 12.5
    assert general.after_place_click and general.remote_bridge_enabled
    assert general.slots == ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta", "Iota", "Kappa"]
    assert general.disconnect_text == "Disconnected | retry"
    assert general.coord_format == "percent" and general.adv_steps_migrated
    assert [(step.type, step.x, step.end_x, step.drag_ms) for step in general.adv_steps] == [
        ("Camera Drag", 10, 30, 500), ("Zoom Out", -3, 0, 0), ("Click", 90.5, 0, 0),
    ]


def test_reader_reconstructs_presets_screens_steps_and_options() -> None:
    config = read_config(FIXTURE)
    assert config.active_preset == "Alternate! Preset"
    assert [preset.name for preset in config.presets] == ["Main Preset", "Alternate! Preset"]
    main = config.presets[0]
    assert main.default_map == "Forest Map" and (main.back_x, main.back_y) == (44.4, 55.5)
    assert [screen.name for screen in main.screens] == ["Lobby", "Battle"]
    assert [step.type for step in main.screens[0].steps] == ["Click", "Wait", "Drag"]
    first = main.screens[0].steps[0]
    assert first.label == "Start | now" and first.once_per_cycle
    assert first.on_true_screen == "Battle" and first.fallback_enabled and first.advanced
    assert first.fallback_max_attempts == 4 and first.outcomes_raw == "Victory>Win|Defeat>Lose"
    assert (main.screens[0].steps[2].end_x, main.screens[0].steps[2].drag_ms) == (30, 350)
    assert len(main.options) == 3
    option = main.options[0]
    assert option.available and option.det_invert and option.max_uses == 7
    assert (option.used_count, option.used_date, option.det_text) == (2, "2026-07-29", "Ready | Go")
    alternate = config.presets[1]
    assert alternate.screens[0].name == "Alt Screen" and alternate.options[2].name == ""


def test_reader_reconstructs_map_profiles_and_custom_camera_branch() -> None:
    config = read_config(FIXTURE)
    assert config.active_map_profile == "Forest Map"
    forest, desert = config.map_profiles
    assert forest.custom_towers and forest.custom_camera and forest.custom_num_placements == 3
    assert [(placement.custom_slot, placement.x, placement.y) for placement in forest.placements[:3]] == [
        ("Alpha", 11, 12), ("Beta", 21, 22), ("Gamma", 31, 32),
    ]
    assert [(step.type, step.drag_ms) for step in forest.adv_steps] == [("Camera Drag", 600), ("Zoom In", 0)]
    assert not desert.custom_towers and not desert.custom_camera
    assert len(desert.placements) == 10 and desert.adv_steps == []
