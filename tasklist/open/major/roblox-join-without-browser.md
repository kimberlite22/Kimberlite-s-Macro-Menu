Title: das autostarten funktioniert noch sehr unpoliert. Finde eine moglichkeit den roblox private
       link anders zu joinen ohne den browser zu oeffnen, oder zumindest einfacher sicherer.
       Nachdem roblox geoeffnet wurde der browser soll automatisch schliessen.

Prio:  2

Goal:  Joining the configured private server no longer leaves a browser window behind. Today
       gui/app/session_shell.py's launch_game() hands the whole https://...roblox.com/share?... link
       to os.startfile, so Windows opens the default browser, the browser hands off to the roblox://
       protocol, and the browser window stays open in the session for the rest of the run. Either
       the link is turned into something that starts the Roblox client directly (a roblox:// deep
       link built from the private server link, so no browser is involved at all), or, if that is not
       possible for every supported link shape, the browser it does open is closed again once Roblox
       has come up. Applies to both places that launch the game: the session shell's "Start Roblox"
       button and the autostart path that runs it unattended.

Open:  Which route is actually available has to be established first, and it decides how much of this
       task there is:
       - Can a roblox:// deep link be built offline from both supported link shapes, the
         ?privateServerLinkCode= form and the newer /share?code=...&type=Server form (see
         gui/app/private_server_link.py)? The share form looks like it needs a Roblox API call to
         resolve the code into a place id plus link code, which would mean the macro suddenly does
         networking; that is a real architecture decision, not an implementation detail.
       - If a browser still has to be opened: which window is safe to close afterwards? Closing "the
         browser" must never close the user's own unrelated browser window, so the fallback has to be
         a process/window started by this app and nothing else, and it has to behave when the default
         browser reuses an already running instance instead of starting a new process.
       - How to tell that Roblox has "come up" (window title, process name, a timeout), since that is
         what triggers the close.
