Title: Its still there, what i excatly do to replicate the bug: I click the searchbar -> i type w
       -> it wont let me type more because the focus is now on the first result.
Prio:  1

Goal:  Follow-up from settings-search-follow-up-2: the settings search box reportedly still stops
       accepting keystrokes after the first character typed, focus apparently jumping to the first
       result in the popup.
Files: gui/app/main_window.py (settings search popup/list construction ~lines 238-273 including the
       Qt.FocusPolicy.NoFocus calls at 263/269, _update_settings_search ~354-369).
Steps: 1. Check release ancestry first, the same way general-parentheses-tooltips-follow-up did:
          the settings-search-follow-up-2 fix (commit c391e90, denies focus to the popup and its
          list) is NOT yet an ancestor of the latest version tag as of this writing
          (`git merge-base --is-ancestor c391e90 <latest-tag>` returned false against v0.4.16) -
          re-run that check against whatever the latest tag is when this task starts, since a
          release may have shipped since. If it still hasn't shipped, ask the user directly whether
          they tested the installed release or a source checkout of main before assuming the bug is
          real on current code.
       2. If a release containing c391e90 has shipped and the user was running that build,
          reproduce for real: focus settings_search_edit, type a 2+ character query, and check
          programmatically (e.g. a headless PySide6 probe like the one used for
          general-parentheses-tooltips-follow-up) which widget QApplication.focusWidget() reports
          after each keystroke.
       3. If focus still moves despite Qt.FocusPolicy.NoFocus on both the popup and the list, treat
          it as Qt's Popup window type grabbing OS-level keyboard focus on show() regardless of
          WA_ShowWithoutActivating, not a specific child widget stealing it; check whether the
          existing `self.settings_search_edit.setFocus()` call at the end of
          _update_settings_search (line 369) is racing something that re-focuses later in the same
          event loop turn, and whether re-asserting it via QTimer.singleShot(0, ...) after the
          popup's show() fully processes fixes it.
Open:  -
