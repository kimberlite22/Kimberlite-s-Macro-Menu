from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app import background_session
from app.background_session_tab import BackgroundSessionTab
from app.rdp_wrapper import CheckResult, SetupStatus


def _ready() -> SetupStatus:
    return SetupStatus(
        tuple(
            CheckResult(name, True, f"{name} is fine.", "")
            for name in (
                "Remote Desktop",
                "Multiple sessions per user",
                "RDP Wrapper installed",
                "RDP Wrapper supports this Windows build",
            )
        )
    )


def _not_ready() -> SetupStatus:
    return SetupStatus(
        (
            CheckResult("Remote Desktop", True, "Remote Desktop is enabled.", ""),
            CheckResult(
                "Multiple sessions per user",
                False,
                "Windows hands the same account its existing session.",
                "Set fSingleSessionPerUser to 0.",
            ),
            CheckResult(
                "RDP Wrapper installed",
                False,
                "Remote Desktop is not configured to load rdpwrap.dll.",
                "Install RDP Wrapper with administrator rights, then reboot.",
            ),
            CheckResult(
                "RDP Wrapper supports this Windows build",
                False,
                "RDP Wrapper is not installed or active.",
                "Install and activate RDP Wrapper first.",
            ),
        )
    )


def _tab(qtbot, tmp_path: Path, status: SetupStatus) -> BackgroundSessionTab:
    tab = BackgroundSessionTab(tmp_path, check_setup=lambda: status)
    qtbot.addWidget(tab)
    tab.show()
    return tab


def test_a_ready_machine_enables_start_and_says_so(qtbot, tmp_path: Path) -> None:
    tab = _tab(qtbot, tmp_path, _ready())

    assert tab.start_button.isEnabled() is True
    assert "ready" in tab.setup_summary_label.text().casefold()
    assert "Needs attention" not in tab.setup_details_label.text()


def test_an_unready_machine_disables_start_and_lists_every_instruction(qtbot, tmp_path: Path) -> None:
    tab = _tab(qtbot, tmp_path, _not_ready())

    assert tab.start_button.isEnabled() is False
    details = tab.setup_details_label.text()
    assert "Set fSingleSessionPerUser to 0." in details
    assert "Install RDP Wrapper with administrator rights, then reboot." in details
    # The one passing check is still shown, so the user sees the whole picture, not only failures.
    assert "OK: Remote Desktop" in details


def test_start_is_never_reached_while_the_setup_gate_is_closed(qtbot, tmp_path: Path, monkeypatch) -> None:
    start = MagicMock()
    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = _tab(qtbot, tmp_path, _not_ready())

    tab.start_button.click()

    start.assert_not_called()


def test_re_checking_after_the_machine_was_fixed_opens_the_gate(qtbot, tmp_path: Path) -> None:
    statuses = [_not_ready(), _ready()]
    tab = BackgroundSessionTab(tmp_path, check_setup=lambda: statuses.pop(0))
    qtbot.addWidget(tab)
    tab.show()
    assert tab.start_button.isEnabled() is False

    tab.recheck_button.click()

    assert tab.start_button.isEnabled() is True


def test_calling_start_directly_still_refuses_on_an_unready_machine(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """The disabled button only hides the action; _start itself has to enforce the verdict."""
    start = MagicMock(return_value=background_session.BackgroundSessionResult(False, "nope"))
    monkeypatch.setattr(background_session, "start_background_session", start)
    tab = _tab(qtbot, tmp_path, _ready())
    tab._setup_ok = False

    tab._start()

    start.assert_not_called()
    assert "Re-check" in tab.result_text.toPlainText()


def test_a_failed_start_does_not_reopen_the_gate_on_an_unready_machine(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """_start's finally block re-enables the buttons; Start must still respect the setup verdict."""
    monkeypatch.setattr(
        background_session,
        "start_background_session",
        MagicMock(return_value=background_session.BackgroundSessionResult(False, "nope")),
    )
    tab = _tab(qtbot, tmp_path, _ready())

    tab._start()
    tab._setup_ok = False
    tab._set_buttons_enabled(True)

    assert tab.start_button.isEnabled() is False
    assert tab.show_button.isEnabled() is True


def test_the_tab_states_the_third_party_and_licensing_caveats_up_front(qtbot, tmp_path: Path) -> None:
    tab = _tab(qtbot, tmp_path, _ready())
    described = " ".join(
        label.text() for label in tab.findChildren(type(tab.setup_summary_label))
    ).casefold()

    assert "not bundled" in described
    assert "administrator" in described
    assert "licensing" in described
