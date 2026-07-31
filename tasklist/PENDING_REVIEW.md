HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes a Claude session just finished, staged here so the user can try them once before they move
to PENDING_RELEASE.md for the final pre-release check. Two lines per change, grouped by task group in
the fixed order fixes, workflow, gui-ux, major:

    - <slug> - <one-liner>
      Review:

Fill in the Review: line yourself once you have tried the change, right here in the file, no chat
needed: a bare approval word and nothing else (approved / ok / okay / yes / lgtm) means it works, no
follow-up needed. Anything else, including an approval word plus more text ("approved, but X" does
NOT count), is read as a follow-up change to make in full, your own words, no particular format
required. The next /tasklist run resolves it: an approval moves the entry to PENDING_RELEASE.md, a
follow-up becomes a new task under tasklist/open/ (this line's text is its Title) and this entry is
dropped.

## FIXES

- config-load-failure-permanent - when config.ini cannot be read at startup, the General tab no
  longer stays stuck on all-zero placeholders (it keeps retrying and recovers by itself), Save is
  blocked in that state so it cannot overwrite your real config, and the yellow bar says so.
  Review:
- tower-loadout-slot-choices - the General tab's Tower Loadout dropdowns now list the hotbar
  positions 1-6 (what the engine actually uses) instead of challenge option names, so your saved
  slots show up again. Nothing was lost; the timing fields reading 0 were your real settings.
  Review:
- config-read-race-on-save - "config.ini could not be read" / permission errno 13 after a save
  should no longer happen: the background poll now waits for config.ini's mtime to settle instead
  of re-reading mid-write-burst. Reported as laptop-only, not reproduced live this session.
  Review:
- refresh-game-processes-stuck-busy - Refresh (game process picker) and any other local command
  now recover from a dead/frozen AHK engine in a few seconds instead of up to 90s, and Refresh no
  longer shows a repeating "not sent" message from a reentrant click while it is already waiting.
  Review:
- pin-one-shot-move - Pin now moves the game window into place once and leaves it alone, so being
  pinned no longer claims the Escape key.
  Review:
- engine-survives-close - closing the GUI now also stops an engine it only attached to (not
  spawned), and closes any open Edit Preset / Map Advanced / Remote Agent window first so the
  process actually quits.
  Review:
