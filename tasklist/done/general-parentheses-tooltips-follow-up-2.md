Title:     Well i have the version with the update built right now and i dont see the tooltips when
           hovering over a label or field
Completed: 2026-08-02
Commit:    -

Result: Re-investigated with new evidence rather than repeating the earlier stale-build conclusion
        unverified. Release ancestry is unchanged since the prior follow-up: v0.4.16 is still the
        latest shipped tag and it still predates both e15ddd4 (the tooltip commit) and, more
        importantly, commit 2d442af ("gui-ux: make every QLabel mouse-selectable app-wide", merged
        the same day this report came in), which flips Qt.TextInteractionFlag.TextSelectableByMouse
        on every QLabel app-wide via CheckmarkProxyStyle.polish() - a real, specific candidate for
        "tooltips silently stopped working" given how broadly it touches QLabel, so it was tested
        directly rather than dismissed.

        Two headless PySide6 probes (QT_QPA_PLATFORM=offscreen), run against this exact worktree's
        gui/ code, both matching production exactly (QApplication.setStyle(CheckmarkProxyStyle
        ("Fusion")) as in gui/app/main.py:258, a QFormLayout.addRow(str, widget) label built the same
        way main_window.py builds its own tooltip-bearing labels, with TextSelectableByMouse applied
        by the real polish() override): (1) a manually constructed QHelpEvent(QEvent.ToolTip) is
        accepted and produces the correct QToolTip.isVisible()==True/text; (2) a second, stricter
        probe using QTest.mouseMove + QTest.qWait to pump Qt's own automatic hover-detection timer
        (not a hand-built event, so it also exercises the real "is this widget still hoverable"
        logic) shows the identical result. TextSelectableByMouse does not suppress or interfere with
        tooltip delivery in either case, ruling that hypothesis out. Also audited: no
        installEventFilter/eventFilter/notify override/WA_TransparentForMouseEvents/setMouseTracking
        exists anywhere in gui/app/*.py that could swallow hover events; style.qss's QToolTip rule
        (dark background, light text, visible border) is not an invisible/degenerate style; and
        gui/app/update_check.py plus self_install.py were read end to end for a silent-downgrade
        path (self-update replacing a fresh local build with the stale official release) - none
        exists, since VERSION is still 0.4.16 (unbumped since the last tag) so
        check_available_update's available <= current check never offers a downgrade, and
        self-install unconditionally installs/relaunches whatever exe was actually launched.

        No code defect was found; the tooltip mechanism is demonstrably correct on current main,
        with or without the newly added label-selectability change. The most likely remaining
        explanation is still that the build the user ran was not actually built from a commit
        including e15ddd4/2d442af (no tagged release ever has, and a local PyInstaller build/dev run
        is the only way to get either), but this could not be fully pinned down without knowing
        exactly which binary and which specific label/field the user tested - flagged in the
        PENDING_REVIEW.md entry for the user to confirm on their next attempt.
