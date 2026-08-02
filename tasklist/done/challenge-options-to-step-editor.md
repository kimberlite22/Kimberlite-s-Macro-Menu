Title:     in Edit preset -> challenge options. Move the challenge options widget into the edit step window of option select because thats basically the entire step
Completed: 2026-08-02
Commit:    -

Result: The "Challenge options" group box (Option 1-3: Name/X/Y/Available at start/Priority/Max
uses/Availability Check) moved out of Edit Preset's always-visible layout into the Step Editor
window, shown only when editing an "Option Select" step. Data model stayed shared per-preset
(self.preset.options): StepEditWindow.open_for() now also takes the preset's options list, writes
edits back into those same OptionConfig objects on Save, and the search-preview path hands it a
throwaway deepcopy so a Save there cannot corrupt the real preset. The "Availability Check..."
button and its OptionAvailabilityWindow moved together with the widget into StepEditWindow.
