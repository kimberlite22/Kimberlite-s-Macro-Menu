Title: Die screen detection settings sollen nicht immer visible sein, sie sollen unter screen
       settings sein
Prio:  3

Goal:  The "Screen Detection" group box in the preset/screen editor
       (gui/app/edit_preset_window.py, currently always shown, ~lines 115-138) is no longer always
       visible; it moves under/inside a "Screen Settings" section that is only shown when the user
       wants to see or edit detection, decluttering the default step-editing view. Resolved shape:
       a "Screen Settings..." button opening a dedicated dialog window; default view shows just the
       step list.
Open:  BLOCKED: the "Screen Detection" group box this task targets no longer exists in the code.
       It was part of the screen-detection-overhaul feature, fully reverted in commit af75b23
       before this task file was even created from INBOX.md; ScreenConfig
       (gui/ipc/config_reader.py) currently has only name/steps, no detection data. This task
       cannot be implemented until [[screen-detection-overhaul]] (tasklist/open/major, Prio 2,
       itself still undecided) is re-decided and re-implemented, since there is nothing to
       relocate yet. Needs a user call: postpone until that major task lands, or close this as
       obsolete if the feature will not be revisited soon.
