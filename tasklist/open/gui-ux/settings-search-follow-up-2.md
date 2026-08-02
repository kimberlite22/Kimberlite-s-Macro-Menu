Title: it stil steals the focus when the current options are presented, if i type for example 1 key
       the results will show which makes me not able to type without clicking the window again
Prio:  1

Goal:  Follow-up from settings-search-follow-up: typing into the settings search box
       (gui/app/main_window.py, settings_search_edit / _update_settings_search /
       _settings_search_popup) still loses keyboard focus as soon as the results popup appears after
       the first keystroke, so the user cannot keep typing without re-clicking the search box. The
       prior fix reclaims focus once right after showing the popup
       (test_update_settings_search_reclaims_focus_after_showing_popup passes), but per this report
       the box still loses focus in real use.
Open:  Reproduce exactly when the reported focus loss happens; the existing regression test passes
       against the qtbot environment, so real Windows focus behavior around a
       Qt.WindowType.Popup + WA_ShowWithoutActivating widget evidently differs from what the test
       models. May need a different mechanism than reclaiming focus after the fact, e.g. preventing
       the popup from ever taking focus in the first place, or diagnosing a timing gap between
       popup.show() and the focus reclaim on the real event loop.
