from __future__ import annotations

from pathlib import Path

import pytest

from ipc.config_reader import read_config


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def test_reader_consumes_utf16le_bom_fixture_and_general_fields() -> None:
    assert FIXTURE.read_bytes().startswith(b"\xff\xfe")
    config = read_config(FIXTURE)
    general = config.general
    assert general.round_wait_seconds == 12.5
    assert general.after_place_click and general.remote_bridge_enabled
    # Tower loadout slots are the game's hotbar positions ("1".."6"), not names - see
    # TOWER_SLOT_CHOICES in app/main_window.py and the engine's own GeneralSlotDdls list.
    assert general.slots == ["3", "1", "6", "2", "4", "5", "1", "1", "1", "1"]
    assert general.disconnect_text == "Disconnected | retry"
    assert general.ocr_match_threshold == 0.6
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


def test_reader_retries_past_a_transient_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "config.ini"
    target.write_bytes(FIXTURE.read_bytes())
    real_read_text = Path.read_text
    call_count = 0

    def flaky_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        if self == target and call_count == 1:
            raise PermissionError(13, "Permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    config = read_config(target)

    assert call_count == 2
    assert config.general.coord_format == "percent"


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


# --------------------------------------------------------------------------------------------
# Agreement with the engine's own parsing. A value the two sides read differently is worse than
# one neither can read: the GUI shows one number, saves it back, and silently changes behavior.
# --------------------------------------------------------------------------------------------


def _write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.ini"
    path.write_bytes(("﻿" + text).encode("utf-16-le"))
    return path


def test_a_key_press_step_reads_its_own_four_fields(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "\r\n".join([
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition",
        "[Game_Anime Expedition_Presets]", "List=Main", "Active=Main",
        "[Game_Anime Expedition_Preset_Main]",
        "ScreenCount=1", "Screen1Name=Battle", "Screen1StepCount=1",
        "Screen1Step1Type=Key Press", "Screen1Step1Key=Space", "Screen1Step1HoldMs=1500",
        "Screen1Step1HoldAsync=1", "Screen1Step1HoldUntilStep=3. Click Button", "",
    ]))

    step = read_config(path).presets[0].screens[0].steps[0]

    assert (step.key, step.hold_ms, step.hold_async) == ("Space", 1500, True)
    assert step.hold_until_step == "3. Click Button"


def test_a_step_saved_before_key_press_existed_reads_as_a_step_that_holds_nothing(tmp_path: Path) -> None:
    # Every one of these keys is absent in a config written by an older build, and an absent key
    # must not become a hold: BuildScreenStepsFromIni defaults them the same way.
    path = _write_config(tmp_path, "\r\n".join([
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition",
        "[Game_Anime Expedition_Presets]", "List=Main", "Active=Main",
        "[Game_Anime Expedition_Preset_Main]",
        "ScreenCount=1", "Screen1Name=Battle", "Screen1StepCount=1",
        "Screen1Step1Type=Button Click", "",
    ]))

    step = read_config(path).presets[0].screens[0].steps[0]

    assert (step.key, step.hold_ms, step.hold_async, step.hold_until_step) == ("", 0, False, "")


def test_a_section_without_the_migration_marker_reads_its_legacy_camera_fields(tmp_path: Path) -> None:
    # GetMapAdvSteps() derives the list from CenterCamera/ZoomOut for a section that has no
    # AdvStepsMigrated marker. Reading only the numbered keys showed an EMPTY list for such a
    # section, and since the Map Advanced window saves back what it was showing, the user's first
    # save silently dropped a camera drag they never touched.
    path = _write_config(tmp_path, "\r\n".join([
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition",
        "[Game_Anime Expedition]",
        "CenterCamera=1", "CamStartX=10", "CamStartY=20", "CamEndX=30", "CamEndY=40",
        "ZoomOut=1", "ZoomTicks=7", "",
    ]))

    steps = read_config(path).general.adv_steps

    assert [(step.type, step.x, step.y, step.end_x, step.end_y) for step in steps] == [
        ("Drag", 10, 20, 30, 40), ("Zoom Out", 7, 0, 0, 0),
    ]
    # The engine's own defaults for the legacy pair, so whichever side reads the section first
    # writes back the same migrated list.
    assert steps[0].drag_ms == 500


def test_an_unmigrated_section_ignores_stray_numbered_keys_exactly_as_the_engine_does(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "\r\n".join([
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition",
        "[Game_Anime Expedition]",
        "AdvStepsCount=1", "AdvStep1Type=Drag", "AdvStep1X=99", "",
    ]))

    assert read_config(path).general.adv_steps == []


@pytest.mark.parametrize("marker", ["true", "yes", "on", "0", ""])
def test_only_the_literal_1_counts_as_migrated_exactly_as_the_engine_reads_it(
    tmp_path: Path, marker: str,
) -> None:
    # GetMapAdvSteps() asks `Cfg(...) != "1"`, a string compare - not a boolean parse. Reading these
    # spellings as "migrated" would put the two sides into exactly the disagreement the marker
    # exists to prevent: the GUI would show the numbered list while the engine still considered the
    # section legacy and overwrote it.
    path = _write_config(tmp_path, "\r\n".join([
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition",
        "[Game_Anime Expedition]",
        f"AdvStepsMigrated={marker}", "AdvStepsCount=1", "AdvStep1Type=Drag", "AdvStep1X=99", "",
    ]))

    general = read_config(path).general

    assert general.adv_steps == [] and not general.adv_steps_migrated


def test_the_literal_1_is_honoured_even_with_the_surrounding_space_iniread_trims(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "\r\n".join([
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition",
        "[Game_Anime Expedition]",
        "AdvStepsMigrated= 1 ", "AdvStepsCount=1", "AdvStep1Type=Drag", "AdvStep1X=99", "",
    ]))

    general = read_config(path).general

    assert general.adv_steps_migrated
    assert [(step.type, step.x) for step in general.adv_steps] == [("Drag", 99)]


def test_integers_round_and_accept_a_decimal_comma_like_safeint(tmp_path: Path) -> None:
    # SafeInt() is Integer(Round(Number(s))) after normalizing a comma to a period. int(float(...))
    # truncated instead ("1.6" -> 1) and rejected the German decimal comma outright ("1,5" -> 0).
    path = _write_config(tmp_path, "\r\n".join([
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition",
        "[Game_Anime Expedition]",
        "ClickDelayMs=1.6", "PlaceTowerDelayMs=1,5", "MarkerSize=2.5", "MaxRounds=-1.5", "",
    ]))

    general = read_config(path).general

    assert general.click_delay_ms == 2
    assert general.place_tower_delay_ms == 2
    # Half away from zero, like AHK's Round() - not Python's round(), which is half-to-even and
    # would give 2 here and 0 for 0.5.
    assert general.marker_size == 3
    assert general.max_rounds == -2


def test_a_missing_ocr_match_threshold_falls_back_to_the_engine_default(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "\r\n".join([
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition", "",
    ]))

    assert read_config(path).general.ocr_match_threshold == 0.75


# "nan" and "inf" are float() literals, so they parse where "not a number" does not, and "nan" in
# particular compares false against both bounds. Without their own guard the reader would hand a NaN
# to the percent conversion in main_window and crash the window on startup.
@pytest.mark.parametrize("value", ["not a number", "0.1", "1.5", "nan", "inf", "-inf"])
def test_ocr_match_threshold_invalid_values_fall_back_to_the_engine_default(
    tmp_path: Path, value: str,
) -> None:
    path = _write_config(tmp_path, "\r\n".join([
        "[General]", f"OcrMatchThreshold={value}",
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition", "",
    ]))

    assert read_config(path).general.ocr_match_threshold == 0.75


def test_ocr_match_threshold_accepts_a_german_decimal_comma(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "\r\n".join([
        "[General]", "OcrMatchThreshold=0,5",
        "[Games]", "List=Anime Expedition", "Active=Anime Expedition", "",
    ]))

    assert read_config(path).general.ocr_match_threshold == 0.5
