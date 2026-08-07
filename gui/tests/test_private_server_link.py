from __future__ import annotations

import pytest

from app.private_server_link import validation_error


@pytest.mark.parametrize("link", [
    "",
    "   ",
    "https://www.roblox.com/share?code=abc&type=Server",
    "https://web.roblox.com/games/1?privateServerLinkCode=abc",
])
def test_accepts_empty_and_supported_private_server_links(link: str) -> None:
    assert validation_error(link) is None


@pytest.mark.parametrize("link", [
    "http://www.roblox.com/share?code=abc&type=Server",
    "file:///C:/Windows/System32/calc.exe",
    "roblox://placeId=1",
])
def test_rejects_non_https_schemes(link: str) -> None:
    assert validation_error(link) == "Private server links must use the https scheme."


@pytest.mark.parametrize("link", [
    "https://roblox.com.evil.example/share?code=abc&type=Server",
    "https://notroblox.com/share?code=abc&type=Server",
])
def test_rejects_hosts_outside_roblox(link: str) -> None:
    assert validation_error(link) == "Private server links must use a roblox.com host."


def test_rejects_a_roblox_url_that_is_not_a_private_server_or_share_link() -> None:
    assert validation_error("https://www.roblox.com/games/1") == (
        "This does not look like a private server or share link."
    )
