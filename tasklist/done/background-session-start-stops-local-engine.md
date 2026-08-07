Title:     beim starten steht das hier: The macro engine is running on this desktop right now. Stop it
           first: starting a background session while it runs would leave two engines sharing one config.
Completed: 2026-08-07
Commit:    -

Result: Pressing Start on the Background Session tab now works from a cold state. It could not
before, and this was a genuine deadlock rather than a bad message: main.py spawns an engine in its
own Windows session at startup whenever none is running anywhere (main.py's "if manage_engine and
not engine_running" branch), so simply opening the GUI created the very engine that Start then
refused over. It only ever appeared to work because a hand-made mstsc session already had an engine
running, which made the GUI attach to that one instead of spawning its own; once that leftover
session was logged off, the feature became unreachable.

_start now resolves the engine situation itself before starting anything. Engines in OTHER sessions
are left completely alone and never block, which is the whole point of the feature. Engines in THIS
session are ours to stop, after asking through an injectable confirm callback (a QMessageBox by
default, injected in tests so no modal ever opens). An engine whose session cannot be verified, or
an unreadable own session id while engines exist, still refuses with the original message, failing
closed exactly as before. Deliberately a prompt rather than reading local_status.json's running
flag: that file outlives the engine it describes, so a stale "running: true" would block Start
forever and a stale "running: false" would silently kill a live run.

Five defects found across three review rounds, all fixed rather than accepted:

- The first version refused whenever current_session_id() returned None, even with NO engine
  running, falsely claiming an engine was present. That was a defect in the task's own plan.
- The local engine was stopped BEFORE start_background_session's cheap, non-destructive refusals,
  so a missing credential would stop a running macro and then fail to start anything. Those
  preconditions are now checked first, and because start_background_session checked the engine
  interlock before the credential, the credential refusal was moved above it (both are pure
  precondition refusals with no side effects, so the order is free, and the user is no longer told
  to stop a macro for a Start that would have failed anyway).
- Engine pids were captured before a modal that can sit open indefinitely, so they could belong to
  an unrelated process by the time they were used. The local engines are now re-enumerated after
  confirmation.
- stop_engine_by_pid issued a graceful "taskkill /PID" before anything verified the pid was still
  an engine, so a recycled pid meant asking an unrelated application to close. Fixed centrally,
  since every caller had the same hazard.
- That central fix was first implemented with a tasklist.exe lookup, which conflated "not an
  engine" with "could not tell" and so skipped shutdown on any transient query failure, leaking a
  running engine. Two review rounds then contradicted each other about which way to fail. Resolved
  properly instead of picking a side: the image is now read from the process HANDLE that
  stop_engine_by_pid has already opened (QueryFullProcessImageNameW), which cannot be fooled by pid
  reuse because Windows will not recycle a pid while a handle to it is open, and needs no second
  process spawn. Only a confirmed non-engine skips the stop; a failed read proceeds, since a pinned
  handle rules out drift and leaking an engine is the worse outcome.

Verified with the full gui/ pytest suite (420 passed) and, for the safety property that matters
most, empirically: stop_engine_by_pid was called against a live non-engine process (powershell.exe)
and correctly refused, leaving it running, after reading its image through the handle. Worth
recording, because it nearly produced a false bug report: two earlier attempts at that same test
reported a failure that did not exist, because the dummy process was already dead both times (a
PowerShell argument-list mangling turned "python -c import time; ..." into a syntax error, and
Windows 11's notepad.exe is a stub whose pid exits immediately as it hands off to the Store app).
Always assert the dummy is alive before concluding anything from a kill test. The positive path (an
actual engine IS stopped) is covered by unit tests only, since CLAUDE.md forbids launching the AHK
application to test.
