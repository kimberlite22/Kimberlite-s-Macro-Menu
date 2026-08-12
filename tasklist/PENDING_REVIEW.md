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

- background-session-hide-window - a Hide button that minimizes the background session's window
  while its screen keeps running, plus a status line that says when minimizing would stop detection
  instead of leaving you to find out by watching it stop.

  Notes: this is the answer to "detections only work while the picture is visible". I checked your
  machine first: the client setting was absent, so Windows was pausing the session's screen exactly
  as you described, and the engine plus both OCR helpers really are in session 8, the background
  session. So the picture being on screen was never about WHERE the screenshots come from, only
  about whether Windows was still drawing that screen.

  How to test it: press Hide. If the setting was not in place yet, Hide reconnects the window first
  (a Remote Desktop client only picks that setting up when it connects, so minimizing the client you
  have open right now would have changed nothing), then minimizes it. Then watch whether detection
  keeps going with the window minimized: macro_log.txt in the session, or the Live Stats tab. Also
  worth trying with the option unticked: Hide still works, but it should tell you outright that
  detection stops until you show the window again. And with the option ticked but the setting
  failing to write, Hide should refuse and point you at Disconnect rather than minimizing anyway.

  Still open, and only your test can settle it: whether a window that is merely COVERED by another
  window (not minimized) also pauses the session. Windows documents the pause for minimizing only,
  so it should be fine, but you are the one who can check it.

  Review:


- background-session-capture - the background session keeps its screen running while its window is
  minimized, and capturing a position from this desktop now happens inside that session instead of
  being refused.

  Notes: your guess was half right. The screenshots were always taken inside the background session
  (the OCR helper is a child of the engine, which runs there), but Windows PAUSES a Remote Desktop
  session's rendering while its window is minimized, so the helper was reading a frozen or black
  picture. The Background Session tab has a new ticked-by-default option, "Keep the session's screen
  running while minimized", which writes the Windows client setting that switches that pause off. It
  is applied when you press Start or Show, and only a client that CONNECTS afterwards picks it up:
  so for the session you have running right now, press Show (or Stop and Start) once, then minimize
  and check that detection keeps going in macro_log.txt. Note it applies to every Remote Desktop
  connection this Windows account makes, not just this one. A fully disconnected session still has
  no rendered desktop at all; that part no setting can fix.

  The second half: with the engine in the background session, pressing a capture button here used to
  say "capture inside that session". Now it brings that session's window to the front (reconnecting
  it if it was disconnected) and you pick the point inside that window with F8, exactly as before but
  without switching sessions by hand. Maximize the window before picking a point, since a scaled-down
  session picture makes the click coarser. Worth testing on purpose: capture from the step editor,
  from Map Placement, and a region capture in a Logic step.

  Also new: if a background session is running while a macro engine is ALSO running on this desktop,
  the tab's status line now says so outright, because that is the configuration in which detection
  really does read the wrong desktop.

  Review:


- background-session-disconnect-button - a Disconnect button next to Show, and Show works again.
  Disconnect closes the session's window on this desktop without ending the session, so everything
  in it keeps running.

  Notes: the reason Show did nothing was real and provable, not a guess. The app remembers the
  background session by its Windows session id, and your reboot this morning renumbered them: the
  recorded file said session 6 while the live one was session 3, so Show, Stop and the status line
  all reported "not running" while Roblox and the engine were plainly working in there. The app now
  also finds the session by evidence (a session that is not this one, signed in as exactly this
  account, with a macro engine running in it), so a reboot or a hand-made connection no longer puts
  it out of reach. Worth checking on purpose: Stop must still end the right session, and the status
  line should read "running (active)" or "running (disconnected)" rather than "not running".

  The reason you asked for it is the open question. Press Disconnect and then watch whether the
  macro KEEPS DETECTING: a disconnected RDP session has no rendered desktop, so screen capture in it
  may come back empty and the macro would sit blind. Check macro_log.txt in that session afterwards
  for detections that stopped at the moment you disconnected. If it does go blind, disconnecting is
  not a usable way to free the GPU while you play, and the answer moves to capping Roblox's frame
  rate inside the session instead. Either way the button is what settles it.

  Review:


- test-ocr-escalation-report - the Test OCR buttons say outright whether the expected text was
  detected, and name the framing that found it: no border at all, or a black/white border of N%
  per side, with its position in the ladder. A failure says how far the ladder actually got.

  Notes: this also fixes why the previous version always said "(no detection)" no matter what the
  ladder found: the engine's acknowledgement writer only serialized a fixed list of field names,
  and the stage field was not on it, so the result never reached the window. Worth trying on three
  kinds of region: one that reads fine unpadded (expect "framing 1 of 7", no border added), one
  that only works padded (expect a black or white border of 10/25/50%), and one with deliberately
  wrong expected text (expect NOT DETECTED plus the text it did read, which is the useful part for
  fixing a typo). On a large region you may see "Only N of 7 framings were tried", which means the
  wider borders would exceed the 750 px scan limit, not that they failed.

  Review:


- ocr-padding-escalation - the 2x upscale applied to every image before OCR is gone, and a
  detection that reads nothing or does not match now retries the same region with a border added
  around it, in stages: raw first, then a black and a white border at +10%, +25% and +50% per side,
  stopping at the first stage that matches. A stage whose padded image would exceed 750x750 ends
  the ladder. The Test OCR buttons now report which stage produced the hit.

  Notes: two things worth checking specifically. First, whether detections that were unreliable
  since the upscale existed are reliable again, since that is the actual point of removing it.
  Second, press Test OCR on a region that used to return nothing: the result line tells you
  whether the escalation is doing anything for that region or whether the raw scan was already
  enough. (Its wording was fixed afterwards by test-ocr-escalation-report below, which is the entry
  to judge that part on.) Note the disconnect watchdog also runs the full ladder now, so a normal no-disconnect
  tick costs about 7 scans instead of 1 (roughly 175ms, at most once a second, by default once
  every five). If that shows up as a slowdown, say so and it gets dialed back to a single scan.

  Review:


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


- orphaned-helper-processes - closing the app now takes its OCR helper processes with it.
  ocr_server.exe could survive an app close indefinitely (you found four of them, two 4+ hours old
  from the pre-rename install folder), because the engine had no exit handling at all: StopOcrServer()
  existed but nothing ever called it.

  Notes: the four orphans you already have will not disappear on their own, this only stops NEW ones,
  so end them once (or reboot) before testing or you will keep seeing the old ones. Then: open the
  app, let it run a preset far enough that a detection step happens (that is what starts
  ocr_server.exe), close the app, and check Task Manager / Details for ocr_server.exe. There should
  be none left. Worth doing twice, once by closing the window normally and once by ending
  Kimberlites-Macro-Menu.exe from Task Manager, since those are two different code paths and the
  second one is the harsher test. Also confirm the app itself still closes as quickly as it did
  after the last shutdown fix; the new cleanup is capped at roughly 1.6 seconds but normally takes
  about half a second.

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
  v0.4.16-dev3 to test it with. dev3 replaces dev2 (which replaced dev1): same comparison, but
  built from current main, so it also carries every change merged since v0.4.16 instead of only
  the two-day-old state dev2 was cut from. Install that release's Kimberlites-Macro-Menu.exe (it
  installs over the normal one and keeps your config and presets), unzip ocr-benchmark-win64.zip
  from the same release page and move the ocr_benchmark folder it contains into your install
  directory (%LOCALAPPDATA%\Programs\Kimberlite's Macro Menu\ocr_benchmark\ocr_benchmark.exe) - a
  one-time step. From then on just run the app and press Start like normal; it starts the benchmark
  helper in the background automatically, no extra window to keep open. Play normally for about ten
  hours, then send back ocr_benchmark_log.jsonl from %LOCALAPPDATA%\Kimberlite's Macro Menu. The
  macro still acts only on the current Windows OCR result, the three other engines are only scored.
  Nothing auto-updates into this build: it is a pre-release, so the normal releases page and the
  in-app updater keep pointing at the real v0.4.16.

  Notes: two things changed since the dev2 instructions. The title bar now reads
  "Kimberlite's Macro Menu v0.4.16 (experimental v0.4.16-dev3)" so you can see at a glance that you
  are running the test build and not production (both report the same version number on purpose).
  And closing the app now stops ocr_benchmark.exe and the OCR helper, so the old "check Task Manager
  for leftovers" caveat is gone - worth confirming in Task Manager after your first session.

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

- map-placement-run-camera-action - the Map Placement tab has a new "Run Camera Action" button that
  runs the selected map profile's camera actions once, so a drag or zoom can be tried out without
  starting a whole run.

  Notes: it runs what is SAVED, so press Save first if you just edited the actions or the "Use custom
  camera actions for this map" checkbox. It brings the game window to the front by itself, then
  performs exactly the actions a real run would for that map (the map's own when the checkbox is
  ticked, the shared default ones otherwise). Worth checking the rejection messages too: with the
  macro running it should refuse with "Not while the macro is running.", and for a map with no
  actions configured it should say so instead of appearing to do nothing. Pressing F10 while a
  camera action is still running is refused on purpose ("A camera action is still running - try
  again in a moment."), since the drag holds the right mouse button down.

  Review:


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


- background-session-no-desktop-checkbox - the Background Session tab's "Enable no-desktop mode" /
  "Restore the Windows default" button is a checkbox now, and the administrator confirmation window
  comes when you press Start instead of the moment you click.

  Notes: tick the box and press Start: the UAC prompt should come first, then the session starts in
  the no-desktop mode without you having to press Start a second time. Press Start again with the
  box unchanged and there should be NO prompt at all, since the machine already matches it. Decline
  the prompt once on purpose: the session should still start (with a normal desktop) and the result
  box should say the prompt was declined above the session's own message, with the box staying
  ticked so the next Start retries. Unticking the box and pressing Start is the way back and should
  prompt once more.

  Review:


- window-title-duplicate-app-name - the window title bar no longer repeats the app name; every
  window now shows exactly the title it sets.

  Notes: this is only visible in a build that contains the change, so run current main from
  source or wait for the next release; an already-installed exe keeps the old title. The main
  window's title should read "Kimberlite's Macro Menu v0.4.x (local build)" (or "(source)") with
  the app name once, not twice. Worth a look at the secondary windows too, since they were also
  getting the app name appended: Edit Preset should now say just "Edit Preset: <name>", and the
  background session's window just "Kimberlite's Macro Menu - Background Session". The taskbar
  icon, its grouping and Alt-Tab must be unchanged.

  Review:


## MAJOR

- roblox-fullscreen-opening - a "Use the whole screen" checkbox in General / Game Window makes the
  opening the entire screen and takes the game window's title bar off, so Roblox really fills it.

  Notes: tick it and press Pin (F7). The window should snap to the full screen with no title bar and
  no grey bars around it. The important thing to check is that your saved positions still hit: the
  old opening and your screen are both 16:9, so every stored percentage should land in the same
  place, but run a preset once and watch a few clicks before trusting it. Then untick the box: the
  title bar should come back on its own, both while a macro is running and while only pinned. Worth
  provoking once: with the box ticked and the window borderless, end Kimberlites-Macro-Menu.exe from
  Task Manager instead of closing it, then start the app again. The title bar should come back on
  the next start, since that recovery is written to disk rather than kept in memory. The four
  Opening values grey out while the box is ticked and keep their numbers, so unticking gives you
  back exactly the opening you had.

  Review:


- roblox-join-without-browser + roblox-share-link-deep-link - the private server is joined through a
  roblox:// link now, so no browser window is opened at all. One entry for both, since the first one
  did not work for your kind of link and the second is what fixed it.

  Notes: your /share?code=...&type=Server link is turned into
  roblox://navigation/share_links?code=...&type=Server, which you already confirmed by hand opens
  Roblox and joins the server. What is left to check is the same thing inside the background
  session: start it and watch that Roblox comes up with NO browser window at all, not even briefly.
  session_shell_log.txt in the app's data folder should say "Roblox started without a browser."; any
  other line there means it fell back. Worth one check with your own browser already open on the
  physical desktop: it must stay untouched, since only a browser this launch itself started is ever
  closed. Roblox has to have been signed in once on this Windows profile, which is shared between
  both sessions.

  Review:


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


- session-roblox-stays-fullscreen - in a background session Roblox now comes up full screen by
  itself and the macro stops moving or resizing it there. The session writes Roblox' own Fullscreen
  setting before starting it, and the engine leaves the window's size and position alone as long as
  it measures the window already filling the screen.

  Notes: two things worth knowing before testing. First, this only takes effect with "Use the whole
  screen" ticked in General / Game Window: with it off, the opening is a smaller rectangle the
  engine still has to position the window into, so nothing changes there on purpose. Second, it
  changes a setting that belongs to Roblox and is shared with your physical desktop, so the next
  time you open Roblox on your own desktop it will also come up full screen; F11 puts that back,
  and Roblox remembers that until the next background session runs. To test, start a background
  session and press Show: Roblox should already be full screen when the picture appears, with no
  visible resize afterwards, and macro_log.txt should say "Game window activated; its size and
  position are left to the game". If it instead says "Game window is not filling the screen, so it
  was positioned as usual", that is the deliberate fallback, and session_shell_log.txt in the same
  folder says why the fullscreen setting could not be written.

  Review:


- live-stats-tab - a new "Live Stats" tab in the app window, holding everything the on-screen
  overlay used to show around the game: Application Stats with its Copy button, the per-screen
  Screen Time table, and the live log.

  Notes: those panels only vanished because the full-screen opening leaves no grey area to draw
  them in, so with "Use the whole screen" ticked this tab is now the only place the numbers exist.
  Open it BEFORE starting anything: Session Time must read 0:00, not your PC's uptime, and Current
  Screen / Current Step / Current Step Time must all show "-". Then run a preset and watch the
  Screen Time table fill in, one row per screen of the running preset, screens not reached yet
  included at 0:00. Press Stop and check the numbers FREEZE rather than carrying on counting. Copy
  puts the same ten lines on the clipboard the old overlay button did. In the log panel, scroll up
  while the macro is still logging: your position should hold, instead of being dragged to the
  bottom or thrown to the top. If you want to compare against the old on-screen panels, untick "Use
  the whole screen": they are still there for that case and should agree with the tab.

  Review:


- ocr-match-scoring - OCR expected-text matching now scores how well a read matches instead of
  answering yes or no, the rule moved into one file (macro/ocr_matching.ahk) instead of five
  copies, every detection logs its score, and two new buttons next to Test OCR save a sample
  screenshot of the region under its expected text.

  Notes: this touches how the macro sees the screen, so the thing to watch is your EXISTING presets
  still detecting exactly as before. Nothing that matched previously can stop matching (the old
  rule is kept as a fallback), but things that used to fail can now succeed: an expected text split
  over two lines, a single misread letter (VICT0RY for VICTORY), a dropped space. Run a normal
  session and read the log: every detection line now ends with a score, for example "detected
  (score 0.93)" or "not detected (best 'Victory' 0.61 < 0.75)". If you see "legacy fallback" in a
  line, that detection only matched through the old rule, which is worth telling me about because
  it means the score threshold is too strict for that text. The threshold lives in config.ini as
  [General] OcrMatchThreshold (default 0.75) and has no GUI field yet, on purpose. For the samples:
  open a detection step, press Save Sample, and check <install folder>\ocr_samples for a PNG named
  after the expected text; a second detection using the SAME expected text should be pointing at
  that same file (Choose Sample... opens the folder so you can see it). The two buttons are
  deliberately hidden on Detect Map steps and on Advanced Detection, because there the expected
  text lives on the map profiles and on the outcomes, not in the step's Name field.

  Review:


- test-ocr-map-candidates - Test OCR on a "Detect Map" step now tests the map profiles (and on an
  Advanced Detection, its outcomes) instead of the step's Name field, and names which one matched.
  Map detection itself also picks up map profiles added while the app is running, which it did not
  before.

  Notes: the second half is the one worth testing hard, because it was silently broken. Add a NEW
  map profile with an expected text while the app is running, do NOT restart it, and run a preset
  with a Detect Map step: it should now be able to detect that new map. Before this it could not,
  the engine only knew the profiles that existed when it started. For the button: open a Detect Map
  step and press Test OCR while the map banner is on screen. It should say something like
  'DETECTED: map profile "Kings Tomb" matched from the raw capture ... (score 1.00, needs 0.75)'
  instead of the old "No expected text set". On a miss it names the closest profile and its score,
  which is what tells you which profile's expected text to fix. Same for an Advanced Detection
  step, where it counts your outcomes ("none of the 3 outcomes matched"). If no map profile has an
  expected text set yet it says so outright rather than reporting a failed detection.

  Review:


- map-detect-repeat-pacing - a Detect Map step that cannot possibly succeed (no region set, or no
  map profile with an expected text) now warns and waits instead of retrying instantly, and no
  repeating step can spin faster than once a second.

  Notes: the True/False branching itself was already fine and is unchanged, so normal presets
  should behave exactly as before. What to check is the broken case, which I made worse in the
  previous change: take a Detect Map step, set its On False to "(Repeat)", and either clear its
  region or make sure no map profile has an expected text. Start the macro. The log should show one
  warning plus a counting-down "waiting" line and retry every few seconds; before this it would
  hammer the log as fast as it could. Escape and Stop must still take effect immediately during
  that wait, that is the thing most worth trying. Then put the region and an expected text back and
  confirm a normal run is unchanged in speed.

  Review:
