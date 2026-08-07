from __future__ import annotations

from pathlib import Path

from app import roblox_display


# A trimmed copy of the real GlobalBasicSettings_13.xml: enough neighbouring settings to prove the
# rest of the file survives, and the two window-state elements that make Fullscreen the right one to
# write (StartScreenSize is what Roblox otherwise remembers, which is where the resizing came from).
SETTINGS = (
    '<roblox version="4">\n'
    '\t<Item class="UserGameSettings">\n'
    "\t\t<Properties>\n"
    '\t\t\t<int name="FramerateCap">240</int>\n'
    '\t\t\t<bool name="Fullscreen">false</bool>\n'
    '\t\t\t<float name="MasterVolume">0</float>\n'
    '\t\t\t<bool name="StartMaximized">false</bool>\n'
    '\t\t\t<Vector2 name="StartScreenSize">\n'
    "\t\t\t\t<X>1262</X>\n"
    "\t\t\t\t<Y>709</Y>\n"
    "\t\t\t</Vector2>\n"
    "\t\t</Properties>\n"
    "\t</Item>\n"
    "</roblox>\n"
)


def _write(path: Path, text: str) -> Path:
    # open() rather than Path.write_text/read_text, whose own newline= arguments landed in different
    # Python versions. These two helpers keep the bytes exactly as written on every version.
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def _read(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def test_the_settings_path_is_per_windows_user(tmp_path: Path) -> None:
    """Which is the whole reason a background session inherits it: it runs as the same user."""
    assert roblox_display.settings_path(tmp_path) == (
        tmp_path / "Roblox" / "GlobalBasicSettings_13.xml"
    )


def test_fullscreen_is_turned_on(tmp_path: Path) -> None:
    settings = _write(tmp_path / "settings.xml", SETTINGS)

    outcome = roblox_display.enable_fullscreen(settings)

    assert outcome.ready and outcome.changed
    assert '<bool name="Fullscreen">true</bool>' in _read(settings)


def test_nothing_but_the_one_setting_changes(tmp_path: Path) -> None:
    """This file holds every preference the user has; only one element may move."""
    settings = _write(tmp_path / "settings.xml", SETTINGS)

    roblox_display.enable_fullscreen(settings)

    written = _read(settings)
    assert written == SETTINGS.replace(
        '<bool name="Fullscreen">false</bool>', '<bool name="Fullscreen">true</bool>'
    )


def test_windows_line_endings_survive_the_edit(tmp_path: Path) -> None:
    """A round trip that rewrote every line would be a far bigger edit than this is allowed to be."""
    crlf = SETTINGS.replace("\n", "\r\n")
    settings = _write(tmp_path / "settings.xml", crlf)

    roblox_display.enable_fullscreen(settings)

    written = _read(settings)
    assert "\r\n" in written
    assert "\n" not in written.replace("\r\n", "")


def test_an_already_fullscreen_client_is_not_rewritten(tmp_path: Path) -> None:
    """Reported as ready, not as a failure: there is genuinely nothing to do."""
    already = SETTINGS.replace(
        '<bool name="Fullscreen">false</bool>', '<bool name="Fullscreen">true</bool>'
    )
    settings = _write(tmp_path / "settings.xml", already)
    before = settings.stat().st_mtime_ns

    outcome = roblox_display.enable_fullscreen(settings)

    assert outcome.ready and not outcome.changed
    assert settings.stat().st_mtime_ns == before


def test_a_missing_settings_file_is_reported_rather_than_created(tmp_path: Path) -> None:
    """Roblox has never run here. Inventing its settings file is not this module's business."""
    missing = tmp_path / "Roblox" / "GlobalBasicSettings_13.xml"

    outcome = roblox_display.enable_fullscreen(missing)

    assert not outcome.ready and not outcome.changed
    assert not missing.exists()


def test_a_file_without_the_setting_is_left_completely_alone(tmp_path: Path) -> None:
    """A client that names it differently is not one this module knows how to edit."""
    other = SETTINGS.replace('name="Fullscreen"', 'name="FullscreenModePreference"')
    settings = _write(tmp_path / "settings.xml", other)

    outcome = roblox_display.enable_fullscreen(settings)

    assert not outcome.ready and not outcome.changed
    assert _read(settings) == other


def test_a_file_with_two_of_the_setting_is_left_completely_alone(tmp_path: Path) -> None:
    """Ambiguity is a reason to stop, not to guess which one Roblox reads."""
    doubled = SETTINGS.replace(
        '<bool name="Fullscreen">false</bool>',
        '<bool name="Fullscreen">false</bool>\n\t\t\t<bool name="Fullscreen">false</bool>',
    )
    settings = _write(tmp_path / "settings.xml", doubled)

    outcome = roblox_display.enable_fullscreen(settings)

    assert not outcome.ready and not outcome.changed
    assert _read(settings) == doubled


def test_an_unreadable_file_is_reported_rather_than_raised(tmp_path: Path, monkeypatch) -> None:
    """This runs on a background session's start-up path, where nothing may throw."""
    settings = _write(tmp_path / "settings.xml", SETTINGS)

    def refuse(*_args, **_kwargs):
        raise OSError("locked")

    monkeypatch.setattr(Path, "open", refuse)

    outcome = roblox_display.enable_fullscreen(settings)

    assert not outcome.ready and not outcome.changed
    assert outcome.message


def test_a_failed_write_leaves_the_original_settings_and_no_litter(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _write(tmp_path / "settings.xml", SETTINGS)

    def refuse(*_args, **_kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(roblox_display.os, "replace", refuse)

    outcome = roblox_display.enable_fullscreen(settings)

    assert not outcome.ready and not outcome.changed
    assert _read(settings) == SETTINGS
    # Nothing left behind at all, whatever the temporary file happened to be called.
    assert [entry.name for entry in tmp_path.iterdir()] == ["settings.xml"]


def test_a_second_call_does_not_share_the_first_ones_temporary_file(
    tmp_path: Path, monkeypatch
) -> None:
    """Overlapping calls must not be able to publish each other's half-written snapshot."""
    settings = _write(tmp_path / "settings.xml", SETTINGS)
    names: list[str] = []
    real_mkstemp = roblox_display.tempfile.mkstemp

    def remember(*args, **kwargs):
        handle, name = real_mkstemp(*args, **kwargs)
        names.append(name)
        return handle, name

    monkeypatch.setattr(roblox_display.tempfile, "mkstemp", remember)

    roblox_display.enable_fullscreen(settings)
    _write(settings, SETTINGS)
    roblox_display.enable_fullscreen(settings)

    assert len(names) == 2 and names[0] != names[1]
    assert [entry.name for entry in tmp_path.iterdir()] == ["settings.xml"]
