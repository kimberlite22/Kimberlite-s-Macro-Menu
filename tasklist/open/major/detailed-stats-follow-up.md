Title: Remove die step time box und showe einfach die accumulative zeit im step in der application
       status box für den step der gerade aktiv ist, dafür mach den screen time größer das es den
       step time einnimmt
Prio:  2

Goal:  Follow-up from detailed-stats: remove the Time Breakdown overlay's Step Time table, show the
       currently active step's accumulative time inside the Application Stats panel instead, and
       grow the Screen Time table to fill the space the removed Step Time table leaves.
Files: macro/tower_defense_macro_gui.ahk - TimeBreakdownGui construction (~lines 2074-2115,
       screenListH/stepListH split at 2081-2082 and the StepTimeLV AddListView call at 2101-2107),
       its reset branches (~2113-2114, 2120-2121, 2243-2244) and global declarations (~1022-1023,
       2022, 2225), RenderTimeBreakdownPanel's StepTimeLV.Delete()/.Add() calls (~2649-2665), the
       StatsGui "Application Stats" panel construction and row1/row2/row3 grid (~2124-2202),
       RenderStatsPanel (~2728+), the live-tick function that already ticks Session Time every
       second (~2205-2260), and CopyStatsClick's clipboard text (~2708+).
Steps: 1. Remove the "Step Time" header text and the StepTimeLV AddListView call from the
          TimeBreakdownGui block (currently ~2097-2107), and drop the screenListH/stepListH
          0.35/0.65 split (2081-2082) so ScreenTimeLV gets the full innerH below its own header,
          growing into the space Step Time used to occupy.
       2. Remove every remaining StepTimeLV/stepListY/stepListH reference: the reset branches at
          ~2113-2114, 2120-2121, 2243-2244, the global declarations at ~1022-1023, 2022, 2225, and
          the StepTimeLV.Delete()/.Add() calls inside RenderTimeBreakdownPanel (~2649-2665). Keep
          the per-step timing data itself (whatever RenderTimeBreakdownPanel currently computes for
          the Total/Current columns) alive, just stop feeding it into a ListView.
       3. Surface that same per-step accumulative time as a new value inside StatsGui's
          row1/row2/row3 grid (~2147-2202), next to "Current Step" - see Open below for exactly
          which cell it replaces or whether a new column is added.
       4. Update RenderStatsPanel (~2728+), the live-tick function that currently ticks Session Time
          every second (~2205-2260), and CopyStatsClick's clipboard text (~2708+) to populate and
          tick the new field the same way Session Time already does.
Open:  Where exactly does the new "current step time" value go inside StatsGui's 3x3 grid - row2
       already has all three slots filled (Screen Repetition Count, Step Repetition Count, Session
       Time). Replace "Step Repetition Count" with it, or widen the grid with a fourth column? Ask
       the user before implementing.
