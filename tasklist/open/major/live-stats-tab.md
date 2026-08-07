Title: Die jetzt removed gui soll in die python gui migrieren, ein neuer tab mit Live-Stats soll
       reinkommen in dem die stats jetzt leben werden mit allem was vorher drin war.

Prio:  3

Goal:  A new "Live Stats" tab in the Qt window shows everything the AHK overlay's panels used to,
       which is where those numbers now have to live. They are gone from the screen: the panels were
       drawn in the gray area AROUND the opening (CreateOverlay in tower_defense_macro_gui.ahk sizes
       the stats bar from `screenH - (hole.y + hole.h)` and the log column from
       `screenW - (hole.x + hole.w)`), and a full-screen opening leaves both at zero, so their own
       size guards skip them entirely. This is also the part the user deferred when the full-screen
       opening was filed ("Die ui soll dann in die pyhton gui aber das koennen wir auch spaeter
       verschieben", see done/roblox-fullscreen-opening.md), now called in.

       What was in there, and therefore what the tab owes:
       - Application Stats, three rows of three: Current Map / Current Screen / Current Step;
         Session Time / Step Repetition Count / Current Step Time; Start Repetition Count /
         Victory Count / Defeat Count.
       - Its "Copy" button, which put those values on the clipboard (CopyStatsClick).
       - The Screen Time table, one row per screen of the running preset (RenderTimeBreakdownPanel).
       - The live log panel (LogGui / LogEdit), which shared that column.

       Most of the values already cross the local bridge: LocalStatus (gui/ipc/protocol.py) carries
       currentMap, currentScreen, currentStep, stepRepeatCount, startRepeatCount, victoryCount and
       defeatCount. Session Time, Current Step Time and the per-screen Screen Time table do not, so
       the bridge has to grow them.

Open:  Decisions to settle first:
       - Whether the AHK panels are deleted in the same change or left in place for a non-full-screen
         opening, where they still render. Two implementations of the same numbers is the thing most
         likely to drift, but deleting them takes the stats away from anyone not using the
         full-screen opening.
       - Whether the log belongs in this tab at all: the Qt window has its own log surface already,
         so this may be two views of one thing rather than a panel to port.
       - How the Screen Time table reaches the GUI. The other status fields are flat scalars written
         about once a second; a table is a list whose length follows the running preset, so decide
         whether it goes into local_status.json or gets its own file, before the shape is fixed.
       - Whether the tab keeps working (showing the last known values, or clearly nothing) while no
         engine is running, since a status file can outlive its engine.
