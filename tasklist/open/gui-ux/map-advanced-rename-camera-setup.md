Title: Rename the button map advanced settings in map placement to camera setup settings.
Prio:  2

Goal:  The Map Placement tab's "Map Advanced Settings..." button reads "Camera Setup Settings...",
       and the window it opens is titled to match, so the name says what the window is for instead
       of what tier of settings it holds. The button is gui/app/main_window.py:661
       (self.map_advanced_button, built by self._button("Map Advanced Settings...",
       self._open_map_advanced)); the window title is gui/app/map_advanced_window.py:89
       (f"Map Advanced Settings: {target_label}").

       This is a label change, not a rename of the code behind it: map_advanced_window.py,
       _open_map_advanced, the map_advanced_button attribute and the MapAdvanced config keys stay as
       they are, so the change cannot reach config.ini or the engine. gui/app/settings_search.py and
       gui/ipc/config_reader.py both mention the old name and need checking, since the settings
       search index is what makes a user typing "camera" find this button at all. Tests that pin the
       old strings live in gui/tests/test_main_window.py and gui/tests/test_map_advanced_window.py.

Open:  - Whether the window title should read "Camera Setup Settings: <target>" or drop the doubled
         "Settings" ("Camera Setup: <target>"). The button keeps the user's own wording either way;
         only the title is in question.
