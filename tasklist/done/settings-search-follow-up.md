Title:     working but bad: After one letter typed it immidiately switches to results, and remove that the setting searched for is highlighed after clicking it
Completed: 2026-08-01
Commit:    -

Result: The settings-search results popup (Qt.WindowType.Popup) implicitly grabbed keyboard focus
every time it was shown, which happened on every keystroke; fixed by reclaiming focus on
settings_search_edit right after popup.show() in _update_settings_search, plus
WA_ShowWithoutActivating on the popup as a defensive second layer. _focus_and_highlight gained a
highlight: bool = True parameter; the three settings-search navigation call sites now pass
highlight=False so the destination widget still gets focused (and the tab/window still switches)
without the #f0c674 flash.
