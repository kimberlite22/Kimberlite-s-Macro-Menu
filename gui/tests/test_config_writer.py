from __future__ import annotations

import os
from pathlib import Path

import pytest

from ipc.config_reader import read_config
from ipc.config_writer import (
    BACKUP_KEEP,
    ConfigValidationError,
    IniDocument,
    MutationError,
    adv_steps_section,
    apply_adv_steps,
    apply_general,
    apply_map_profile,
    apply_preset,
    backup_config,
    create_game,
    create_map_profile,
    create_preset,
    delete_game,
    delete_map_profile,
    delete_preset,
    export_preset,
    import_preset,
    rename_game,
    rename_map_profile,
    rename_preset,
    save_config,
    set_active_game,
    set_option_max,
    set_option_used_count,
    validate_general,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.ini"
    path.write_bytes(("\ufeff" + text).encode("utf-16-le"))
    return path


# --------------------------------------------------------------------------------------------
# The property everything else rests on: a file this module did not write survives untouched.
# --------------------------------------------------------------------------------------------


def test_load_and_save_without_edits_is_byte_identical(tmp_path: Path) -> None:
    # As AHK's own IniWrite leaves it: UTF-16LE, BOM, CRLF. The fixture is stored with LF, so
    # normalize it first - a file in the shape the engine actually writes must survive a load and
    # save with not one byte changed.
    text = FIXTURE.read_bytes().decode("utf-16").replace("\r\n", "\n").replace("\n", "\r\n")
    path = _write(tmp_path, text)
    original = path.read_bytes()

    IniDocument.load(path).write_atomic(path)

    assert path.read_bytes() == original


def test_lf_line_endings_are_normalized_to_the_crlf_the_engine_writes(tmp_path: Path) -> None:
    path = _write(tmp_path, "[General]\nHoleW=1248\n")

    IniDocument.load(path).write_atomic(path)

    assert path.read_bytes().decode("utf-16") == "[General]\r\nHoleW=1248\r\n"


def test_unmodelled_keys_survive_a_general_save(tmp_path: Path) -> None:
    # Every one of these is a real key the engine or an older version wrote and that no dataclass
    # in config_reader models. Serializing from the typed model instead of editing the file would
    # delete all of them.
    path = _write(tmp_path, "\r\n".join([
        "[General]",
        "StartX=0",
        "RegionX1=760",
        "ScreenWidth=1920",
        "CenterCamera=1",
        "ZoomTicks=50",
        "RoundEndText=Repeat Stage",
        "CoordFormat=percent",
        "ScreenDetectionSchema=v2",
        "HoleW=1248",
        "",
        "[Game_Anime Expedition]",
        "AdvStepsMigrated=1",
        "",
    ]))

    document = IniDocument.load(path)
    apply_general(document, {"holeW": 1300, "clickDelayMs": 250}, "Anime Expedition")
    document.write_atomic(path)

    saved = IniDocument.load(path)
    assert saved.get("General", "RegionX1") == "760"
    assert saved.get("General", "CenterCamera") == "1"
    assert saved.get("General", "RoundEndText") == "Repeat Stage"
    assert saved.get("General", "CoordFormat") == "percent"
    assert saved.get("General", "ScreenDetectionSchema") == "v2"
    assert saved.get("General", "HoleW") == "1300"
    assert saved.get("Game_Anime Expedition", "AdvStepsMigrated") == "1"
    assert saved.get("Game_Anime Expedition", "ClickDelayMs") == "250"


def test_comments_blank_lines_and_key_order_survive(tmp_path: Path) -> None:
    path = _write(tmp_path, "\r\n".join([
        "; a hand written note",
        "[General]",
        "HoleW=1248",
        "HoleH=702",
        "",
        "[Presets]",
        "List=Alpha",
        "",
    ]))

    document = IniDocument.load(path)
    document.set("General", "HoleH", 800)
    document.write_atomic(path)

    lines = path.read_bytes().decode("utf-16").splitlines()
    assert lines[0] == "; a hand written note"
    assert lines[1:4] == ["[General]", "HoleW=1248", "HoleH=800"]
    assert "[Presets]" in lines


# --------------------------------------------------------------------------------------------
# Encoding and atomicity: what the AHK side depends on byte for byte.
# --------------------------------------------------------------------------------------------


def test_written_file_is_utf16le_with_bom_and_crlf(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    document = IniDocument.from_text("[General]\nHoleW=1248\n")
    document.write_atomic(path)

    raw = path.read_bytes()
    assert raw.startswith(b"\xff\xfe")
    # decode("utf-16") consumes the BOM, so this is the exact payload AHK's IniRead sees.
    assert raw.decode("utf-16") == "[General]\r\nHoleW=1248\r\n"


def test_write_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    IniDocument.from_text("[General]\nHoleW=1248\n").write_atomic(path)
    assert [entry.name for entry in tmp_path.iterdir()] == ["config.ini"]


def test_reader_round_trips_a_document_written_here(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_bytes(FIXTURE.read_bytes())
    before = read_config(path)

    IniDocument.load(path).write_atomic(path)

    assert read_config(path) == before


# --------------------------------------------------------------------------------------------
# Value formatting: what the engine's SafeInt/SafeNum have to be able to read back.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "1"),
        (False, "0"),
        (5, "5"),
        (50.0, "50"),
        (32.051, "32.051"),
        # The exact float a JSON round trip of 32.051 produced in the shipped config.
        (32.051000000000002, "32.051"),
        (65.704999999999998, "65.705"),
        (None, ""),
        ("Repeat Stage", "Repeat Stage"),
    ],
)
def test_value_formatting(tmp_path: Path, value: object, expected: str) -> None:
    document = IniDocument()
    document.set("General", "Probe", value)
    assert document.get("General", "Probe") == expected


def test_newlines_in_a_value_cannot_split_it_into_a_second_line() -> None:
    document = IniDocument()
    document.set("General", "DisconnectText", "line one\r\nHoleW=0")
    assert document.get("General", "DisconnectText") == "line one  HoleW=0"
    assert len(document.to_text().splitlines()) == 2


# --------------------------------------------------------------------------------------------
# AHK INI semantics.
# --------------------------------------------------------------------------------------------


def test_lookup_is_case_insensitive_and_keeps_the_files_own_spelling() -> None:
    document = IniDocument.from_text("[general]\nholew=1248\n")
    assert document.get("General", "HoleW") == "1248"

    document.set("GENERAL", "HOLEW", 900)
    assert document.to_text() == "[general]\r\nholew=900\r\n"


def test_a_new_key_lands_inside_its_section_not_after_the_next_one() -> None:
    document = IniDocument.from_text("[General]\nHoleW=1248\n\n[Presets]\nList=Alpha\n")
    document.set("General", "HoleH", 702)

    lines = document.to_text().splitlines()
    assert lines.index("HoleH=702") < lines.index("[Presets]")


def test_a_missing_section_is_created_at_the_end() -> None:
    document = IniDocument.from_text("[General]\nHoleW=1248\n")
    document.set("MapProfile_New", "ExpectedText", "Tomb")
    assert document.to_text().endswith("[MapProfile_New]\r\nExpectedText=Tomb\r\n")


# --------------------------------------------------------------------------------------------
# Payload application, against the AHK writers these replace.
# --------------------------------------------------------------------------------------------


def test_apply_general_writes_every_slot() -> None:
    document = IniDocument()
    apply_general(document, {"slots": [str(index) for index in range(1, 11)]}, "Anime Expedition")
    assert [document.get("Game_Anime Expedition", f"Slot{i}") for i in range(1, 11)] == [
        str(index) for index in range(1, 11)
    ]


def test_apply_general_only_touches_the_keys_it_was_given() -> None:
    document = IniDocument.from_text("[General]\nHoleW=1248\n[Game_Anime Expedition]\nClickDelayMs=300\n")
    apply_general(document, {"holeW": 1300}, "Anime Expedition")
    assert document.get("Game_Anime Expedition", "ClickDelayMs") == "300"


def test_apply_general_splits_shared_and_game_scoped_keys() -> None:
    document = IniDocument()
    apply_general(document, {
        "holeW": 1300, "clickDelayMs": 250,
        "privateServerLink": "https://www.roblox.com/share?code=abc&type=Server",
    }, "Anime Expedition")
    assert document.get("General", "HoleW") == "1300"
    assert document.get("General", "PrivateServerLink") == "https://www.roblox.com/share?code=abc&type=Server"
    assert document.get("General", "ClickDelayMs", "<absent>") == "<absent>"
    assert document.get("Game_Anime Expedition", "PrivateServerLink", "<absent>") == "<absent>"
    assert document.get("Game_Anime Expedition", "ClickDelayMs") == "250"
    assert document.get("Game_Anime Expedition", "HoleW", "<absent>") == "<absent>"


def test_private_server_link_round_trips_through_the_general_section(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_bytes(FIXTURE.read_bytes())
    link = "https://www.roblox.com/share?code=abc&type=Server"

    save_config(path, game="Anime Expedition", general={
        "holeW": 1280, "holeH": 720, "privateServerLink": link,
    })

    assert read_config(path).general.private_server_link == link


def test_apply_preset_removes_the_steps_of_a_screen_that_was_deleted() -> None:
    document = IniDocument.from_text("\n".join([
        "[Game_Anime Expedition_Preset_Alpha]",
        "ScreenCount=2",
        "Screen1Name=Lobby",
        "Screen1StepCount=1",
        "Screen1Step1Type=Button Click",
        "Screen2Name=Battle",
        "Screen2StepCount=1",
        "Screen2Step1Type=Wait",
        "BackX=10",
        "",
    ]))

    apply_preset(document, {
        "name": "Alpha",
        "screens": [{"name": "Lobby", "steps": [{"type": "Button Click"}]}],
        "options": [{}, {}, {}],
        "defaultMap": "", "backX": 10, "backY": 0, "fallbackScreen": "",
    }, "Anime Expedition")

    assert document.get("Game_Anime Expedition_Preset_Alpha", "ScreenCount") == "1"
    assert document.get("Game_Anime Expedition_Preset_Alpha", "Screen2Name", "<gone>") == "<gone>"
    assert document.get("Game_Anime Expedition_Preset_Alpha", "Screen2Step1Type", "<gone>") == "<gone>"
    # A non-screen key of the same section is left alone by the screen rebuild.
    assert document.get("Game_Anime Expedition_Preset_Alpha", "BackX") == "10"


def test_apply_preset_requires_exactly_three_options() -> None:
    with pytest.raises(ValueError):
        apply_preset(
            IniDocument(), {"name": "Alpha", "screens": [], "options": [{}, {}]}, "Anime Expedition"
        )


def test_apply_map_profile_rejects_more_than_ten_placements() -> None:
    with pytest.raises(ValueError):
        apply_map_profile(
            IniDocument(), {"name": "Tomb", "placements": [{} for _ in range(11)]}, "Anime Expedition"
        )


def test_adv_steps_section_follows_the_custom_camera_flag() -> None:
    document = IniDocument.from_text(
        "[Game_Anime Expedition_MapProfile_Tomb]\nCustomCamera=1\n"
        "[Game_Anime Expedition_MapProfile_Ruins]\nCustomCamera=0\n"
    )
    assert adv_steps_section(document, "Tomb", "Anime Expedition") == "Game_Anime Expedition_MapProfile_Tomb"
    assert adv_steps_section(document, "Ruins", "Anime Expedition") == "Game_Anime Expedition"
    assert adv_steps_section(document, "General", "Anime Expedition") == "Game_Anime Expedition"


def test_apply_adv_steps_writes_count_and_fields() -> None:
    document = IniDocument()
    apply_adv_steps(document, "General", [
        {"type": "Drag", "x": 49.679, "y": 11.396, "endX": 49.679, "endY": 78.348, "dragMs": 500},
    ])
    assert document.get("General", "AdvStepsCount") == "1"
    assert document.get("General", "AdvStep1Type") == "Drag"
    assert document.get("General", "AdvStep1X") == "49.679"
    assert document.get("General", "AdvStep1DragMs") == "500"


# --------------------------------------------------------------------------------------------
# Validation and backups.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [
    {"holeW": 0, "holeH": 702},
    {"holeW": 1248, "holeH": 0},
    {"holeW": 0, "holeH": 0},
    {},
])
def test_a_zero_size_opening_is_refused(payload: dict[str, object]) -> None:
    with pytest.raises(ConfigValidationError):
        validate_general(payload)


def test_a_usable_opening_passes() -> None:
    validate_general({"holeW": 1248, "holeH": 702})


def test_backup_snapshots_the_file_and_prunes_to_the_newest(tmp_path: Path) -> None:
    path = _write(tmp_path, "[General]\r\nHoleW=1248\r\n")
    backup_dir = tmp_path / "config_backups"
    backup_dir.mkdir()
    for index in range(BACKUP_KEEP + 4):
        (backup_dir / f"config_20260101_0000{index:02d}.ini").write_bytes(b"old")
    # A file that does not match the snapshot pattern must never be pruned.
    (backup_dir / "keep_me.txt").write_bytes(b"unrelated")

    backup_config(path)

    snapshots = sorted(entry.name for entry in backup_dir.glob("config_*.ini"))
    assert len(snapshots) == BACKUP_KEEP
    assert (backup_dir / "keep_me.txt").exists()
    # The pruned ones are the oldest by name, which is also oldest by time for this stamp format.
    assert "config_20260101_000000.ini" not in snapshots


def test_backup_of_a_missing_config_is_a_no_op(tmp_path: Path) -> None:
    backup_config(tmp_path / "does_not_exist.ini")
    assert not (tmp_path / "config_backups").exists()


def test_write_creates_a_missing_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.ini"
    IniDocument.from_text("[General]\nHoleW=1248\n").write_atomic(path)
    assert path.exists()


def test_a_reader_never_observes_a_partially_written_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the atomic replace: the old bytes stay readable until the new ones are complete.

    Simulated by reading the file after the temp copy exists but before the replace lands, which is
    exactly the window that used to expose a truncated config to the 250ms poll.
    """
    path = _write(tmp_path, "[General]\r\nHoleW=1248\r\n")
    document = IniDocument.load(path)
    document.set("General", "HoleW", 1300)

    observed: list[str] = []
    original_replace = os.replace

    def replace_spy(source, target):  # type: ignore[no-untyped-def]
        observed.append(IniDocument.load(path).get("General", "HoleW"))
        original_replace(source, target)

    monkeypatch.setattr(os, "replace", replace_spy)
    document.write_atomic(path)
    monkeypatch.undo()

    assert observed == ["1248"], "the old value must still be readable until the replace happens"
    assert IniDocument.load(path).get("General", "HoleW") == "1300"


# --------------------------------------------------------------------------------------------
# Structural mutations: create/rename/delete a preset or map profile, export/import, usage counts.
# --------------------------------------------------------------------------------------------


GAME = "Anime Expedition"


def _presets_config(tmp_path: Path, names: list[str], active: str = "") -> Path:
    lines = [f"[Game_{GAME}_Presets]", f"List={','.join(names)}"]
    if active:
        lines.append(f"Active={active}")
    for name in names:
        lines += [f"[Game_{GAME}_Preset_{name}]", "ScreenCount=0", "BackX=1"]
    return _write(tmp_path, "\r\n".join(lines) + "\r\n")


def test_create_preset_adds_a_default_preset_to_the_list(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])

    message = create_preset(path, "Beta", game=GAME)

    assert message == "Preset 'Beta' created."
    document = IniDocument.load(path)
    assert document.get(f"Game_{GAME}_Presets", "List") == "Alpha,Beta"
    assert document.get(f"Game_{GAME}_Preset_Beta", "ScreenCount") == "1"
    assert document.get(f"Game_{GAME}_Preset_Beta", "Screen1Name") == "Screen 1"
    assert document.get(f"Game_{GAME}_Preset_Beta", "Option3Priority") == "3"
    # A new preset is created for editing but must NOT become the active (running) one.
    assert document.get(f"Game_{GAME}_Presets", "Active", "<absent>") == "<absent>"


def test_create_preset_rejects_a_duplicate_case_insensitively(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])
    with pytest.raises(MutationError, match="already exists"):
        create_preset(path, "alpha", game=GAME)


def test_create_preset_rejects_an_empty_name(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])
    with pytest.raises(MutationError, match="cannot be empty"):
        create_preset(path, "   ", game=GAME)


def test_rename_preset_moves_the_section_and_list_and_active_entry(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha", "Beta"], active="Alpha")

    message = rename_preset(path, "Alpha", "Gamma", game=GAME)

    assert message == "Preset renamed to 'Gamma'."
    document = IniDocument.load(path)
    assert document.get(f"Game_{GAME}_Presets", "List") == "Gamma,Beta"
    assert document.get(f"Game_{GAME}_Presets", "Active") == "Gamma"
    assert document.get(f"Game_{GAME}_Preset_Gamma", "BackX") == "1"
    assert document.has_section(f"Game_{GAME}_Preset_Alpha") is False


def test_rename_preset_leaves_active_alone_when_a_different_preset_was_renamed(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha", "Beta"], active="Alpha")

    rename_preset(path, "Beta", "Gamma", game=GAME)

    assert IniDocument.load(path).get(f"Game_{GAME}_Presets", "Active") == "Alpha"


def test_rename_preset_rejects_a_duplicate_and_an_unknown_source(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha", "Beta"])
    with pytest.raises(MutationError, match="already exists"):
        rename_preset(path, "Alpha", "beta", game=GAME)
    with pytest.raises(MutationError, match="Unknown preset"):
        rename_preset(path, "Ghost", "Delta", game=GAME)


def test_rename_preset_refuses_the_currently_running_preset(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha", "Beta"])
    with pytest.raises(MutationError, match="currently running"):
        rename_preset(path, "Alpha", "Gamma", game=GAME, running=True, running_preset="Alpha")


def test_delete_preset_removes_the_section_and_falls_active_back(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha", "Beta"], active="Alpha")

    message = delete_preset(path, "Alpha", game=GAME)

    assert message == "Preset deleted."
    document = IniDocument.load(path)
    assert document.get(f"Game_{GAME}_Presets", "List") == "Beta"
    assert document.get(f"Game_{GAME}_Presets", "Active") == "Beta"
    assert document.has_section(f"Game_{GAME}_Preset_Alpha") is False


def test_delete_preset_refuses_the_last_one_and_the_running_one(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])
    with pytest.raises(MutationError, match="At least one preset"):
        delete_preset(path, "Alpha", game=GAME)

    path = _presets_config(tmp_path, ["Alpha", "Beta"])
    with pytest.raises(MutationError, match="currently running"):
        delete_preset(path, "Alpha", game=GAME, running=True, running_preset="Alpha")


def test_export_then_import_preset_round_trips_every_key(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])
    export_path = tmp_path / "exported.ini"

    export_message = export_preset(path, "Alpha", str(export_path.with_suffix("")), game=GAME)
    assert export_path.exists()
    assert "exported to" in export_message

    import_message = import_preset(path, str(export_path), "Copy", game=GAME)
    assert import_message == "Preset 'Copy' imported."
    document = IniDocument.load(path)
    assert document.get(f"Game_{GAME}_Presets", "List") == "Alpha,Copy"
    assert document.get(f"Game_{GAME}_Preset_Copy", "ScreenCount") == "0"
    assert document.get(f"Game_{GAME}_Preset_Copy", "BackX") == "1"


def test_export_preset_rejects_an_unknown_preset(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])
    with pytest.raises(MutationError, match="Unknown preset"):
        export_preset(path, "Ghost", str(tmp_path / "out.ini"), game=GAME)


def test_import_preset_rejects_a_file_without_a_preset_section(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])
    bogus = tmp_path / "not_a_preset.ini"
    IniDocument.from_text("[Other]\nKey=Value\n").write_atomic(bogus)
    with pytest.raises(MutationError, match="doesn't look like an exported preset"):
        import_preset(path, str(bogus), "Copy", game=GAME)


def test_import_preset_rejects_a_duplicate_name(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])
    export_path = tmp_path / "exported.ini"
    export_preset(path, "Alpha", str(export_path), game=GAME)
    with pytest.raises(MutationError, match="already exists"):
        import_preset(path, str(export_path), "alpha", game=GAME)


def _map_profiles_config(tmp_path: Path, names: list[str], active: str = "") -> Path:
    lines = [f"[Game_{GAME}_MapProfiles]", f"List={','.join(names)}"]
    if active:
        lines.append(f"Active={active}")
    for name in names:
        lines += [
            f"[Game_{GAME}_MapProfile_{name}]", "ExpectedText=" + name, "CustomCamera=1",
            "AdvStep1Type=Drag",
        ]
    return _write(tmp_path, "\r\n".join(lines) + "\r\n")


def test_create_map_profile_adds_defaults_and_becomes_active(tmp_path: Path) -> None:
    path = _map_profiles_config(tmp_path, ["Forest"])

    message = create_map_profile(path, "Desert", game=GAME)

    assert message == "Map profile 'Desert' created."
    document = IniDocument.load(path)
    assert document.get(f"Game_{GAME}_MapProfiles", "List") == "Forest,Desert"
    # Unlike a new preset, a new map profile DOES become the active one.
    assert document.get(f"Game_{GAME}_MapProfiles", "Active") == "Desert"
    assert document.get(f"Game_{GAME}_MapProfile_Desert", "CustomNumPlacements") == "4"
    assert document.get(f"Game_{GAME}_MapProfile_Desert", "CustomCamera") == "0"


def test_rename_map_profile_carries_its_camera_steps_along(tmp_path: Path) -> None:
    path = _map_profiles_config(tmp_path, ["Forest"], active="Forest")

    rename_map_profile(path, "Forest", "Jungle", game=GAME)

    document = IniDocument.load(path)
    assert document.get(f"Game_{GAME}_MapProfiles", "List") == "Jungle"
    assert document.get(f"Game_{GAME}_MapProfiles", "Active") == "Jungle"
    assert document.get(f"Game_{GAME}_MapProfile_Jungle", "AdvStep1Type") == "Drag"
    assert document.has_section(f"Game_{GAME}_MapProfile_Forest") is False


def test_rename_and_delete_map_profile_refuse_while_running(tmp_path: Path) -> None:
    path = _map_profiles_config(tmp_path, ["Forest", "Desert"])
    with pytest.raises(MutationError, match="while the macro is running"):
        rename_map_profile(path, "Forest", "Jungle", game=GAME, running=True)
    with pytest.raises(MutationError, match="while the macro is running"):
        delete_map_profile(path, "Forest", game=GAME, running=True)


def test_delete_map_profile_refuses_the_last_one(tmp_path: Path) -> None:
    path = _map_profiles_config(tmp_path, ["Forest"])
    with pytest.raises(MutationError, match="At least one map profile"):
        delete_map_profile(path, "Forest", game=GAME)


def test_set_option_used_count_and_max_write_the_expected_keys(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])

    set_option_used_count(path, "Alpha", 2, -5, game=GAME)
    set_option_max(path, "Alpha", 2, 7, game=GAME)

    document = IniDocument.load(path)
    assert document.get(f"Game_{GAME}_Preset_Alpha", "Option2UsedCount") == "0"  # floored at zero
    assert len(document.get(f"Game_{GAME}_Preset_Alpha", "Option2UsedDate")) == 8  # yyyyMMdd
    assert document.get(f"Game_{GAME}_Preset_Alpha", "Option2MaxUses") == "7"


def test_set_option_used_count_rejects_an_unknown_preset(tmp_path: Path) -> None:
    path = _presets_config(tmp_path, ["Alpha"])
    with pytest.raises(MutationError, match="Unknown preset"):
        set_option_used_count(path, "Ghost", 1, 3, game=GAME)


# --------------------------------------------------------------------------------------------
# Game management: create/rename/delete/switch which game's sections are active.
# --------------------------------------------------------------------------------------------


def _games_config(tmp_path: Path, names: list[str], active: str = "") -> Path:
    lines = ["[Games]", f"List={','.join(names)}"]
    if active:
        lines.append(f"Active={active}")
    return _write(tmp_path, "\r\n".join(lines) + "\r\n")


def test_create_game_seeds_a_default_preset_and_map_profile(tmp_path: Path) -> None:
    path = _games_config(tmp_path, ["Alpha"])

    message = create_game(path, "Beta")

    assert message == "Game 'Beta' created."
    document = IniDocument.load(path)
    assert document.get("Games", "List") == "Alpha,Beta"
    # A new game is created for editing but must NOT become the active one.
    assert document.get("Games", "Active", "<absent>") == "<absent>"
    assert document.get("Game_Beta_Presets", "List") == "Challenges"
    assert document.get("Game_Beta_Preset_Challenges", "ScreenCount") == "1"
    assert document.get("Game_Beta_MapProfiles", "List") == "Default"
    assert document.get("Game_Beta_MapProfile_Default", "CustomNumPlacements") == "4"
    assert document.get("Game_Beta", "NumPlacements") == "4"
    # Explicit non-zero defaults, not left absent - see create_game()'s own comment: an absent key
    # reads back as 0 through config_reader.py (unlike the engine's own Cfg() fallback), and an
    # untouched Save would then persist that 0 as a real setting.
    assert document.get("Game_Beta", "ClickDelayMs") == "300"
    assert document.get("Game_Beta", "PlaceTowerDelayMs") == "100"
    assert document.get("Game_Beta", "MarkerSize") == "4"


def test_create_game_rejects_a_duplicate_case_insensitively(tmp_path: Path) -> None:
    path = _games_config(tmp_path, ["Alpha"])
    with pytest.raises(MutationError, match="already exists"):
        create_game(path, "alpha")


def test_rename_game_moves_every_section_it_owns(tmp_path: Path) -> None:
    # Active is deliberately "Beta", not "Alpha" - renaming the active game is refused outright
    # (see test_rename_and_delete_game_refuse_the_active_game), regardless of running state.
    path = _games_config(tmp_path, ["Alpha", "Beta"], active="Beta")
    document = IniDocument.load(path)
    document.set("Game_Alpha", "NumPlacements", 4)
    document.set("Game_Alpha_Presets", "List", "Challenges")
    document.set("Game_Alpha_Presets", "Active", "Challenges")
    document.set("Game_Alpha_Preset_Challenges", "ScreenCount", 0)
    document.set("Game_Alpha_MapProfiles", "List", "Default")
    document.set("Game_Alpha_MapProfiles", "Active", "Default")
    document.set("Game_Alpha_MapProfile_Default", "ExpectedText", "Default")
    document.write_atomic(path)

    message = rename_game(path, "Alpha", "Gamma")

    assert message == "Game renamed to 'Gamma'."
    document = IniDocument.load(path)
    assert document.get("Games", "List") == "Gamma,Beta"
    assert document.get("Games", "Active") == "Beta"  # unaffected: Alpha (renamed) was not active
    assert document.get("Game_Gamma", "NumPlacements") == "4"
    assert document.get("Game_Gamma_Presets", "List") == "Challenges"
    assert document.get("Game_Gamma_Preset_Challenges", "ScreenCount") == "0"
    assert document.get("Game_Gamma_MapProfiles", "List") == "Default"
    assert document.get("Game_Gamma_MapProfile_Default", "ExpectedText") == "Default"
    assert document.has_section("Game_Alpha") is False
    assert document.has_section("Game_Alpha_Presets") is False
    assert document.has_section("Game_Alpha_Preset_Challenges") is False
    assert document.has_section("Game_Alpha_MapProfiles") is False
    assert document.has_section("Game_Alpha_MapProfile_Default") is False


def test_rename_and_delete_game_refuse_while_running(tmp_path: Path) -> None:
    path = _games_config(tmp_path, ["Alpha", "Beta"])
    with pytest.raises(MutationError, match="while the macro is running"):
        rename_game(path, "Alpha", "Gamma", running=True)
    with pytest.raises(MutationError, match="while the macro is running"):
        delete_game(path, "Alpha", running=True)


def test_rename_and_delete_game_refuse_the_active_game(tmp_path: Path) -> None:
    # Even when idle (not running): the AHK engine's ActiveGameName is fixed for its process
    # lifetime, so renaming/deleting the active game out from under a not-yet-restarted engine
    # would leave it pointed at sections that no longer exist.
    path = _games_config(tmp_path, ["Alpha", "Beta"], active="Alpha")
    with pytest.raises(MutationError, match="active game"):
        rename_game(path, "Alpha", "Gamma")
    with pytest.raises(MutationError, match="active game"):
        delete_game(path, "Alpha")
    # A non-active game is unaffected.
    rename_game(path, "Beta", "Gamma")
    assert IniDocument.load(path).get("Games", "List") == "Alpha,Gamma"


def test_delete_game_removes_every_section_it_owns_and_falls_active_back(tmp_path: Path) -> None:
    path = _games_config(tmp_path, ["Alpha", "Beta"], active="Alpha")
    document = IniDocument.load(path)
    document.set("Game_Beta_Presets", "List", "Challenges")
    document.set("Game_Beta_Preset_Challenges", "ScreenCount", 0)
    document.set("Game_Beta_MapProfiles", "List", "Default")
    document.set("Game_Beta_MapProfile_Default", "ExpectedText", "Default")
    document.write_atomic(path)

    message = delete_game(path, "Beta")

    assert message == "Game deleted."
    document = IniDocument.load(path)
    assert document.get("Games", "List") == "Alpha"
    assert document.get("Games", "Active") == "Alpha"
    assert document.has_section("Game_Beta_Presets") is False
    assert document.has_section("Game_Beta_Preset_Challenges") is False
    assert document.has_section("Game_Beta_MapProfiles") is False
    assert document.has_section("Game_Beta_MapProfile_Default") is False


def test_delete_game_refuses_the_last_one(tmp_path: Path) -> None:
    path = _games_config(tmp_path, ["Alpha"])
    with pytest.raises(MutationError, match="At least one game"):
        delete_game(path, "Alpha")


def test_set_active_game_writes_games_active(tmp_path: Path) -> None:
    path = _games_config(tmp_path, ["Alpha", "Beta"], active="Alpha")

    message = set_active_game(path, "Beta")

    assert message == "Active game set to 'Beta'."
    assert IniDocument.load(path).get("Games", "Active") == "Beta"


def test_set_active_game_rejects_an_unknown_game(tmp_path: Path) -> None:
    path = _games_config(tmp_path, ["Alpha"])
    with pytest.raises(MutationError, match="Unknown game"):
        set_active_game(path, "Ghost")


def test_set_active_game_refuses_while_running(tmp_path: Path) -> None:
    path = _games_config(tmp_path, ["Alpha", "Beta"], active="Alpha")
    with pytest.raises(MutationError, match="while the macro is running"):
        set_active_game(path, "Beta", running=True)
