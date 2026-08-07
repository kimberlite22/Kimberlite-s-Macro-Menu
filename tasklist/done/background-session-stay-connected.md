Title:     Dont immidiately disconnect the session.
Completed: 2026-08-07
Commit:    -

Result: start_background_session gained a keyword-only disconnect_after_start, defaulting to False,
so the session now stays connected. The whole disconnect path is kept behind that flag rather than
deleted: it is still right for a genuinely headless run and it holds the deliberate
confirm-the-disconnect-actually-happened logic. Two consequences had to be handled with it. The
mstsc process is no longer terminated on the success path, since killing the client would tear the
window straight back down, which is the thing this task undoes. And the client is now launched
VISIBLE rather than hidden when the session is going to stay connected, which review caught: a
retained client that cannot be seen is strictly worse than a disconnected session, because it holds
the session and shows nothing. The tab's status line now reports the session's real state from
find_session_by_id instead of the hardcoded "running (disconnected)".

Beyond the user asking for it, staying connected is the better default for a reason worth recording:
a disconnected RDP session has no rendered desktop, so screen capture and OCR inside it can come
back empty, and this macro's entire perception layer is screen based.

Keeping a client attached broke Show, which review also caught: this setup requires
fSingleSessionPerUser=0, so launching a second client while one is connected can create a NEW,
untracked session instead of reconnecting, and Stop would then log off only the recorded one and
strand the other. Refusing Show outright was the first fix and was itself wrong, since a client that
dies, is hidden, or sits on an unreachable desktop would leave the session ACTIVE forever with Stop
(which kills the running macro) as the only escape. Show is now self-healing instead: on an ACTIVE
recorded session it disconnects first, confirms the session actually left the ACTIVE state using the
same bounded confirm-and-poll shape the Start path uses, and only then launches a client, which
therefore reconnects rather than causing a second session. If the release cannot be confirmed it
launches nothing and asks to be tried again, since launching anyway is exactly the rival-session
risk the guard exists for.

Verified with the full gui/ suite (434 passed) and live against real Windows sessions: Start left
session 8 in state 0 (ACTIVE) with mstsc still running, Show against that ACTIVE session released
and reconnected it without creating any second session, and Stop ended it in 3.6s leaving nothing
behind.
