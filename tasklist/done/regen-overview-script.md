Title:     tasklist/OVERVIEW.md wird laut CLAUDE.md "regeneriert", es gibt dafuer aber kein Skript, es
           ist reine Handarbeit ueber inzwischen 218 Zeilen. Bei jedem Task-Abschluss muss die
           MAJOR-Liste durchnummeriert werden. Ein kleines tools/regen-overview.mjs, das open/ und done/
           einliest, wuerde das zuverlaessig und billiger machen, und die Regel "niemals von Hand
           editieren" waere dann auch woertlich haltbar.
Completed: 2026-08-07
Commit:    -

Result: Added tools/regen-overview.mjs (plain Node, no dependencies): it parses every
        tasklist/open/<group>/*.md and tasklist/done/*.md file's Title/Prio/Goal/Completed/Commit/
        Result fields (multi-line values continue until the next known field label), sorts each
        open group by Prio and the done list by Completed date descending (git commit timestamp,
        then slug, as tie-breaks), and rewrites tasklist/OVERVIEW.md from scratch, so the group
        renumbering that used to be manual now happens automatically on every run. `--check` exits
        non-zero on a stale file without writing. Running it against the current tasklist/ also
        fixed real staleness the manual process had already missed: OVERVIEW.md's MAJOR section
        was missing three open tasks entirely (background-session-setup-wizard/-launcher/-minimal-
        shell) and its DONE section was missing the most recently completed one
        (background-session-engine-lifecycle). Updated CLAUDE.md's "Regenerating OVERVIEW.md"
        section and the routine's step 6 to describe running the script.
