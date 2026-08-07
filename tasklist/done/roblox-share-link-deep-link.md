Title:     ok udate roblox automatisch joinen geht nicht

Completed: 2026-08-07
Commit:    084d38ab42090cd95ec9e7c1279bd90f42209c9d

Result: Follow-up from roblox-join-without-browser, created and finished in one go once the cause
was proven. The share-link half of that task never worked. It resolved a /share?code=...&type=Server
link through Roblox' sharelinks/v1/resolve-link, and that endpoint is closed to an application: 403
without a CSRF token, 401 with one, because it resolves a code in the context of a signed-in USER.
So the resolve always failed, the launch always fell through to the browser, and the browser landed
on an interstitial page waiting for a click nobody was there to give; the session ended up with a
browser window and no game, which is exactly what the user's session_shell_log.txt showed. The web
redirect for such a link hands back the deep link directly
(roblox://navigation/share_links?code=<code>&type=Server), which is the same code under a different
prefix; confirmed against the live redirect with a fabricated code, which comes back unchanged, so
the server fills a template rather than looking anything up. The conversion is therefore a string
operation, and resolve_share_link, its URL/timeout/size constants, the urllib imports and the
now-unused place-id pattern are gone with it. The client started by the deep link resolves the code
itself as the user signed in to it; that login lives under HKCU\Software\Roblox, per Windows user
rather than per session, so the background session needs nothing carried across to it. The macro
side now makes no network requests at all, and the browser is back to being only a fallback for a
link that cannot be converted. Verified by the user: the deep link opens Roblox and joins the
private server. This reverses the "resolve /share through the Roblox API" answer the user had
originally chosen for roblox-join-without-browser's Open question, which turned out to be
impossible without shipping a login.
