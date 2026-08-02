Title:     it stil steals the focus when the current options are presented, if i type for example 1 key
           the results will show which makes me not able to type without clicking the window again
Completed: 2026-08-02
Commit:    -

Result: _settings_search_popup and its _settings_search_list now both set
Qt.FocusPolicy.NoFocus, so Qt's own popup-open focus machinery has nothing focusable inside the
popup to steal keyboard focus into on any keystroke (not just the first one the earlier one-shot
setFocus() reclaim covered); confirmed the new structural regression test fails without the fix
and passes with it.
