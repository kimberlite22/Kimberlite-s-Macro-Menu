from app.advanced_outcomes_window import DetectionOutcome, parse_outcomes, serialize_outcomes


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
