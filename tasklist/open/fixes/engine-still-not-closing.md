Title: not working correctly, postpone until later release
Prio:  1

Goal:  Follow-up from engine-survives-close-followup: the user tried the merged fix (closeEvent
       sweeping every visible top-level widget instead of only the three tracked collections) and
       it still does not close the engine/process correctly. Find out why the sweep is not enough
       and fix the actual remaining leak, instead of the level this was already fixed at once.
Open:  - What exactly "not working correctly" looks like from the user's side (process still
         lingers after close? a specific window still stays open? an error?) - ask before
         re-diagnosing from scratch.
