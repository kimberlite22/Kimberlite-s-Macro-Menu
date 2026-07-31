Title:     wenn man das macro startet und auf refresh game processes klickt dann kommt da wait for
           the previous command to finish und das verschwindet nie
Completed: 2026-07-31
Commit:    -

Result: Two independent fixes, both confirmed by static reading (live repro still not authorized
        this session). (1) gui/ipc/client.py's abandoned-command detection now checks the AHK
        engine's own heartbeat (local_status.json's timestamp, republished by the same SetTimer
        tick that would consume local_cmd.txt) instead of a flat time guess, so a dead/frozen/
        never-started engine is detected and a stuck file cleared in a few seconds instead of up
        to 90s (or, before today's earlier stuck-command fix, forever). (2) general_game_process_
        refresh_button is now disabled for the duration of its call, mirroring RemoteAgentWindow's
        pair_button and the "Test OCR" buttons: its pump=QApplication.processEvents wait let a
        second, impatient click queue a duplicate LIST_GAME_PROCESSES while the first was still in
        flight, each rejection re-showing its own "not sent" toast - which is what actually made
        the status bar look permanently stuck, since MainLoop's own waits (Sleep-based throughout:
        WaitSecondsInterruptible, DragRightClick, the OCR poll loop) all yield back to
        LocalBridgeTick normally and did not show any sign of starving it during a run.
