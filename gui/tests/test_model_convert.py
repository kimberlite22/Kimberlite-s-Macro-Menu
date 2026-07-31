from __future__ import annotations

from pathlib import Path

from app.main_window import preset_config_to_screens_payload
from ipc.config_reader import read_config
from ipc.protocol import ScreenPayload, StepPayload


FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.ini"


def test_preset_screens_are_converted_without_losing_step_fields() -> None:
    preset = read_config(FIXTURE).presets[0]

    actual = preset_config_to_screens_payload(preset)
    expected = [
        ScreenPayload(
            name="Lobby",
            steps=(
                StepPayload(
                    type="Button Click", label="Start | now", x=12.5, y=22.5,
                    end_x=0, end_y=0, drag_ms=0, once_per_cycle=True,
                    seconds=1.5, on_true_screen="Battle", on_false_screen="Retry",
                    fallback_enabled=True, fallback_max_attempts=4,
                    fallback_screen="Fallback", advanced=True,
                    outcomes_raw="Victory>Win|Defeat>Lose",
                ),
                StepPayload(type="Wait", label="Wait for match", seconds=8),
                StepPayload(type="Drag", label="Pan camera", x=1, y=2, end_x=30, end_y=40, drag_ms=350),
            ),
        ).to_dict(),
        ScreenPayload(
            name="Battle",
            # Resolved against the fixture's global registry entry (linked via
            # Screen2UseGlobalDetection=1), not the preset's own stale local values - see
            # test_config_reader.test_reader_resolves_a_globally_linked_screen_against_the_registry.
            detection_type="Ingame Detection", detection_x=1.5, detection_y=2.5,
            detection_end_x=3.5, detection_end_y=4.5, detection_text="Victory",
            default_screen="Lobby", use_global_detection=True,
            steps=(StepPayload(type="Restart Stage Button", label="Use ability", x=7, y=8),),
        ).to_dict(),
    ]

    assert actual == expected
