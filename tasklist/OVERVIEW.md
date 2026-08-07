AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead
(see "Tasklist routine" in CLAUDE.md). Run `node tools/regen-overview.mjs` after any change
under tasklist/open/ or tasklist/done/ instead of editing this file by hand.
Finished-task archive: tasklist/DONE.md.

Last regenerated: 2026-08-07

## FIXES

1. [gui-exe-lingers-first-launch](open/fixes/gui-exe-lingers-first-launch.md) - Follow-up from
   engine-still-not-closing-followup: that task sped up and hardened the shutdown path reached
   when the MAIN window closes (main.py's QApplication.aboutToQuit / closeEvent), but the user's
   own retest still finds a stray gui.exe left behind specifically the very first time a freshly
   built/installed exe is launched. That first launch never reaches the window-close path at
   all: [...] (full text in open/fixes/gui-exe-lingers-first-launch.md)

## WORKFLOW

1. [remove-session-shell-launcher-deadweight](open/workflow/remove-session-shell-launcher-deadweight.md) - The
   separate AEMSessionShell.exe launcher and the "which mode am I in" detection that reads the
   running executable's own filename are gone, and session-shell mode is selected only by the
   --session-shell flag. Follow-up from rdp-initial-program-does-nothing: PR #133 added them to
   work around a supposed CreateProcess quoting/argument problem, and the investigation then
   proved that CreateProcess [...] (full text in
   open/workflow/remove-session-shell-launcher-deadweight.md)

## GUI & UX

1. [general-parentheses-tooltips-follow-up-5](open/gui-ux/general-parentheses-tooltips-follow-up-5.md) - Follow-up
   from general-parentheses-tooltips-follow-up-4: the user confirmed a freshly rebuilt exe (not
   a stale instance) still shows no tooltips and found nothing unusual in Windows's own
   tooltip/hover settings or third-party mouse software, but has not yet reported the exact
   PySide6 version their build resolved or tried a plain source run (`python -m app.main`) to
   isolate whether this is [...] (full text in
   open/gui-ux/general-parentheses-tooltips-follow-up-5.md)

2. [screen-detection-settings-placement](open/gui-ux/screen-detection-settings-placement.md) - The
   "Screen Detection" group box in the preset/screen editor (gui/app/edit_preset_window.py,
   currently always shown, ~lines 115-138) is no longer always visible; it moves under/inside a
   "Screen Settings" section that is only shown when the user wants to see or edit detection,
   decluttering the default step-editing view. Resolved shape: a "Screen Settings..." button
   opening a dedicated dialog [...] (full text in
   open/gui-ux/screen-detection-settings-placement.md)

3. [window-title-duplicate-app-name](open/gui-ux/window-title-duplicate-app-name.md) - Follow-up
   from window-title-version-indicator: the main window's native title bar shows the app name
   twice ("<build_window_title() text> - Kimberlite's Macro Menu") instead of the plain
   "Kimberlite's Macro Menu vX.Y.Z (local build)" that build_window_title()
   (gui/app/update_check.py) actually returns. Likely cause: main.py:250-252 calls both
   app.setApplicationName(APP_NAME) and [...] (full text in
   open/gui-ux/window-title-duplicate-app-name.md)

## MAJOR

1. [multi-game-support-restart-ux](open/major/multi-game-support-restart-ux.md) - Follow-up from
   multi-game-support: "Switch to Selected" (gui/app/main_window.py's _switch_game) currently
   only writes config.ini and refreshes the GUI's own displayed data, then tells the user to
   restart manually - the AHK engine's ActiveGameName is resolved once at startup and stays
   fixed for the process's lifetime (InitGames() in tower_defense_macro_gui.ahk), so the GUI
   ends up showing the newly [...] (full text in open/major/multi-game-support-restart-ux.md)

2. [live-stats-tab](open/major/live-stats-tab.md) - A new "Live Stats" tab in the Qt window
   shows everything the AHK overlay's panels used to, which is where those numbers now have to
   live. They are gone from the screen: the panels were drawn in the gray area AROUND the
   opening (CreateOverlay in tower_defense_macro_gui.ahk sizes the stats bar from `screenH -
   (hole.y + hole.h)` and the log column from `screenW - (hole.x + hole.w)`), and a [...] (full
   text in open/major/live-stats-tab.md)

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
   checked separately (exact match first, then the existing 6-character fuzzy fallback) so any
   one matching variant counts as detected. Wherever a "Test OCR" button already exists for such
   a field, a new button next to it (working label "Add as expected") adds the [...] (full text
   in open/major/ocr-expected-variants.md)

6. [remote-agent-tab-online-settings](open/major/remote-agent-tab-online-settings.md) - The
   "Remote Agent" tab (gui/app/remote_agent_tab.py) is renamed to "Online Settings", drops its
   explanatory text, and is trimmed down to just sign-in and pair; the agent executable path
   field is replaced by automatic detection instead of manual entry, and the server URL is fixed
   to kimberlitemacro.duckdns.org instead of being user-entered. Explicitly deprioritized by the
   user: not needed right [...] (full text in open/major/remote-agent-tab-online-settings.md)

7. [rapidfuzz-fuzzy-matching](open/major/rapidfuzz-fuzzy-matching.md) - OCR expected-text
   comparisons (`TextContainsPartialMatch` in tower_defense_macro_gui.ahk, currently a
   fixed-length substring-window heuristic) use a real edit-distance/similarity score instead,
   so match quality no longer depends on a hardcoded window size.

8. [opencv-template-matching](open/major/opencv-template-matching.md) - Screens and steps can be
   detected by OpenCV template or color matching, as an alternative to the existing OCR-text
   detection, for cases text recognition handles poorly (icons, color states, non-text UI
   elements).

9. [agent-self-update-codesigning](open/major/agent-self-update-codesigning.md) - animeexpedition-agent.exe
   updates itself automatically (reading AGENT_LATEST_VERSION from the backend) instead of
   requiring the operator to distribute updates manually, without triggering Windows
   SmartScreen/user-trust warnings.
