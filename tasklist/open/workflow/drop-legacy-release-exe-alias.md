Title: Follow-up from project-rename: drop the temporary "Kimberlites-Anime-Expedition-Macro.exe"
       release asset alias once installs have migrated

Prio:  1

Goal:  .github/workflows/release.yml stops publishing the release EXE a second time under the old,
       pre-rename filename "Kimberlites-Anime-Expedition-Macro.exe" once it is no longer needed, so
       every future release goes back to shipping exactly one installer asset.

Files: .github/workflows/release.yml ("Finalize the single installer exe" and "Publish GitHub
       release" steps)

Steps:
  1. Confirm enough time/releases have passed since the project-rename PR merged that active
     installs have had the chance to auto-update at least once (each self-update also runs
     gui/app/self_install.py's cleanup_legacy_installation(), which retires the old install
     directory and Start Menu shortcut, and moves the install onto the current RELEASE_EXE_NAME
     going forward). There is no automatic signal for this - it is a judgment call, not something
     to infer from repo state alone; ask the user before removing the alias if it is not obvious.
  2. In "Finalize the single installer exe", remove the second `Copy-Item` that produces
     'dist/Kimberlites-Anime-Expedition-Macro.exe' (and its comment block).
  3. In "Publish GitHub release", remove 'dist/Kimberlites-Anime-Expedition-Macro.exe' from both the
     `gh release upload` and `gh release create` asset lists.
  4. Leave everything else (the update.ini metadata, the primary Kimberlites-Macro-Menu.exe asset)
     unchanged - this only removes the temporary compatibility copy.

Open:  How long to wait before doing this is a judgment call for the user (how many releases /
       how much time since the rename shipped), not something this task file can decide on its own.
