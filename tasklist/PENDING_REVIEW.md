HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes a Claude session just finished, staged here so the user can try them once before they move
to PENDING_RELEASE.md for the final pre-release check. Two lines per change with a blank line between
them, grouped by task group in the fixed order fixes, workflow, gui-ux, major:

    - <slug> - <one-liner>

      Review:

Leave one blank line between a change's own one-liner and its Review: line as above, and two blank
lines between one change's Review: line and the next change's one-liner, so entries stay easy to
tell apart when skimming the file.

Fill in the Review: line yourself once you have tried the change, right here in the file, no chat
needed: a bare approval word and nothing else (approved / ok / okay / yes / lgtm) means it works, no
follow-up needed. Anything else, including an approval word plus more text ("approved, but X" does
NOT count), is read as a follow-up change to make in full, your own words, no particular format
required. The next /tasklist run resolves it: an approval moves the entry to PENDING_RELEASE.md, a
follow-up becomes a new task under tasklist/open/ (this line's text is its Title) and this entry is
dropped.

## GUI & UX

- settings-search-follow-up-2 - the settings search results popup and its list no longer accept
  keyboard focus at all, so typing into the search box no longer stops registering once the
  results popup is showing (the earlier fix only reclaimed focus once, right after the popup's
  first show())

  Review:


- map-placement-checkbox-order-follow-up - the Map Placement tab's two checkboxes, plus every other
  genuine checkbox-before-text occurrence found in a sweep (Disconnect Detection's reconnect
  checkbox, the Step Editor's fallback/advanced checkboxes), now show their label text first and the
  checkbox second, inline with the other label-then-field rows

  Review:


- general-parentheses-tooltips-follow-up - investigated the "I don't see the tooltips" report;
  verified the tooltip code from general-parentheses-to-tooltips is correct (no gui/ file changed),
  the real cause was that no release had shipped that commit yet, so the installed app was still on
  the old pre-tooltip build. Added a CLAUDE.md note so a future session checks release ancestry
  before treating a similar confusing review as a bug.

  Review:


- challenge-options-to-step-editor - the "Challenge options" widget (Option 1-3 Name/X/Y/Available/
  Priority/Max uses/Availability Check) moved out of Edit Preset's always-visible layout into the
  Step Editor window, shown only for "Option Select" steps; the Availability Check button moved with
  it, and the options still share one set of data across the whole preset

  Review:

