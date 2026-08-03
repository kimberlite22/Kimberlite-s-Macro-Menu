Title:     I hovererd over everything multiple seconds and not a single tooltip showed up
Completed: 2026-08-03
Commit:    -

Result: This round's own premise (three prior code-level investigations found nothing, so pivot to
        asking the user directly with AskUserQuestion) turned out not to hold in practice: this task
        was worked by a delegated subagent, and AskUserQuestion is not part of that agent's toolset
        in this harness (confirmed by querying the tool registry: it is absent from both the
        directly available tools and the deferred-tool list that every other harness-level tool,
        e.g. ExitWorktree/Monitor/SendMessage, does appear in). So the interactive part of Steps 1-3
        could not run as written. The three questions (exact PySide6 version the build resolved via
        `pip show PySide6`; whether the freshly built exe was hovered rather than a stale running
        instance or old shortcut; whether a plain `python -m app.main` source run also shows no
        tooltips; whether Windows's own tooltip/hover accessibility settings or third-party mouse
        software are configured unusually) were forwarded to the orchestrating session so a live
        human can still answer them, either now or in a fifth follow-up round.

        No code was changed: there was nothing new to act on beyond what general-parentheses-
        tooltips-follow-up-3 already established (the Qt tooltip mechanism, bundled Qt plugins, and
        style.qss are all correct; no frozen-specific code path or app-wide event filter suppresses
        ToolTip events). This closes the same way follow-up-3 did: a documented investigation, no
        code change, waiting on a live answer from the user. The one new, concrete finding this round
        adds is procedural rather than about tooltips: a tasklist round whose own Steps are "ask the
        user" cannot be completed by a delegated subagent in this harness, since AskUserQuestion is a
        top-level-session-only tool here; such rounds need to run in the top-level session itself, or
        need an explicit relay/wait mechanism, to actually get answers before closing.
