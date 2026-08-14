AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead
(see "Tasklist routine" in CLAUDE.md). Run `node tools/regen-overview.mjs` after any change
under tasklist/open/ or tasklist/done/ instead of editing this file by hand.
Finished-task archive: tasklist/DONE.md.

Last regenerated: 2026-08-14

## FIXES

1. [disconnect-rejoin-click-not-link](open/fixes/disconnect-rejoin-click-not-link.md) - A
   detected disconnect always recovers the way it did before the private server link was
   introduced: reactivate the game window, click the configured Reconnect button, restart the
   preset from its first screen. The link-based rejoin branch in CheckDisconnectTick is gone, so
   no disconnect ever hands off to the browser or teleports through a share link. The [General]
   PrivateServerLink setting itself [...] (full text in
   open/fixes/disconnect-rejoin-click-not-link.md)

2. [live-stats-default-map-name](open/fixes/live-stats-default-map-name.md) - The Live Stats
   tab's "Current Map" shows the map the macro is actually running on, including when that is
   the configured Default Map, instead of "(none)". Today it reports "(none)" precisely in the
   case where the macro is happily using a map: macro/local_bridge.ahk:603 publishes currentMap
   from LastDetectedMap, which stays empty when detection did not run or matched nothing, while
   everything [...] (full text in open/fixes/live-stats-default-map-name.md)

3. [log-write-disk-full](open/fixes/log-write-disk-full.md) - A full disk degrades visibly
   instead of silently. Today LogMsg() (macro/tower_defense_macro_gui.ahk:3711) appends the line
   under a bare try, and the same bare-try pattern guards the crash handler's own log write at
   :137, so a write that fails because the volume is full throws, is swallowed, and nothing
   anywhere says the log stopped recording. The on-screen panel keeps scrolling, so the run
   looks [...] (full text in open/fixes/log-write-disk-full.md)

## WORKFLOW

1. [remove-session-shell-launcher-deadweight](open/workflow/remove-session-shell-launcher-deadweight.md) - The
   separate AEMSessionShell.exe launcher and the "which mode am I in" detection that reads the
   running executable's own filename are gone, and session-shell mode is selected only by the
   --session-shell flag. Follow-up from rdp-initial-program-does-nothing: PR #133 added them to
   work around a supposed CreateProcess quoting/argument problem, and the investigation then
   proved that CreateProcess [...] (full text in
   open/workflow/remove-session-shell-launcher-deadweight.md)

2. [ci-run-ahk-matching-tests](open/workflow/ci-run-ahk-matching-tests.md) - The OCR matching
   test table runs on every push and pull request like the ocr/ pytest suite does, so a change
   to the matching rule cannot merge with the table red. Today it only runs when someone
   remembers to run it locally.

## GUI & UX

1. [general-parentheses-tooltips-follow-up-5](open/gui-ux/general-parentheses-tooltips-follow-up-5.md) - Follow-up
   from general-parentheses-tooltips-follow-up-4: the user confirmed a freshly rebuilt exe (not
   a stale instance) still shows no tooltips and found nothing unusual in Windows's own
   tooltip/hover settings or third-party mouse software, but has not yet reported the exact
   PySide6 version their build resolved or tried a plain source run (`python -m app.main`) to
   isolate whether this is [...] (full text in
   open/gui-ux/general-parentheses-tooltips-follow-up-5.md)

2. [map-advanced-rename-camera-setup](open/gui-ux/map-advanced-rename-camera-setup.md) - The Map
   Placement tab's "Map Advanced Settings..." button reads "Camera Setup Settings...", and the
   window it opens is titled to match, so the name says what the window is for instead of what
   tier of settings it holds. The button is gui/app/main_window.py:661
   (self.map_advanced_button, built by self._button("Map Advanced Settings...",
   self._open_map_advanced)); the window title is [...] (full text in
   open/gui-ux/map-advanced-rename-camera-setup.md)

3. [screen-detection-settings-placement](open/gui-ux/screen-detection-settings-placement.md) - The
   "Screen Detection" group box in the preset/screen editor (gui/app/edit_preset_window.py,
   currently always shown, ~lines 115-138) is no longer always visible; it moves under/inside a
   "Screen Settings" section that is only shown when the user wants to see or edit detection,
   decluttering the default step-editing view. Resolved shape: a "Screen Settings..." button
   opening a dedicated dialog [...] (full text in
   open/gui-ux/screen-detection-settings-placement.md)

4. [session-shell-control-window-removal](open/gui-ux/session-shell-control-window-removal.md) - Opening
   the background session no longer puts a control window on top of it, and the "Start Explorer"
   escape hatch is reachable from the main macro window on the physical desktop instead. The
   window is SessionShellWindow in gui/app/session_shell.py (built by _build_ui at :345; the
   buttons are "Start Roblox", "Start Explorer" at :368 and "Sign out"), and it appears in BOTH
   background session modes: [...] (full text in
   open/gui-ux/session-shell-control-window-removal.md)

## MAJOR

1. [multi-game-support-restart-ux](open/major/multi-game-support-restart-ux.md) - Follow-up from
   multi-game-support: "Switch to Selected" (gui/app/main_window.py's _switch_game) currently
   only writes config.ini and refreshes the GUI's own displayed data, then tells the user to
   restart manually - the AHK engine's ActiveGameName is resolved once at startup and stays
   fixed for the process's lifetime (InitGames() in tower_defense_macro_gui.ahk), so the GUI
   ends up showing the newly [...] (full text in open/major/multi-game-support-restart-ux.md)

2. [remove-challenge-usage-mechanic](open/major/remove-challenge-usage-mechanic.md) - The daily
   challenge-usage mechanic is gone from the whole program, not just from the Preset Settings
   tab. That means the "Today's Challenge Usage" group box (gui/app/main_window.py:578, its Used
   / Daily limit spin boxes at :584-:595, _usage_changed at :1364 and the load path at
   :1054-:1055), the per-option counters it edits, and the engine logic that consumes them. The
   mechanic reaches further [...] (full text in open/major/remove-challenge-usage-mechanic.md)

3. [screen-detection-overhaul](open/major/screen-detection-overhaul.md) - A screen is
   self-identifying: it starts with its own entry detection, then runs its steps, then the
   global screen detection decides which screen comes next. Ties are resolved by a per-screen
   configured default instead of by step order.

4. [global-screens](open/major/global-screens.md) - Screens (their name, identity and entry
   detection, per [[screen-detection-overhaul]]) are defined once globally instead of being
   duplicated inside every preset's `[Preset_<name>]` section. Every preset recognizes the same
   set of screens; only the step-sequence run on each screen stays preset-specific. The
   "Challenges" preset's current 3 screens (Before Map Detection / Ingame / Round End) are the
   [...] (full text in open/major/global-screens.md)

5. [ocr-expected-variants](open/major/ocr-expected-variants.md) - Any "expected text" field used
   for OCR matching supports several independent text variants instead of a single string, each
   scored separately so the best matching variant counts as detected. Wherever a "Test OCR"
   button already exists for such a field, a new button next to it (working label "Add as
   expected") adds the just-recognized text as a new variant.

6. [remote-agent-tab-online-settings](open/major/remote-agent-tab-online-settings.md) - The
   "Remote Agent" tab (gui/app/remote_agent_tab.py) is renamed to "Online Settings", drops its
   explanatory text, and is trimmed down to just sign-in and pair; the agent executable path
   field is replaced by automatic detection instead of manual entry, and the server URL is fixed
   to kimberlitemacro.duckdns.org instead of being user-entered. Explicitly deprioritized by the
   user: not needed right [...] (full text in open/major/remote-agent-tab-online-settings.md)

7. [ocr-samples-map-profiles-outcomes](open/major/ocr-samples-map-profiles-outcomes.md) - "Save
   Sample" / "Choose Sample..." reach every expected text, not just the ones a Logic step's Name
   field holds. A map profile's ExpectedText and an Advanced Detection outcome's Name get the
   same two buttons next to their own fields, so a sample can be filed under the text the
   matcher actually compares against.

8. [opencv-template-matching](open/major/opencv-template-matching.md) - Screens and steps can be
   detected by OpenCV template or color matching, as an alternative to the existing OCR-text
   detection, for cases text recognition handles poorly (icons, color states, non-text UI
   elements).

9. [agent-self-update-codesigning](open/major/agent-self-update-codesigning.md) - animeexpedition-agent.exe
   updates itself automatically (reading AGENT_LATEST_VERSION from the backend) instead of
   requiring the operator to distribute updates manually, without triggering Windows
   SmartScreen/user-trust warnings.
