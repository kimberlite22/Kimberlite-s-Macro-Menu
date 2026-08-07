Title:     in advanced settings the old gui is still there. The gui should be like the normal preset
           edit ui
Completed: 2026-08-07
Commit:    e6b3705

Result: Map Advanced Settings now has the preset editor's step table (Type / X / Y / End X / End Y /
Drag, reordered by dragging the row-number header) with Add Step / Edit Step... / Delete Selected /
Duplicate and the same shortcuts, and editing opens the SAME StepEditWindow the preset editor uses
via a new map_action_mode restricted to Drag and Zoom Out. The duplicate inline editor is gone, so
the two cannot drift apart again, which is the root cause of the earlier
map-advanced-sync-step-editor follow-up. StepEditWindow also gained a "Set End Position" capture
button for Drag steps, both to preserve the map window's old "Capture end" and because a preset Drag
step's End X/End Y previously could only be typed by hand. Two lifecycle guards were added for the
shared parentless editor: it closes with the window and on a custom-camera toggle, since _save()
only serializes the currently effective section.
