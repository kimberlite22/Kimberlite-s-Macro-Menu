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


## WORKFLOW

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


- map-advanced-sync-step-editor - the step editor inside "Map Advanced Settings..." now has a
  "Show" button next to the start coordinates and one next to the end coordinates, the same
  point-preview button every other coordinate field in the app already had.

  Notes: Map Placement tab -> "Map Advanced Settings..." -> select or add a Drag action. Each Show
  should flash the crosshair on the game window at exactly the point the X/Y fields next to it
  currently hold, including uncommitted edits you have typed but not added/updated yet. For a Zoom
  Out action both buttons must disappear together with the capture buttons, since its X is a wheel
  tick count and not a coordinate.

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
