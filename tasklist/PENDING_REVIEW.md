HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes a Claude session just finished, staged here so the user can try them once before they move
to PENDING_RELEASE.md for the final pre-release check. Two lines per change with a blank line between
them, grouped by task group in the fixed order fixes, workflow, gui-ux, major:

    - <slug> - <one-liner>

      Review:

When there is something specific worth checking (a particular click-path to try, an edge case, a
config value to set first), an optional Notes: paragraph goes between the one-liner and Review:, same
blank-line spacing on both sides. Left out when the one-liner already says everything needed:

    - <slug> - <one-liner>

      Notes: <what to specifically test or look at>

      Review:

Leave one blank line between a change's own one-liner and its Review: line (or its Notes: paragraph
when present) as above, and two blank lines between one change's Review: line and the next change's
one-liner, so entries stay easy to tell apart when skimming the file.

Fill in the Review: line yourself once you have tried the change, right here in the file, no chat
needed: a bare approval word and nothing else (approved / ok / okay / yes / lgtm) means it works, no
follow-up needed. Anything else, including an approval word plus more text ("approved, but X" does
NOT count), is read as a follow-up change to make in full, your own words, no particular format
required. The next /tasklist run resolves it: an approval moves the entry to PENDING_RELEASE.md, a
follow-up becomes a new task under tasklist/open/ (this line's text is its Title) and this entry is
dropped.

## FIXES

- background-session-roblox-not-launching - the reason "Boot straight into the macro" showed an
  error and closed the session, and why Roblox never opened: the session's shell could never start
  at all. Fixed.

  Notes: your screenshot solved it. Windows hands the RDP "alternate shell" straight to
  CreateProcess as a FILE NAME, so it cannot contain quotes or arguments, and we were passing
  "...gui.exe" --session-shell. It looked for a file called exactly that, failed, and took the
  session with it. Proven with three test sessions: unquoted and argument-free is honored, quoted is
  ignored, and unquoted-with-an-argument is ignored. There is now a second executable next to
  gui.exe called AEMSessionShell.exe (a hard link, so it costs no extra disk) whose NAME means "run
  as the session shell", and the .rdp points at that bare path. After rebuilding you should see it
  appear in %LOCALAPPDATA%\Programs\Kimberlite's Macro Menu. Tick the box, press Start, and the
  session should come up with the small control window and the engine, no error. If it does but
  Roblox still does not open, send me session_shell_log.txt, since that would be a different and
  so far untested cause (the share link is opened through the default browser, which may behave
  differently in a session with no Explorer).

  Review:

- background-session-stay-connected - Start no longer disconnects the session a second after it
  appears. Its window stays open and visible, so you can watch it come up, read anything it says,
  and start the macro in it.

  Notes: press Start. A Remote Desktop window should appear and STAY, rather than flashing and
  vanishing. Show is now only for reconnecting after you have closed that window; if you press it
  while the session is still connected, it releases and reattaches instead of quietly creating a
  second session. Two things worth knowing: this also matters for the macro itself, because a
  disconnected RDP session has no rendered desktop and screen capture in it can come back empty; and
  Stop is what ends the session, closing the window only disconnects it.

  Review:


- background-session-match-desktop-resolution - the session now comes up at your screen's own
  resolution (1920x1080 here) instead of a fixed 1024x768, so the window can be made full size.

  Notes: this is the other half of the resizing complaint. The window could not grow past a third of
  your screen because the session itself was only 1024x768, and smart sizing scales the picture
  without raising that ceiling. It also matters beyond window size: your macro coordinates are stored
  as percentages of an opening rectangle measured in real pixels on this desktop, and a 1024x768
  session could not even contain an opening measured on a 1920x1080 screen. If your presets were
  captured on this desktop, they should now mean the same thing inside the session.

  Review:


- smart-sizing-needs-dynamic-resolution-off - smart sizing now works without you turning it on from
  the window's right-click menu.

  Notes: the previous attempt set smart sizing but left dynamic resolution out of the file entirely,
  and "out" is not "off": Windows defaults it ON, and it overrides smart sizing. It is now explicitly
  0, which is also what we want anyway, since letting the session change resolution while you drag
  the window would invalidate every stored macro coordinate.

  Review:


- session-shell-diagnostics - the background session's shell now writes what it did to
  session_shell_log.txt, so a failure that takes the session down with it leaves evidence.

  Notes: this does NOT fix Roblox failing to launch, and nothing was guessed at. Please start a
  session with "Boot straight into the macro" ticked once more, then send me
  %LOCALAPPDATA%\Kimberlite's Macro Menu\session_shell_log.txt. It records whether the engine
  started, whether a link was configured, and whether launching it succeeded, plus any crash, and it
  never writes the link or its code. That file tells us which of the two possible causes it is. The
  remaining work is tracked as background-session-roblox-not-launching.

  Review:


- background-session-stop-confirmation - Stop now waits until the session has really gone before
  saying it stopped, and keeps tracking it when it has not, so a session can no longer be lost and
  left running with the app claiming none exists.

  Notes: press Stop and watch it take a few seconds instead of answering instantly; when it returns,
  the session should already be gone from "query session". If it ever cannot confirm within 30
  seconds it now says so and asks you to press Stop again, and the session stays tracked so a second
  press can still end it. That is the important part to try if you can provoke it. Also fixed: Start
  timing out while the session comes up anyway no longer strands it, it gets adopted and stays
  stoppable, which is what happened to the session you had to have me kill by hand. Buttons now grey
  out while Stop runs, so a double click cannot log off twice.

  Review:


- background-session-window-resize - the Show window can be resized normally now: the picture scales
  to the window instead of just being cropped.

  Notes: press Show and drag the window edges. The session picture should scale to fit rather than
  cut off. It will look somewhat soft when stretched a long way, because the session itself is still
  1024x768 and only the displayed image is scaled. Scaling the real resolution instead was
  deliberately NOT done: this macro stores every coordinate as a percentage of a fixed opening
  rectangle, so a resolution change under a running macro would silently break all of them. If the
  1024x768 default itself is the thing bothering you (a small, squarish picture), say so, since
  changing that is a separate decision that does affect your stored coordinates.

  Review:


- background-session-start-stops-local-engine - Start on the Background Session tab now works from
  a cold state. It asks first, then stops the macro engine running on this desktop, then creates the
  background session, which brings up its own engine.

  Notes: this was a real deadlock, not just a confusing message. Opening the GUI starts an engine in
  your desktop session whenever none is running anywhere, and Start then refused over that very
  engine, so there was no way to reach it from a cold start. It only ever worked for you because
  your hand-made mstsc session already had an engine running. Press Start with the app open and
  nothing else running: you should get a prompt saying the engine on this desktop will be stopped
  (and that any macro run in progress HERE stops with it), and after confirming, the background
  session should come up. Answering No must change nothing at all. Two refusals worth checking on
  purpose: with no saved credential it must now tell you about the credential instead of telling you
  to stop the macro, and it must not stop your engine in that case; an engine running in ANOTHER
  session must never be touched or block anything.

  Review:


- setup-wizard-undetermined-checks - a Background Session setup check that cannot work out its
  answer no longer disables Start. It shows as a Warning instead, Start stays clickable, and the box
  says only to start with warnings if you know what you are doing. A check that did read a value and
  found a real problem still blocks Start exactly as before.

  Notes: this is the follow-up to your report that the fourth point stayed red while the remote
  connection worked flawlessly. Two things worth knowing. First, that exact failure could not be
  reproduced afterwards: your machine passes all four checks now, from source and from a frozen
  build, so pressing Re-check may simply show ready. The root cause was never pinned down (WOW64
  redirection, a lost SystemRoot, the bundled VERSION file, a later code change and a pending
  Windows update were each ruled out with evidence), so this fixes the consequence rather than the
  cause. Second, the check now explains the two different version numbers your Windows reports for
  termsrv.dll: binary 10.0.26100.4484 versus FileVersion 10.0.26100.8875. Only the binary one is
  used to look up the rdpwrap.ini section, because that is what RDP Wrapper itself keys on, which
  your own machine proves (your rdpwrap.ini has a section for 4484 and none for 8875, and RDP
  Wrapper works). The string version is shown as context only and can never make the check pass.

  Review:


- rdp-initial-program-does-nothing - "Boot straight into the macro" actually works now, and the
  option finally describes what it will really do. The reason it never worked: Windows checks an RDP
  session's start-up program against its RemoteApp "published applications" list BEFORE launching
  it, that list is switched on but empty on your machine, so the check missed and nothing started at
  all, not even Explorer. The old "file not found" error was that failed lookup, never your file.

  Notes: this supersedes the background-session-roblox-not-launching entry further up, whose
  explanation (a quoting problem, fixed by adding AEMSessionShell.exe) was WRONG. Do not judge that
  one on its own terms. Proven this time with a purpose-built probe that writes a marker file the
  instant it runs, across three sessions: with the Windows setting at its default the probe did not
  run, with it switched off the probe DID run, and switched back the failure returned. Never judged
  by "Explorer is missing", which is what produced the wrong fix last time. Your machine was left
  exactly as it was; the setting is back at its Windows default.

  What to try. Press Start with the box ticked. You should get a background session that comes up
  with Roblox and the engine running and NO error dialog. On your machine it will take the
  no-administrator route, so that session keeps a normal Windows desktop, and the label under the
  checkbox says so rather than promising "no Windows desktop" it cannot deliver. If you want the
  real no-desktop version, there is now an "Enable no-desktop mode (administrator)" button under the
  checkbox: one UAC prompt, machine-wide, and the same button turns it back off afterwards. Tick the
  box again after pressing it, press Start, and that session should come up with only Roblox, the
  engine and the small control window.

  Two things worth checking on purpose, because they are the risky parts. First, an ordinary Remote
  Desktop login into this PC that you make yourself must NOT boot into the macro: only a session the
  app started within the last few minutes may, and the authorisation is single-use. Second, logging
  on at the physical screen must show nothing at all from this, no window and no flash, since both
  sessions share one Windows profile and the same autostart entry fires for both.

  Still untested, and honestly so: Roblox opening through the private server share link has never
  once been observed to work, because until now nothing ever ran inside that session. If Roblox does
  not open, send me session_shell_log.txt from %LOCALAPPDATA%\Kimberlite's Macro Menu - it records
  whether the launch was attempted and what it returned. Your Roblox account also has to be signed
  in inside that session for a private server link to land anywhere.

  Review:


## WORKFLOW

- build-script-orphan-process-lock - the VS Code build task no longer fails with "Access is denied"
  on gui\dist\gui.exe. The previous run's own smoke test was leaving a gui.exe process alive, and a
  running exe cannot be overwritten, so every second build died.

  Notes: run the build task twice in a row, which is what used to fail. The first run already works
  again (the stale process from your last attempt was killed by hand). If the script ever does find
  something still holding a build output, it now prints a line naming the process and PID before
  stopping it, so a kill is never silent. The same pattern in the three GitHub workflows was left
  alone on purpose: a CI runner is thrown away after one build, so the orphan cannot hurt there.

  Review:


- codex-sandbox-python - delegated Codex work can now run the pytest suites itself instead of
  always reporting that Python is unavailable, so a delegation's own change gets tested before it
  comes back.

  Notes: nothing to click in the app. This needed a one-time permission setup on this machine
  (documented in CLAUDE.md under "Letting Codex run the test suites"): the two Codex sandbox
  accounts were granted read+execute on your Python install, and a new C:\CodexTemp was created and
  made writable for them, because the sandbox runs as a different Windows account that could reach
  neither your Python nor your %TEMP%. Both grants are narrow and reversible with `icacls ...
  /remove`; nothing else in your profile was opened up. Verified by having a delegation run the gui
  suite: 410 passed, the same as a local run.

  Review:


- ci-automate-ocr-build - added .github/workflows/ci.yml, running OCR helper pytest plus a
  PyInstaller smoke build on every push/PR to main (not only on a version tag); release.yml and
  build-exe.yml are untouched, and gui.exe's build was deliberately left out of scope for now.

  Review:


- benchmark-ocr-engines - shadow-mode OCR comparison plus the experimental pre-release
  v0.4.16-dev2 to test it with (dev2 replaces dev1: same comparison, but the app now launches the
  benchmark helper for you instead of you having to run it yourself, see below). Install that
  release's Kimberlites-Anime-Expedition-Macro.exe (it installs over the normal one and keeps your
  config and presets), unzip ocr-benchmark-win64.zip from the same release page and move the
  ocr_benchmark folder it contains into your install directory
  (%LOCALAPPDATA%\Programs\Kimberlite's Anime Expedition Macro\ocr_benchmark\ocr_benchmark.exe) -
  a one-time step. From then on just run the app and press Start like normal; it starts the
  benchmark helper in the background automatically, no extra window to keep open. Play normally
  for about ten hours, then send back ocr_benchmark_log.jsonl from
  %LOCALAPPDATA%\Kimberlite's Anime Expedition Macro. Note: closing the app does not currently stop
  the benchmark helper (a known, separately tracked gap also affecting the OCR helper itself) - it
  is harmless to leave running, but check Task Manager if you want it fully stopped between
  sessions. The macro still acts only on the current Windows OCR result, the three other engines
  are only scored. Nothing auto-updates into this build: it is a pre-release, so the normal
  releases page and the in-app updater keep pointing at the real v0.4.16.

  Review:


- regen-overview-script - tasklist/OVERVIEW.md is now produced by `node tools/regen-overview.mjs`
  instead of by hand: it reads tasklist/open/ and tasklist/done/ and rewrites the file, including
  the group renumbering that used to need manual upkeep after every finished task.

  Notes: nothing to click-test in the app; check that the regenerated tasklist/OVERVIEW.md still
  reads sensibly (it also picked up several entries the manual process had missed, so it moved
  around more than a normal task-completion update would).

  Review:


- drop-legacy-release-exe-alias - release.yml no longer builds or publishes the second,
  pre-rename-named copy of the installer exe (Kimberlites-Anime-Expedition-Macro.exe); each release
  now ships exactly one installer asset (Kimberlites-Macro-Menu.exe) plus update.ini. Note: this was
  removed at your explicit request even though no real (non-prerelease) build has shipped the
  project-rename yet, so any install still on a pre-rename build will need a manual reinstall from
  the releases page instead of a smooth auto-update.

  Review:


## GUI & UX

- background-session-hide-engine-overlay - when the engine runs in a background session it now draws
  no on-screen overlay at all, so that session shows nothing but the Roblox window.

  Notes: needs your RDP Wrapper setup. Start a background session, then press Show to look inside it:
  you should see only Roblox (and the minimal-shell control window if that box is ticked), with no
  gray frame, no Log panel, no Time Breakdown panel and no Application Stats panel. macro_log.txt in
  that session should carry the line "Background Windows session: on-screen overlay skipped." The
  window lock is deliberately kept, so the game window still gets pulled into the opening there. On
  your physical desktop nothing at all should change: the overlay must look exactly as it does today.
  One scope note worth knowing: the condition is "not the physical console session", so if you ever
  run the whole app over an ordinary Remote Desktop connection instead, that run loses the overlay
  too.

  Review:


- map-advanced-reuse-step-editor - "Map Advanced Settings..." now looks and works like the normal
  preset edit UI: a step table with Add Step / Edit Step... / Delete Selected / Duplicate, and
  editing an action opens the SAME Step Editor window the preset editor uses. This supersedes
  map-advanced-sync-step-editor, whose Show buttons were only ever added to the old inline editor
  that this replaces (they are still there, inside the shared editor).

  Notes: Map Placement tab -> "Map Advanced Settings...". The table should list your camera actions
  with their coordinates; reorder by dragging the row NUMBER on the left, not the row body. Double
  click a row (or Edit Step...) to open the Step Editor, which in this mode offers only Drag and
  Zoom Out and hides everything a camera action has no use for (Name, Wait After, the flow and
  fallback rows, Challenge options). Its "Set End Position" button is new and also shows up for a
  normal preset Drag step, where End X/End Y previously could only be typed in by hand. Two things
  worth trying on purpose: closing the Map Advanced window while the Step Editor is still open must
  close the editor too, and toggling "Use custom camera/zoom settings for this map" while it is
  open must also close it, discarding that in-flight edit, because only the currently shown list is
  what Save writes. One deliberate behaviour: older configs can hold action types this editor does
  not offer ("Camera Drag", "Zoom In", "Click"); the table shows them with all their values, but
  opening one and pressing Save rewrites its type to Drag. The engine only ever ran "Drag" and
  "Zoom Out", so those rows were being skipped anyway.

  Review:


- background-session-window-branding - the Remote Desktop window that Show opens now carries this
  app's own name and icon instead of presenting itself as a generic Remote Desktop connection.

  Notes: needs your RDP Wrapper setup. Start a background session, then press Show: the window that
  appears should be titled "Kimberlite's Macro Menu - Background Session" and carry the app icon in
  its title bar and in its taskbar entry. Watch it for the first few seconds, because mstsc rewrites
  its own title and icon while connecting and the app keeps re-asserting them for about 15 seconds;
  the interesting question is whether it still looks right once the connection has settled. Nothing
  about the connection itself should behave differently, and if the branding fails for any reason it
  is meant to fail invisibly, leaving a normally-titled Remote Desktop window rather than an error.
  Two deliberate scope decisions worth knowing: Start's window is launched hidden so there is nothing
  to brand there, and no desktop shortcut was added, since the session is only ever started from the
  buttons inside the app.

  Review:


- map-placement-remove-button - each row of the Map Placement table has a small "X" button at the
  end of the row that removes that placement and drops "Number of placements" by one.

  Notes: it sits in a new last column, past Show rather than directly between Capture and Show, so
  a destructive button is not next to the one you click most. Removing a middle row should pull
  every row below it up by one rather than leave a hole, and the table should shrink by one visible
  row on its own. The whole column only appears while "Use custom tower slots for this map" is
  ticked; with it unticked the table is one column narrower with no dead space on the right. Like
  the Capture button, removing only edits the table: press Save to keep it.

  Review:


## MAJOR

- stats-row2-three-columns - the Application Stats panel's row 2 is back to 3 evenly-spaced columns
  like rows 1 and 3 instead of 4: Screen Repetition Count is gone, and Session Time now sits in its
  place next to Step Repetition Count and Current Step Time.

  Review:


- background-session-engine-lifecycle - closing the GUI no longer stops an engine that runs in a
  different Windows session, so the macro can keep running in a background RDP session while the
  physical desktop is used for something else. First of four steps towards driving that whole setup
  from the app itself.

  Notes: needs your RDP Wrapper setup to test. Start the macro inside the background session, then
  open the GUI on the physical desktop: it should attach to that engine (status and counters live,
  Pause/Resume/Stop working) and show a blue "Background session" label next to the run state.
  Closing the GUI must leave the macro running; check with "query session" or Task Manager that the
  engine is still there. Pressing a capture button (F8 position, Map Placement, a step's region)
  must now fail immediately with "Capture failed: the engine runs in a background session..."
  instead of silently hanging for two minutes. On a normal single-session setup nothing should
  behave differently at all: no label, capture works as before, and closing the GUI still stops the
  engine.

  Review:


- background-session-launcher - a new "Background Session" tab starts, shows and stops the
  background RDP session from inside the app, so no mstsc command has to be typed. Second of four
  steps towards driving that whole setup from the app itself.

  Notes: needs your RDP Wrapper setup. First enter your Windows password once and press "Save
  Credential" (it goes into Windows Credential Manager, never into config.ini or any file the app
  writes). Then press Start with the macro NOT running on this desktop: a session should appear in
  "query session" within a few seconds and immediately go to Disc(onnected), with no window ever
  becoming visible. Press Show to look inside it, then close that window again (closing the mstsc
  window only disconnects, it does not end the session). Press Stop to end it for good. Two
  refusals worth checking on purpose: Start while the macro is running on the physical desktop must
  refuse with a message about two engines sharing one config, and Start with no saved credential
  must refuse and point at Save Credential.

  Review:


- background-session-setup-wizard - a "Setup" box at the top of the Background Session tab checks
  the four things that have to be true before a background session can work and tells you exactly
  what to fix for each one, with Start disabled until all four pass. Third of four steps towards
  driving that whole setup from the app itself.

  Notes: since your machine is already set up, the interesting check is whether it correctly reports
  "ready" rather than a false alarm. The fourth check is the one most likely to be wrong: it reads
  the BINARY version of termsrv.dll and looks for that exact section in your rdpwrap.ini, so compare
  the version it names against the section headers in your own rdpwrap.ini. If you want to see the
  failing side too, the harmless way is to look at the wording only; do not turn Remote Desktop off
  just to test it. Nothing here ever writes to the registry or asks for administrator rights.

  Review:


- background-session-minimal-shell - with "Boot straight into the macro, with no Windows desktop"
  ticked, the background session runs the app as its Windows shell instead of Explorer, so that
  session holds only Roblox and the engine: no desktop, no start menu, less RAM and CPU. Last of
  the four steps.

  Notes: this is the riskiest one to test, because Windows signs a session out the moment its shell
  stops, so try it while you can still get back in. Press Start with the box ticked, then Show: you
  should see a small "Background Session" window with Start Roblox, Start Explorer and Sign out, and
  nothing else, no taskbar and no desktop icons. That window deliberately has no minimize or close
  button, because losing it would leave that session with no way in; "Start Explorer" is the way
  back to a normal desktop, and "Sign out" is the only way to end the session from inside. If you
  have a private server link set under [General] PrivateServerLink in config.ini, Roblox should
  already be opening into it; without one, "Start Roblox" just explains that none is configured (the
  settings field for it comes with the private-server-link task). Untick the box to get the old
  behavior with a normal desktop. The macro itself is still driven from the main window on your
  physical desktop, exactly as before.

  Review:


- private-server-link - a "Private server link" field in the General tab's Disconnect Detection
  group. When it is set, an automatic reconnect rejoins through that private server instead of
  clicking the Reconnect position, and a background session booted straight into the macro opens
  Roblox into it. Empty field means today's behavior in both places.

  Notes: paste your own share link (https://www.roblox.com/share?code=...&type=Server) and press
  Save, then reopen the app and check it is still there. Paste something invalid on purpose too (a
  plain https://www.roblox.com/home, or an http:// link): the save must be refused with a message
  naming the problem, and nothing must be written. Then, with the macro running, let a real
  disconnect happen: it should log "Disconnect detected -> rejoining through the configured private
  server link.", open the link, and restart the preset from its first screen. Check macro_log.txt
  afterwards and confirm the link itself and its code appear nowhere in it. One thing worth knowing
  before testing the background session half: only the "Boot straight into the macro" option opens
  Roblox by itself, since a background session running the normal Windows desktop gives the app no
  way to start anything inside it, so with that box unticked you still start Roblox in there
  yourself.

  Review:
