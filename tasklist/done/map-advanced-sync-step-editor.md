Title:     update in map placements die advanced settings so das sie uptodate mit dem aktuellen step
           editor sind
Completed: 2026-08-07
Commit:    678eeb1

Result: The Map Advanced Settings step editor gained the "Show" point-preview buttons for a Drag
step's start and end coordinates, closing the one gap commit 316a23a left when it wired that button
into every other coordinate editor in the app. Every other difference from the preset Step Editor
was checked and left alone as deliberate: this window only edits Drag / Zoom Out camera actions, so
Name, Wait After, Once per cycle, the on-true/on-false targets, the fallback rows, Advanced
Detection and the Challenge options box have no meaning here, and its two separate capture buttons
suit a drag better than the Step Editor's single "Set Position".
