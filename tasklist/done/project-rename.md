Title: Ändere den namen des projektes Kimberlites anime expedition macro zu einfach nur Kimberlites
       Macro Menu in Allen Vorkommen
Completed: 2026-08-02
Commit:    -

Result: Renamed the project from "Kimberlite's Anime Expedition Macro" / "Anime Expedition Macro"
to "Kimberlite's Macro Menu" everywhere: GUI/AHK/OCR/agent APP_NAME constants, the branded release
exe ("Kimberlites-Macro-Menu.exe"), all doc/description strings (CLAUDE.md, README.md, gui/ocr/
remote BUILD.md/README.md, pyproject.toml/package.json descriptions, the remote website), and the
GitHub repository itself (renamed to github.com/kimberlite22/Kimberlite-s-Macro-Menu). Added a
one-hop legacy-name migration on both the per-user install directory (gui/app/launcher_paths.py's
LEGACY_APP_NAME/legacy_install_dir() plus self_install.py's new cleanup_legacy_installation(), and
the matching AppName/LegacyAppName pair already established in tower_defense_macro_gui.ahk) and the
remote agent's own MacroDir (remote/agent/internal/config/config.go), and a temporary compatibility
copy of the release exe under the old filename so already-installed builds' self-updater is not
stranded (.github/workflows/release.yml; follow-up to drop it later tracked in
tasklist/open/workflow/drop-legacy-release-exe-alias.md). The Roblox game's own name ("Anime
Expedition") and internal, non-user-visible identifiers (animeexpedition-agent.exe,
animeexpedition-gui, AnimeExpeditionMacro/AnimeExpeditionAgent) were deliberately left unchanged.
The local checkout folder name ("Anime-Expedition-Macro-Menu") is deliberately left unchanged too,
since it is the live working tree for multiple concurrent sessions; renaming it is a manual,
purely-cosmetic step left to the user for whenever no session is active in it.
