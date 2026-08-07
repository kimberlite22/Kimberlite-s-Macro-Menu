Title:     das autostarten funktioniert noch sehr unpoliert. Finde eine moglichkeit den roblox private
           link anders zu joinen ohne den browser zu oeffnen, oder zumindest einfacher sicherer.
           Nachdem roblox geoeffnet wurde der browser soll automatisch schliessen.

Completed: 2026-08-07
Commit:    d6757c7

Result: New gui/app/roblox_launch.py replaces the one-line os.startfile launch. It builds a
roblox:// deep link and starts that, so no browser is opened at all: offline for a
?privateServerLinkCode= link (the place id is in the path, the link code in the query), and through
Roblox' own share-link resolve endpoint for a /share?code=...&type=Server link, which carries
neither. That endpoint is the only network request the macro side makes: one pinned https URL, an
8s timeout, a capped body, and every failure mode falls through rather than being reported, since
the fallback needs no network. The browser is only the fallback, and it is closed again once Roblox
is up. Two rules make that safe: the process closed is the one Windows started FOR THIS LINK, taken
from ShellExecuteExW's own process handle (a shell that routes the link into an already running
browser starts nothing, so nothing is closed, and a user's own window can never be a candidate),
and the handle is held open until the decision is made, because Windows only recycles a pid once the
last handle to it is gone. "Roblox came up" means a process that was NOT running before the launch,
so an already open Roblox cannot read as instant success. The deep link is verified the same way
rather than trusted: a client that ignores it falls back to the browser instead of leaving the
session with nothing. Everything past the validation runs on a daemon thread, since the session
shell has not built its control window yet and the button press is on the Qt GUI thread. If the
handle route cannot be taken at all, the plain shell open is still the floor, so the worst case is
exactly the old behavior. Open question resolved by the user: resolve /share links through the
Roblox API rather than rejecting them.
