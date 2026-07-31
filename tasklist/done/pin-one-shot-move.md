Title:     Change how pinning works. Pinning should just move it in the correct position once, and
           then leave it as is. That makes it so you dont have to claim esc at all
Completed: 2026-07-31
Commit:    -

Result: Follow-up from escape-blocks-other-apps: Pin (F7 / the Pin button) now calls
ForceGameWindow with a new enforceLock=false, so it moves the game window into place once and
leaves it alone, no ongoing lock, no overlay, nothing to release. LockedProcess/OverlayVisible are
now only ever set during an actual macro run, so the Escape #HotIf guard no longer claims the key
just because the window is pinned; it still claims it during a real run and its brief restart gap.
