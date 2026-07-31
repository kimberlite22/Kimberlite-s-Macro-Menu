Title: wenn man das macro startet und auf refresh game processes klickt dann kommt da wait for
       the previous command to finish und das verschwindet nie
Prio:  1

Goal:  Clicking "Refresh" next to the game process picker (General tab) after starting the macro
       must not get permanently stuck showing an IPC-busy status message; it should either
       succeed or show a message that clears once the underlying condition resolves.
Files: gui/ipc/client.py (LocalIpcClient.send_command: raises IpcBusyError when
       local_cmd.txt/.tmp already exists, or when self._awaiting_ack is already true - single-slot
       file protocol, no retry/wait built in), gui/app/main_window.py (_refresh_game_processes,
       _send, _show_message: an 8s statusBar().showMessage, so a single busy message should clear
       on its own - "never disappears" more likely means it keeps getting RE-shown on repeated
       clicks/polling than that one message is literally permanent), macro/local_bridge.ahk
       (LocalBridgeTick/LocalBridgeProcessCommand, the SetTimer(...,125) bridge loop that reads and
       deletes local_cmd.txt; LocalBridgeStartMacro defers the actual run via a one-shot
       SetTimer(LocalBridgeRunStartAsync,-1) so START itself should ack almost immediately),
       macro/tower_defense_macro_gui.ahk (ForceGameWindow/PinClick, StartMacro/MainLoop - whether
       MainLoop's per-step Sleeps reliably yield back to LocalBridgeTick while a run is active).
Steps: 1. Reproduce live (needs the user's go-ahead per CLAUDE.md's "do not run the app" rule,
          which blocked confirming this from static reading alone): start the macro, click
          Refresh, and watch macro_log.txt plus whether local_cmd.txt/local_cmd.txt.tmp lingers
          on disk while the status bar shows the busy message.
       2. If local_cmd.txt genuinely lingers unconsumed: find which MainLoop step (or which
          LocalBridgeApplyCommand handler) is running without yielding long enough that
          LocalBridgeTick's 125ms timer cannot get back in to read/delete it.
       3. If the file is NOT lingering (engine consumes it fine) but the message still reappears:
          the bug is on the Python side - likely the button/poll path calling
          send_command()/_refresh_game_processes repeatedly while a prior call is still
          in-flight (the pump=QApplication.processEvents wait in _refresh_game_processes lets
          Qt process a second click reentrantly during the first call's own wait), each hit
          producing its own fresh 8s message and making it look permanently stuck even though
          any single message does clear.
       4. Fix at the diagnosed layer: either make the AHK side keep consuming local_cmd.txt
          promptly during a run, or disable/guard the Refresh button (and the automatic startup
          refresh) while a command from the same client is already in flight, matching the
          engine_process.py wait_for_local_command_slot() precedent used at GUI startup.
Open:  Root cause not confirmed - this file records what static reading of the IPC/bridge code
       ruled in/out (see Files/Steps) so the next session does not have to redo that reading, but
       actually nailing the fix needs a live repro this session was not authorized to run.
