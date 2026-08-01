Title:     Victory und defeat count und generell alle stats sollen beim neustarten des macros resettet
           werden
Completed: 2026-08-01
Commit:    a3d35e3

Result: StartMacro() now zeroes StartRepeatCount, VictoryCount and DefeatCount once per genuine new
Start (F10 or the local IPC bridge's START command), in the same Critical block that already resets
PendingPresetSwitch/PresetSwitchRestartPending/StopRequested. Internal restarts that reuse StartMacro's
own restart loop (disconnect auto-reconnect, a committed queued preset switch) do NOT re-enter this
block, so they correctly keep accumulating into the same lifetime counts instead of resetting them.
local_bridge.ahk's status writer and gui/app/main_window.py's stats display already read these globals
live and needed no changes; both picked up the zeroed values automatically once the AHK side resets
them.
