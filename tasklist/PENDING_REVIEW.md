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
