Title: it still doesnt work and the procedure to replicate the bug still persist, if there is no obvious fix postpone until later revisit, stealing too much focus right now
Prio:  3

Goal:  Follow-up from settings-search-follow-up-3: the settings search box still stops accepting
       keystrokes and the user's original reproduction steps still hold, even though the
       settings-search-follow-up-2 NoFocus fix (c391e90) is verified sound on current main by a
       full passing test suite. Explicitly deprioritized by the user: postpone this if no obvious
       fix surfaces quickly, it is stealing too much focus right now relative to its impact.
Open:  What exactly reproduces it (which field is focused first, mouse vs. keyboard interaction, how
       many searches in a row) - ask the user for the precise steps next time this is picked up,
       since two rounds of investigation have not been able to reproduce the reported freeze from
       the existing description alone.
