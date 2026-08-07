Title:     Mach auch das man das window der remote verbindung auch normal resizen kann, weil im moment
           ist das so das man nur abschneidet und der inhalt der remote session ist aber immer noch
           fullscreen, also in 100% bildschimr nimmt es ein. Wenn ich das window resize dann schneidet
           es nur den teil ab es wird aber nicht kleiner wie es sein soll eigentlich.
Completed: 2026-08-07
Commit:    -

Result: The .rdp file now carries "smart sizing:i:1", so the Remote Desktop client scales the
session picture into whatever window size is chosen instead of cropping it. Confirmed against the
generated file before the change: it pinned desktopwidth 1024 and desktopheight 768 with no scaling
directive of any kind, which is exactly the reported "resizing only cuts a part off" behavior.

"dynamic resolution:i:1" is deliberately NOT used, even though it is the crisper option, and the
reason is recorded in the code so a later change does not upgrade it back. Dynamic resolution
changes the session's REAL resolution as the window is dragged, and this macro pins the game window
into a fixed opening rectangle whose coordinates are all stored as a percentage of it (see "Key
conventions" in CLAUDE.md). A resolution change under a running macro moves that reference frame and
silently breaks every stored coordinate, which is far worse than a slightly soft preview image.

Scope note, raised with the user rather than changed unilaterally: the 1024x768 session size itself
is untouched here, since that size is the coordinate reference frame the macro's stored percentages
resolve against, so changing it is not a cosmetic decision. Smart sizing means the window can now be
any size and shape, but the session underneath is still 1024x768 and will look soft when stretched
far beyond it. Whether that default should instead match the physical desktop is a separate call.

Verified with the full gui/ pytest suite (425 passed), including a new assertion that the generated
.rdp contains "smart sizing:i:1" and contains no "dynamic resolution" line at all, and by dumping
the real generated file.
