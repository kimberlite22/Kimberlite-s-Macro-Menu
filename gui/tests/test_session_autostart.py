from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app import session_autostart


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="the registry is Windows-only")


# ---------------------------------------------------------------------------------------------
# The Run command line
# ---------------------------------------------------------------------------------------------


def test_the_command_quotes_the_path_and_carries_the_flag(tmp_path: Path) -> None:
    """A Run value is a command line, so the installed path has to survive being parsed as one.

    The real installed directory contains both spaces and an apostrophe ("Kimberlite's Macro
    Menu"), which unquoted would be split into an executable plus stray arguments.
    """
    directory = tmp_path / "Programs" / "Kimberlite's Macro Menu"

    command = session_autostart.autostart_command(directory)

    assert command.startswith('"')
    assert command.endswith(f" {session_autostart.SESSION_AUTOSTART_FLAG}")
    assert str(directory / "gui.exe") in command


def test_the_command_carries_arguments_unlike_the_alternate_shell(tmp_path: Path) -> None:
    """The whole reason this route needs no separate launcher executable."""
    command = session_autostart.autostart_command(tmp_path)

    assert session_autostart.SESSION_AUTOSTART_FLAG in command


def test_it_is_unavailable_without_an_installed_executable(tmp_path: Path) -> None:
    assert session_autostart.autostart_available(tmp_path) is False


def test_it_is_available_once_the_executable_exists(tmp_path: Path) -> None:
    (tmp_path / "gui.exe").write_text("", encoding="utf-8")

    assert session_autostart.autostart_available(tmp_path) is True


# ---------------------------------------------------------------------------------------------
# The registry entry, round-tripped against a test-only key
# ---------------------------------------------------------------------------------------------


@pytest.fixture()
def isolated_run_key(monkeypatch):
    """Point the module at a throwaway HKCU key so a test never edits the real Run key."""
    key_path = r"Software\Kimberlite Macro Menu\SessionAutostartTest"
    monkeypatch.setattr(session_autostart, "RUN_KEY_PATH", key_path)
    yield key_path
    if sys.platform != "win32":
        return
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    except OSError:
        pass


@windows_only
def test_the_entry_round_trips(isolated_run_key, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_autostart, "installed_gui_path", lambda _=None: tmp_path / "gui.exe")

    assert session_autostart.install_autostart_entry() is True
    assert session_autostart.read_autostart_entry() == session_autostart.autostart_command()
    assert session_autostart.remove_autostart_entry() is True
    assert session_autostart.read_autostart_entry() is None


@windows_only
def test_removing_an_absent_entry_counts_as_removed(isolated_run_key) -> None:
    """Callers use this as cleanup, where "it was not there" is the outcome they wanted."""
    assert session_autostart.remove_autostart_entry() is True


@windows_only
def test_installing_twice_replaces_rather_than_duplicates(
    isolated_run_key, tmp_path: Path, monkeypatch
) -> None:
    """The installed path can move between releases, so the current one always wins."""
    monkeypatch.setattr(session_autostart, "installed_gui_path", lambda _=None: tmp_path / "old.exe")
    session_autostart.install_autostart_entry()
    monkeypatch.setattr(session_autostart, "installed_gui_path", lambda _=None: tmp_path / "new.exe")

    session_autostart.install_autostart_entry()

    entry = session_autostart.read_autostart_entry()
    assert entry is not None
    assert "new.exe" in entry
    assert "old.exe" not in entry


# ---------------------------------------------------------------------------------------------
# The one-shot arm marker
# ---------------------------------------------------------------------------------------------


def test_a_fresh_marker_is_consumed_once(tmp_path: Path) -> None:
    assert session_autostart.arm(tmp_path, now=1000.0) is True

    assert session_autostart.consume_arm(tmp_path, now=1001.0) is True
    # Consume-on-read: a second logon must not be able to reuse the same authorisation.
    assert session_autostart.consume_arm(tmp_path, now=1002.0) is False


def test_a_missing_marker_is_not_an_authorisation(tmp_path: Path) -> None:
    assert session_autostart.consume_arm(tmp_path) is False


def test_a_stale_marker_is_refused_and_still_deleted(tmp_path: Path) -> None:
    """An expired marker left on disk could arm an unrelated RDP logon later in the day."""
    session_autostart.arm(tmp_path, now=1000.0)

    assert (
        session_autostart.consume_arm(
            tmp_path, now=1000.0 + session_autostart.ARM_WINDOW_SECONDS + 1
        )
        is False
    )
    assert not (tmp_path / session_autostart.ARM_FILE_NAME).exists()


def test_a_marker_from_the_future_is_refused(tmp_path: Path) -> None:
    """A clock that moved between the two sessions must not widen the window indefinitely."""
    session_autostart.arm(tmp_path, now=10_000.0)

    assert session_autostart.consume_arm(tmp_path, now=1000.0) is False


def test_a_corrupt_marker_is_refused_and_still_deleted(tmp_path: Path) -> None:
    (tmp_path / session_autostart.ARM_FILE_NAME).write_text("not json", encoding="utf-8")

    assert session_autostart.consume_arm(tmp_path) is False
    assert not (tmp_path / session_autostart.ARM_FILE_NAME).exists()


def test_arming_writes_a_readable_timestamp(tmp_path: Path) -> None:
    session_autostart.arm(tmp_path, now=1234.5)

    payload = json.loads((tmp_path / session_autostart.ARM_FILE_NAME).read_text(encoding="utf-8"))
    assert payload["armed_at"] == 1234.5


def test_disarming_removes_the_marker_without_consuming_it(tmp_path: Path) -> None:
    session_autostart.arm(tmp_path)

    session_autostart.disarm(tmp_path)

    assert not (tmp_path / session_autostart.ARM_FILE_NAME).exists()


def test_disarming_nothing_is_harmless(tmp_path: Path) -> None:
    session_autostart.disarm(tmp_path)


# ---------------------------------------------------------------------------------------------
# Self-gating
# ---------------------------------------------------------------------------------------------


def test_the_console_session_is_never_a_background_session(monkeypatch) -> None:
    """Both sessions share one profile, so this same entry fires on the physical desktop."""
    monkeypatch.setattr(session_autostart, "is_remote_session", lambda: False)

    assert session_autostart.in_background_session() is False


def test_an_unreadable_remote_flag_refuses(monkeypatch) -> None:
    """Fails closed: booting the user's real desktop into a macro shell is the failure to avoid."""
    monkeypatch.setattr(session_autostart, "is_remote_session", lambda: None)

    assert session_autostart.in_background_session() is False


def test_a_remote_session_is_a_background_session(monkeypatch) -> None:
    monkeypatch.setattr(session_autostart, "is_remote_session", lambda: True)
    monkeypatch.setattr(session_autostart, "console_session_id", lambda: 1)
    monkeypatch.setattr(session_autostart, "current_session_id", lambda: 14)

    assert session_autostart.in_background_session() is True


def test_a_remote_session_that_is_the_console_is_refused(monkeypatch) -> None:
    """A contradiction between the two signals is resolved by refusing, not by guessing."""
    monkeypatch.setattr(session_autostart, "is_remote_session", lambda: True)
    monkeypatch.setattr(session_autostart, "console_session_id", lambda: 3)
    monkeypatch.setattr(session_autostart, "current_session_id", lambda: 3)

    assert session_autostart.in_background_session() is False


def test_an_unreadable_console_id_does_not_veto(monkeypatch) -> None:
    """The console comparison may only veto the primary signal, never be required to supply it."""
    monkeypatch.setattr(session_autostart, "is_remote_session", lambda: True)
    monkeypatch.setattr(session_autostart, "console_session_id", lambda: None)
    monkeypatch.setattr(session_autostart, "current_session_id", lambda: None)

    assert session_autostart.in_background_session() is True


# ---------------------------------------------------------------------------------------------
# The claim, which is what main() calls
# ---------------------------------------------------------------------------------------------


def test_the_console_launch_does_not_eat_the_marker(monkeypatch, tmp_path: Path) -> None:
    """The single most important ordering in this module.

    The console logon fires the same Run entry off the same shared profile. If it consumed the
    marker, the background session logging on moments later would find nothing and come up idle.
    """
    monkeypatch.setattr(session_autostart, "in_background_session", lambda: False)
    session_autostart.arm(tmp_path)

    assert session_autostart.claim_session_autostart(tmp_path) is False
    assert (tmp_path / session_autostart.ARM_FILE_NAME).exists()


def test_the_console_launch_leaves_the_entry_in_place(monkeypatch, tmp_path: Path) -> None:
    """The background session still has to find it."""
    monkeypatch.setattr(session_autostart, "in_background_session", lambda: False)
    removed = []
    monkeypatch.setattr(
        session_autostart, "remove_autostart_entry", lambda: removed.append(True) or True
    )

    session_autostart.claim_session_autostart(tmp_path)

    assert removed == []


def test_an_unarmed_background_session_is_refused(monkeypatch, tmp_path: Path) -> None:
    """An RDP logon the user made for their own reasons is not a request to run the macro."""
    monkeypatch.setattr(session_autostart, "in_background_session", lambda: True)

    assert session_autostart.claim_session_autostart(tmp_path) is False


def test_an_armed_background_session_claims_and_retires_the_entry(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(session_autostart, "in_background_session", lambda: True)
    removed = []
    monkeypatch.setattr(
        session_autostart, "remove_autostart_entry", lambda: removed.append(True) or True
    )
    session_autostart.arm(tmp_path)

    assert session_autostart.claim_session_autostart(tmp_path) is True
    assert removed == [True]
    assert not (tmp_path / session_autostart.ARM_FILE_NAME).exists()


# ---------------------------------------------------------------------------------------------
# main()'s use of the claim, which is what actually protects the physical desktop
# ---------------------------------------------------------------------------------------------


def test_main_exits_before_building_a_qapplication_on_the_console(monkeypatch, tmp_path) -> None:
    """The gate has to close before any Qt object exists, or the desktop gets a window flash.

    Both sessions share one Windows profile, so the console logon runs this exact command line too.
    A QApplication constructed before the refusal would be a visible flicker on the desktop the
    user is actually looking at.
    """
    from app import main as main_module

    monkeypatch.setattr(main_module, "claim_session_autostart", lambda _: False)

    def explode(*_args, **_kwargs):
        raise AssertionError("a QApplication must not be constructed on the console")

    monkeypatch.setattr(main_module, "QApplication", explode)

    assert main_module.main(["--session-autostart", "--dir", str(tmp_path)]) == 0


def _capture_owns_session(monkeypatch, qapp) -> dict:
    """Run main() far enough to see which mode it hands the session shell.

    QApplication is a process-wide singleton, so main()'s own construction of one is redirected at
    the instance the test session already has; everything this asserts happens after that point.
    """
    from app import main as main_module

    captured: dict[str, object] = {}

    def run(data_dir, launch_target="", *, owns_session=True):
        captured["owns_session"] = owns_session
        return 0

    monkeypatch.setattr(main_module, "QApplication", lambda *_a, **_k: qapp)
    monkeypatch.setattr(main_module, "run_session_shell", run)
    monkeypatch.setattr(main_module, "read_launch_target", lambda _: "")
    return captured


def test_main_runs_the_shell_when_the_claim_succeeds(monkeypatch, tmp_path, qapp) -> None:
    from app import main as main_module

    monkeypatch.setattr(main_module, "claim_session_autostart", lambda _: True)
    captured = _capture_owns_session(monkeypatch, qapp)

    assert main_module.main(["--session-autostart", "--dir", str(tmp_path)]) == 0
    # Explorer starts on this route, so the control window must not behave like the session's shell.
    assert captured["owns_session"] is False


def test_the_alternate_shell_mode_still_owns_its_session(monkeypatch, tmp_path, qapp) -> None:
    from app import main as main_module

    captured = _capture_owns_session(monkeypatch, qapp)

    main_module.main(["--session-shell", "--dir", str(tmp_path)])

    assert captured["owns_session"] is True


# ---------------------------------------------------------------------------------------------
# Taking the marker is atomic, so two logons cannot both be authorised by one arm
# ---------------------------------------------------------------------------------------------


def test_only_one_of_two_racing_claimants_is_authorised(monkeypatch, tmp_path: Path) -> None:
    """A read-then-delete would let both read the same valid payload before either removed it.

    The race is simulated at the only point where it matters: the second claimant runs entirely
    inside the first one's read, which is exactly the interleaving a plain read-then-delete loses.
    """
    session_autostart.arm(tmp_path, now=1000.0)
    inner: list[bool] = []
    real_read_text = Path.read_text

    def read_text_then_let_the_other_try(self, *args, **kwargs):
        if not inner:
            # Re-entrant on purpose: a second process reaching consume_arm while this one is between
            # its own take and its own read.
            inner.append(session_autostart.consume_arm(tmp_path, now=1000.0))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text_then_let_the_other_try)

    first = session_autostart.consume_arm(tmp_path, now=1000.0)

    assert [first, *inner].count(True) == 1


def test_a_marker_that_cannot_be_taken_authorises_nothing(monkeypatch, tmp_path: Path) -> None:
    """Authorising a launch whose marker could not be removed would authorise every later one too."""
    session_autostart.arm(tmp_path, now=1000.0)

    def refuse(*_args, **_kwargs):
        raise OSError("in use")

    monkeypatch.setattr(session_autostart.os, "replace", refuse)

    assert session_autostart.consume_arm(tmp_path, now=1000.0) is False


def test_taking_the_marker_leaves_no_claim_file_behind(tmp_path: Path) -> None:
    session_autostart.arm(tmp_path, now=1000.0)

    session_autostart.consume_arm(tmp_path, now=1000.0)

    assert list(tmp_path.glob("*")) == []


def test_a_claim_file_left_by_a_failed_delete_is_swept_by_the_next_arm(
    monkeypatch, tmp_path: Path
) -> None:
    """consume_arm's delete is best-effort, so the debt has to be settled somewhere."""
    session_autostart.arm(tmp_path, now=1000.0)
    real_unlink = Path.unlink

    def refuse_to_unlink_claims(self, *args, **kwargs):
        if ".claim-" in self.name:
            raise OSError("in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse_to_unlink_claims)
    assert session_autostart.consume_arm(tmp_path, now=1000.0) is True
    leftovers = list(tmp_path.glob(f"{session_autostart.ARM_FILE_NAME}.claim-*"))
    assert leftovers != []

    monkeypatch.undo()
    session_autostart.arm(tmp_path, now=2000.0)

    assert list(tmp_path.glob(f"{session_autostart.ARM_FILE_NAME}.claim-*")) == []


def test_a_leftover_claim_file_is_never_an_authorisation(tmp_path: Path) -> None:
    """Only the marker's own name is ever looked for, so litter cannot let a logon through."""
    (tmp_path / f"{session_autostart.ARM_FILE_NAME}.claim-1234").write_text(
        '{"armed_at": 1000.0}', encoding="utf-8"
    )

    assert session_autostart.consume_arm(tmp_path, now=1000.0) is False
