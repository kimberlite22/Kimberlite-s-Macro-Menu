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

## GUI & UX

- preset-active-row-spacing - small gap added between the preset list/buttons row and the "Runs on
  Start" / "Set as Active" row inside the Presets group box
  Review:
- settings-search-follow-up - fixed the settings-search popup stealing keyboard focus from the
  search box on every keystroke, and removed the temporary #f0c674 highlight flash when navigating
  to a search result (destination still gets focus and the tab/window switch).
  Review:
- map-placement-checkbox-order - both Map Placement tab checkboxes now sit below "Number of
  placements" with a small gap, order unchanged (custom tower slots, then custom camera actions)
  Review:
