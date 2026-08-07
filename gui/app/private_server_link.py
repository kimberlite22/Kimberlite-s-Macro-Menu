"""Validate private server links before they reach a process launcher.

This lives outside the GUI because ``session_shell.launch_game`` passes its argument straight to
``os.startfile``. A value that reaches that boundary must be validated rather than trusted for
having come from config.ini.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse


def validation_error(link: str) -> str | None:
    """Return a user-facing error, or ``None`` when ``link`` is a supported Roblox link."""
    link = link.strip()
    if not link:
        return None

    try:
        parsed = urlparse(link)
        host = parsed.hostname
    except ValueError:
        return "Private server links must be valid https URLs."

    if parsed.scheme.casefold() != "https":
        return "Private server links must use the https scheme."
    if host is None or not _is_roblox_host(host):
        return "Private server links must use a roblox.com host."

    query = parse_qs(parsed.query, keep_blank_values=True)
    is_share_link = (
        parsed.path == "/share"
        and bool(query.get("code", [""])[0])
        and query.get("type", [""])[0] == "Server"
    )
    is_private_server_link = bool(query.get("privateServerLinkCode", [""])[0])
    if not (is_share_link or is_private_server_link):
        return "This does not look like a private server or share link."
    return None


def _is_roblox_host(host: str) -> bool:
    """Match roblox.com only at a DNS label boundary."""
    host = host.casefold()
    return host == "roblox.com" or host.endswith(".roblox.com")
