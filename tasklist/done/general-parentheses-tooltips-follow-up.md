Title:     ok, add tooltips instead now
Completed: 2026-08-02
Commit:    bd476e1

Result: Investigated why the tooltips added by general-parentheses-to-tooltips (commit e15ddd4)
        were reportedly not showing up. Empirically verified with a headless PySide6/pytest-qt
        probe (QT_QPA_PLATFORM=offscreen, matching gui/tests/conftest.py) that the code is correct:
        every setToolTip() call lands on the right, visible, enabled widget with non-empty text,
        and manually posting a real QEvent::ToolTip help event to a target widget makes
        QToolTip.isVisible() become True with the exact expected text. There is no implementation
        bug and no gui/app/*.py file was changed.

        The actual root cause is release staleness: commit e15ddd4 merged into main at
        2026-08-01 15:34:20, but the latest shipped release tag is v0.4.16, cut at
        2026-08-01 03:38:32, before that commit and before roughly nine other approved GUI changes
        reviewed in the same batch (commit 863d715). No release has shipped since (VERSION is still
        0.4.16, no later "Bump version" commit), and .github/workflows/release.yml only
        builds/publishes gui.exe on a pushed version tag, never on a plain merge to main. So the
        user's installed gui.exe necessarily predates e15ddd4 and simply does not contain the
        tooltip code yet; hovering over the old, still-parenthetical labels shows nothing because
        that binary was never built from the new source.

        Added a clarification to CLAUDE.md's tasklist routine (`Pending release lists` section):
        a PENDING_REVIEW.md entry reflects a merge to main only, not necessarily something present
        in the user's installed app yet, and a session should check commit-vs-release ancestry
        (`git merge-base --is-ancestor <commit> <tag>`) before treating a confusing review comment
        as an implementation bug. `python -m pytest gui/tests/ -q` passes unchanged (no gui/ files
        touched).
