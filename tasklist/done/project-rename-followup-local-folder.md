Title:     ok but rename the local folder too if thats no a problem
Completed: 2026-08-03
Commit:    -

Result: Re-confirmed rather than acted on. project-rename's own Result already explains why the
        local checkout folder ("Anime-Expedition-Macro-Menu") was deliberately left unchanged: it
        is the live working tree for multiple concurrent Claude sessions/accounts, including
        worktrees nested under it, so renaming it out from under an active session would break
        every other session currently using this checkout (this very sweep is running from a
        worktree under it). This stays a manual, purely-cosmetic step for the user to do
        themselves whenever no session is active in this directory - close every open session,
        rename the folder, then reopen from the new path. No code or automation belongs here.
