Title: working but bad: After one letter typed it immidiately switches to results, and remove that the setting searched for is highlighed after clicking it
Prio:  2

Goal:  Follow-up from settings-search: the results popup should not appear after just one typed
       character (main_window.py:252 wires `_update_settings_search` straight to
       `settings_search_edit.textChanged` with no minimum-length gate), and the destination widget
       should no longer get the temporary highlight color after a search result is clicked
       (`_focus_and_highlight`, main_window.py:408-420, applies `background-color: #f0c674` for
       1200ms) - it should still get keyboard focus and the tab/window switch, just without the
       highlight flash.
Open:  How many characters should be required before showing results (e.g. 2 or 3), or should it
       debounce by time instead of character count? `_focus_and_highlight` is shared by other call
       sites too (not just settings search) - confirm removing the highlight applies only to the
       settings-search navigation path, not to every caller of `_focus_and_highlight`.
