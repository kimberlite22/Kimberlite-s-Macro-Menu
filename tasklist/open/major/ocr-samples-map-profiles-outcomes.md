Title: Sample images for the expected texts that do NOT live in a step's Name field (map profiles
       and advanced detection outcomes)
Prio:  10

Goal:  "Save Sample" / "Choose Sample..." reach every expected text, not just the ones a Logic
       step's Name field holds. A map profile's ExpectedText and an Advanced Detection outcome's
       Name get the same two buttons next to their own fields, so a sample can be filed under the
       text the matcher actually compares against.
Open:  Where exactly do the buttons go: the map profile editor (gui/app/map_advanced_window.py) has
       no Test OCR button today, and the outcomes editor
       (gui/app/advanced_outcomes_window.py) edits N rows at once, so one pair of buttons per row
       may crowd it. Does the outcomes window get per-row buttons or one pair acting on the
       selected row? The engine side needs nothing new: SAVE_OCR_SAMPLE / SET_OCR_SAMPLE /
       GET_OCR_SAMPLE already key off whatever expected text they are handed, and the region for a
       map profile sample is the Detect Map step's region, which that window does not currently
       know, so it has to be passed in or looked up.
       Background: the buttons are deliberately hidden on "Detect Map" and Advanced Detection steps
       today (gui/app/step_edit_window.py, step_label_is_expected_text) precisely because a sample
       saved there would be filed under the step's name, which no matcher ever looks up.
