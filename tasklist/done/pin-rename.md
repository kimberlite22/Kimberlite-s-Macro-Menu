Title:     Placement mode soll auf pin umbenannt werden, und das window nur noch auf die position
pinnen. Die gui mit log und status die normalerweise beim macroen stehen sollen nicht mehr
auftauchen. Der pin button ist lediglich das window an die richtige stelle zu bekommen um positions
festzulegen.
noch dazu nur das window soll pinned sein aber der rest der grau hintergrund alles logs soll nicht
da sein
Completed: 2026-07-31
Commit:    816fb5f

Result: F7 / the Pin button / the local bridge's FORCE_GAME_WINDOW command now only move and lock
the game window into the opening rectangle; the gray fullscreen overlay and the log/stats panel no
longer appear while pinning (ForceGameWindow gained a showOverlay parameter, defaulting to true so
a real macro run still shows the full overlay). "Placement Mode" was renamed to "Pin" throughout the
GUI, hotkey docs, README and the remote-access Documentation tab. Escape still releases the pin
(its CloseOverlay guard was widened to also fire when only the window lock, not the overlay, is
active). Pin does not toggle off on a second F7 press and does not release when an F8 capture ends;
it stays locked until Escape is pressed or a macro run starts - unchanged from the prior Placement
Mode behavior, which already worked this way.
