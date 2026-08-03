Title:     it still doesnt work and the procedure to replicate the bug still persist, if there is no obvious fix postpone until later revisit, stealing too much focus right now
Completed: 2026-08-03
Commit:    -

Result: Found and fixed the real mechanism, which was never a focus problem at all, so all three
        earlier rounds were chasing the wrong thing. The results popup is a Qt.WindowType.Popup, and
        opening one makes Qt steal the KEYBOARD GRAB (QApplicationPrivate::openPopup -> grabForPopup
        -> stealKeyboardGrab). From that moment every key press is delivered to the POPUP's own
        QWindow regardless of which widget QApplication::focusWidget() points at; it lands on the
        popup QWidget, which ignores it, and QApplication::notify stops walking up the parent chain
        at the first widget that isWindow(), which the popup is. The character is silently dropped.
        That is exactly the user's repro: type "w", results appear with row 0 highlighted, type "w"
        again, nothing happens. The follow-up-2 NoFocus fix was correct and is kept (the search box
        verifiably still holds focus the whole time), it was just irrelevant to this routing path.

        Why three rounds of green tests missed it: qtbot/QTest keyClicks aim their events at a
        WIDGET, which bypasses the window-level routing the grab hijacks, so the old behavioral test
        could never reproduce it. Verified by instrumenting a QApplication-wide event filter: a key
        sent to the MAIN window while the popup is open is redirected to the popup's window and
        delivered to the popup QWidget, never to settings_search_edit.

        Fix (gui/app/main_window.py): install an event filter on _settings_search_popup and forward
        key events back to settings_search_edit, which is precisely what Qt's own QCompleter does for
        this identical arrangement (QCompleter::setPopup installs a filter on the popup;
        QCompleter::eventFilter forwards key presses to the line edit). Escape is consumed to close
        the popup (the popup's own QWidget::keyPressEvent used to do that and no longer runs), and
        Up/Down are consumed to move the highlighted row, so the purple current-row highlight that
        decides what Enter activates is finally reachable by keyboard. Return still reaches
        returnPressed -> _activate_current_search_result via the forward. Rejected the alternative
        root-cause fix (make the results list an in-window child widget instead of a top-level
        popup) because it would lose the popup's automatic close-on-click-outside and its ability to
        extend past the window edge; both options are documented in the code comment.

        Tests: three new tests in gui/tests/test_settings_search.py drive the real delivery path via
        QTest.keyClick against the popup's windowHandle(); two of them fail without the fix
        (confirmed by temporary revert) and all pass with it. The old widget-targeted test is kept
        but now carries an explicit KNOWN BLIND SPOT note so a future round does not trust it as
        proof that typing works. Full gui/ suite: 266 passed. Reviewed read-only by gpt-5.6-terra,
        no issues found.
