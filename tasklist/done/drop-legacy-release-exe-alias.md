Title:     Follow-up from project-rename: drop the temporary "Kimberlites-Anime-Expedition-Macro.exe"
           release asset alias once installs have migrated
Completed: 2026-08-03
Commit:    -

Result: .github/workflows/release.yml no longer builds or publishes the second, pre-rename-named
copy of the installer exe; each release now ships exactly one installer asset
(Kimberlites-Macro-Menu.exe) plus update.ini. Removed at the user's explicit request even though no
real (non-prerelease) build had yet shipped the rename, so any install still on a pre-rename build
will need a manual reinstall from the releases page instead of a smooth auto-update.
