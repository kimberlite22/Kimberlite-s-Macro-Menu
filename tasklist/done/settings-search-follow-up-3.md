Title:     Its still there, what i excatly do to replicate the bug: I click the searchbar -> i type w
           -> it wont let me type more because the focus is now on the first result.
Completed: 2026-08-02
Commit:    -

Result: Investigated whether the settings-search-follow-up-2 fix (commit c391e90, denies
        Qt.FocusPolicy.NoFocus to the results popup and its QListWidget) actually stopped the popup
        from stealing keyboard focus. Root cause is release staleness, the same pattern as
        general-parentheses-tooltips-follow-up: c391e90 was committed 2026-08-02 06:14, several hours
        AFTER the latest shipped tag v0.4.16 (cut 2026-08-01 03:38), so no release has ever contained
        this fix (`git merge-base --is-ancestor c391e90 v0.4.16` is false, and it is trivially true
        that a commit cannot be an ancestor of a tag cut before it existed). The user's installed
        build necessarily predates the NoFocus fix entirely, so of course typing a second character
        still moves focus to the first result there; that is the pre-fix behavior, not evidence the
        fix itself failed.

        Verified the fix is sound on current main with the existing headless PySide6/pytest-qt suite
        (QT_QPA_PLATFORM=offscreen, gui/tests/conftest.py's own convention): all 8 tests in
        gui/tests/test_settings_search.py pass, including
        test_settings_search_popup_and_its_list_never_accept_keyboard_focus (structural: both the
        popup and its list report Qt.FocusPolicy.NoFocus) and
        test_typing_a_second_character_while_the_popup_is_showing_keeps_focus_on_the_search_box
        (behavioral: real key events for "s" then "a" while the popup is visible and repopulates
        between them, asserting settings_search_edit keeps focus throughout and ends up with text
        "sa"). c391e90's own commit message notes the structural test was confirmed to fail without
        the fix via a temporary revert. Full `python -m pytest` in gui/ passes (247 passed). No
        gui/app/*.py file was changed; this is a re-confirmation, not a new fix.
