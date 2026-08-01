from PySide6.QtCore import Qt

from app.advanced_outcomes_window import (
    AdvancedOutcomesWindow,
    DetectionOutcome,
    parse_outcomes,
    serialize_outcomes,
)


def test_outcomes_parse_and_serialize_match_ahk_flat_format() -> None:
    raw = "Victory=Win|Defeat=Lose|Retry=(Repeat)"
    parsed = parse_outcomes(raw)

    assert parsed == [
        DetectionOutcome("Victory", "Win"),
        DetectionOutcome("Defeat", "Lose"),
        DetectionOutcome("Retry", "(Repeat)"),
    ]
    assert serialize_outcomes(parsed) == raw


def test_outcomes_fresh_values_round_trip() -> None:
    outcomes = [
        DetectionOutcome("Ready", "Battle"),
        DetectionOutcome("No attempts", "(Stop Macro)"),
    ]

    assert parse_outcomes(serialize_outcomes(outcomes)) == outcomes


def test_window_has_independent_minimize_button(qtbot) -> None:
    # Regression guard, see make_independently_minimizable: AdvancedOutcomesWindow would
    # otherwise have no minimize button of its own, and its caller (StepEditWindow)
    # deliberately constructs it with no Qt parent since a parented QDialog would be a native
    # Windows "owned window" that auto-hides whenever its owner is minimized. Shown via .exec()
    # elsewhere, but the flag and the no-parent construction apply equally either way.
    window = AdvancedOutcomesWindow("True=(continue)|False=(continue)", ["Lobby"])
    qtbot.addWidget(window)
    assert window.windowFlags() & Qt.WindowMinimizeButtonHint
