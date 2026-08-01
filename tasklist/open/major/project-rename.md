Title: Ändere den namen des projektes Kimberlites anime expedition macro zu einfach nur Kimberlites
       Macro Menu in Allen Vorkommen
Prio:  5

Goal:  Every occurrence of the project's old name ("Anime Expedition macro" / "Kimberlite's Anime
       Expedition Macro") in the codebase, GUI, docs and public-facing surfaces reads "Kimberlite's
       Macro Menu" instead.
Open:  Scope needs deciding before this can be planned in detail: does the rename cover only visible
       strings (GUI window title, docs, website), or also the installed app's folder name and
       %LocalAppData% path (gui/app/self_install.py, gui/app/launcher_paths.py), which would need a
       migration step for existing installs so the self-updater does not silently orphan them? Does
       it also cover the GitHub repository itself (currently
       github.com/kimberlite22/Kimberlite-s-Anime-Expedition-Macro) and the local repo folder name
       ("Anime-Expedition-Macro-Menu")? Renaming the GitHub repo changes the remote URL for every
       existing clone and worktree and for CI, so that specifically needs explicit confirmation
       before touching it. For reference, a case-insensitive grep for "Anime Expedition" currently
       matches in: tasklist/INBOX.md, CLAUDE.md, remote/server/web/index.html (see
       [[website-header-rebrand]] for that one specifically), gui/tests/test_launcher_paths.py,
       gui/app/main.py, macro/tower_defense_macro_gui.ahk, gui/pyproject.toml,
       gui/tests/test_self_install.py, gui/app/launcher_paths.py, README.md,
       .github/workflows/release.yml, gui/app/remote_agent_window.py, ocr/pyproject.toml,
       ocr/ocr_helper/cli.py, remote/README.md, remote/server/.env.example, remote/agent/main.go,
       remote/server/package.json, remote/agent/internal/config/config.go,
       remote/server/src/index.ts, remote/server/src/auth/auth.ts,
       macro/ocr_result_disconnect.txt.
