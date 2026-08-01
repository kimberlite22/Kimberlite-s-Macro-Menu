Title: in Edit preset -> challenge options. Move the challenge options widget into the edit step window of option select because thats basically the entire step
Prio:  5

Goal:  The "Challenge options" group box (Option 1-3: Name/X/Y/Available at start/Priority/Max
       uses/Availability Check, gui/app/edit_preset_window.py:134-165) moves out of Edit Preset's
       always-visible layout and into the Step Editor window (gui/app/step_edit_window.py), shown
       only when editing a step of type "Option Select", since that step type's behavior is
       essentially defined entirely by this options data.
Open:  The three challenge options are stored once per preset (self.preset.options in
       edit_preset_window.py), not per-step, while "Option Select" steps live inside individual
       screens. If a preset has more than one "Option Select" step (across different screens), do
       they all share this single set of options, or does the data model need to become per-step?
       StepEditWindow currently only receives/edits a single StepConfig - it needs a way to
       receive and write back the preset's shared options list when open for this step type.
       Does the "Availability Check..." button's target (OptionAvailabilityWindow,
       gui/app/option_availability_window.py) move along with the widget, or stay owned by
       EditPresetWindow?
