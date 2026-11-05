"""Checking and cleaning the links people type. Every link check in the bot goes through here.
A link must be a real http(s) address with a host: no spaces, backslashes, user:password@ or other tricks. A Roblox game link is only accepted on
roblox.com itself and is stored in one clean form, https://www.roblox.com/games/<place id>."""
import re
from urllib.parse import urlsplit

_GAME_PATH = re.compile(r'^/(?:[a-z]{2}(?:-[a-z]{2})?/)?games/(\d+)(?:/|$)', re.I)
_ROBLOX_HOSTS = ('roblox.com', 'www.roblox.com', 'web.roblox.com')


def _split(text):
    t = str(text or '').strip()
    if not t or any(c in t for c in '\\ \t\r\n<>"\''):
        return None
    if not re.match(r'^https?://', t, re.I):
        t = 'https://' + t
    try:
        u = urlsplit(t)
        host = u.hostname
    except ValueError:
        return None
    if u.scheme.lower() not in ('http', 'https') or not host or '.' not in host or u.username or u.password:
        return None
    return u


def web_url(text):
    """An http(s) link with a real host (https:// added when it was left out), or None."""
    u = _split(text)
    return u.geturl() if u else None


def roblox_place(text):
    """The place id in a Roblox game page link, or None."""
    u = _split(text)
    if not u or u.hostname.lower() not in _ROBLOX_HOSTS:
        return None
    m = _GAME_PATH.match(u.path)
    return m[1] if m else None


def roblox_game(text):
    """A Roblox game page link in its clean form, or None."""
    place = roblox_place(text)
    return f'https://www.roblox.com/games/{place}' if place else None


def roblox_any(text):
    """A Roblox game page (clean form) or a ro.blox.com share link (as given, https), or None."""
    game = roblox_game(text)
    if game:
        return game
    u = _split(text)
    return u._replace(scheme='https').geturl() if u and u.hostname.lower() == 'ro.blox.com' else None
