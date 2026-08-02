Title:     In preset settings, remove das widget Challenge option basics
           Remove bei presets die challenge option basics
Completed: 2026-08-02
Commit:    -

Result: Removed the "Challenge option basics" QGroupBox (Option 1-3 Name/X/Y/Available/Priority)
from the Presets tab in gui/app/main_window.py; the Step Editor's "Challenge options" widget (added
in challenge-options-to-step-editor, PR #73) is now the sole editor for that data, and
_preset_payload() now reads name/x/y/available/priority straight from preset.options (like it
already did for det_x/det_y) instead of from the removed widgets. "Today's Challenge Usage" is
unaffected, unchanged, and confirmed still reading the same preset.options data.
