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
    assert (
        general.remote_agent_path,
        general.remote_server_url,
        general.remote_account_email,
    ) == (
        r"C:\Tools\animeexpedition-agent.exe",
        "https://remote.example.test",
        "trainer@example.test",
    )
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
    assert [step.type for step in main.screens[0].steps] == ["Button Click", "Wait", "Drag"]
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
    # "Alt Screen" has no matching global registry entry (manual reconciliation, not auto-linking):
    # it stays fully custom/unlinked, exactly like before the global registry existed.
    assert not alternate.screens[0].use_global_detection


def test_reader_resolves_a_globally_linked_screen_against_the_registry() -> None:
    config = read_config(FIXTURE)
    assert [screen.name for screen in config.global_screens] == ["Battle"]
    battle = config.global_screens[0]
    assert (battle.detection_type, battle.detection_x, battle.detection_text) == ("Ingame Detection", 1.5, "Victory")

    main = config.presets[0]
    linked = main.screens[1]
    assert linked.name == "Battle" and linked.use_global_detection
    # The preset's own local Detection* fields are deliberately stale in the fixture (999/"STALE
    # LOCAL VALUE") to prove a linked screen is resolved against the GLOBAL entry, never the local
    # mirror/backup - mirrors ResolveScreenDetection() in tower_defense_macro_gui.ahk.
    assert (linked.detection_type, linked.detection_x, linked.detection_text) == ("Ingame Detection", 1.5, "Victory")
    # DefaultScreen always stays preset-local, linked or not - it names another screen within this
    # preset's own jump graph.
    assert linked.default_screen == "Lobby"


def test_reader_reconstructs_screen_entry_detection_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[Presets]\nList=Main\n\n[Preset_Main]\nScreenCount=1\n"
        "Screen1Name=Lobby\nScreen1StepCount=0\n"
        "Screen1DetectionType=Custom Detection\nScreen1DetectionX=10.5\n"
        "Screen1DetectionY=20.25\nScreen1DetectionEndX=30.75\n"
        "Screen1DetectionEndY=40.5\nScreen1DetectionText=Ready\n"
        "Screen1DefaultScreen=Lobby\n",
        encoding="utf-16",
    )

    screen = read_config(config_path).presets[0].screens[0]

    assert (
        screen.detection_type, screen.detection_x, screen.detection_y,
        screen.detection_end_x, screen.detection_end_y, screen.detection_text,
        screen.default_screen,
    ) == ("Custom Detection", 10.5, 20.25, 30.75, 40.5, "Ready", "Lobby")


def test_reader_falls_back_to_local_values_when_linked_but_no_global_entry_exists(tmp_path: Path) -> None:
    # UseGlobalDetection=1 with no matching [Screen_<name>] (e.g. right after a rename detached the
    # name from its old link, or a config predating the registry) must not crash or show blank
    # values - it falls back to this preset's own local storage, same as an unlinked screen.
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[Presets]\nList=Main\n\n[Preset_Main]\nScreenCount=1\n"
        "Screen1Name=Orphaned\nScreen1StepCount=0\n"
        "Screen1DetectionType=Custom Detection\nScreen1DetectionX=1\n"
        "Screen1DetectionY=2\nScreen1DetectionEndX=3\nScreen1DetectionEndY=4\n"
        "Screen1DetectionText=Local\nScreen1DefaultScreen=Orphaned\nScreen1UseGlobalDetection=1\n",
        encoding="utf-16",
    )

    screen = read_config(config_path).presets[0].screens[0]

    assert screen.use_global_detection
    assert (screen.detection_type, screen.detection_x, screen.detection_text) == ("Custom Detection", 1, "Local")


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
