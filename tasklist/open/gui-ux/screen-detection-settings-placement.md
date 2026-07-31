Title: Die screen detection settings sollen nicht immer visible sein, sie sollen unter screen
       settings sein
Prio:  7

Goal:  The "Screen Detection" group box in the preset/screen editor
       (gui/app/edit_preset_window.py, currently always shown, ~lines 115-138) is no longer always
       visible; it moves under/inside a "Screen Settings" section that is only shown when the user
       wants to see or edit detection, decluttering the default step-editing view.
Open:  What should the always-visible default view show instead (just the step list)? Should
       "Screen Settings" be a collapsible section, a separate sub-tab, or a button opening a
       dedicated dialog?
