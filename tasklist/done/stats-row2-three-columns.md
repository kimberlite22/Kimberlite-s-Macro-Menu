Title:     ok the 4 stats in one line looks ugly replace screen repition count dann mit session time
           damit es fittet
Completed: 2026-08-04
Commit:    -

Result: The Application Stats panel's row 2 is back to 3 evenly-spaced columns like rows 1 and 3
        (was 4): Screen Repetition Count is gone from the panel, and Session Time now sits in its
        place, next to Step Repetition Count and Current Step Time. ScreenRepeatCount itself is
        untouched everywhere else (still tracked, still published to the remote/local bridge status
        files); only its cell in this overlay panel is removed. The "Copy" button's clipboard text
        is unchanged and still includes Screen Repetition Count.
