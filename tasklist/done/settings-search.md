Title:     Füge oben rechts eine search funktion hinzu wo man nach einem setting searchen kann. wenn ich
           für die lupe ein asset hinzufügen muss dan sag mir.
Completed: 2026-08-01
Commit:    -

Result: A "Search:" box (plain text label, no icon asset needed) sits top-right in the "Engine
status" row of the main window. Typing shows a results popup (case-insensitive substring match,
prefix matches ranked first) covering the three main tabs, the Remote Agent tab, the bottom
Save/Pin/Start/Pause/Resume/Stop action row, and the Edit Preset, Map Advanced, Option
Availability, Step Editor and Advanced Outcomes secondary windows. Selecting a result switches to
the right tab or opens/reuses the right secondary window (surfacing "Select a preset/profile
first" when needed, same as the existing Edit button), then focuses and briefly highlights the
matching field. Navigating into the Step Editor/Advanced Outcomes from search deliberately uses a
new read-only preview path (EditPresetWindow._open_step_editor_for_search) instead of the "Add
Step" path, so merely looking a setting up can never queue a phantom new step.
