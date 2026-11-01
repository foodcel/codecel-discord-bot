"""Guardrails for /release: how often a dev can release and ping, and a check of the pictures before anything is shown to everyone.
A card with an @everyone ping needs both: a free spot in the limits, and pictures that pass the check."""
import base64
import json
import time
from pathlib import Path

from .ai import moderate_release
from .db import kv_get, kv_set

COOLDOWN_S = 300      # between two /release new of the same dev
CARDS_PER_DEV = 2     # new-game cards (with @everyone) one dev can make in a day
CARDS_PER_DAY = 6     # new-game cards for the whole server in a day
DAY = 86400


def _log():
    try:
        return [e for e in json.loads(kv_get('release_log') or '[]') if time.time() - e[0] < DAY]
    except Exception:
        return []


def cooldown_left(user_id):
    """Seconds this dev still has to wait before the next /release new (0 = go ahead)."""
    last = max([e[0] for e in _log() if e[1] == str(user_id) and e[2] == 'release'] or [0])
    return max(0, int(COOLDOWN_S - (time.time() - last)))


def note(user_id, what):
    kv_set('release_log', json.dumps(_log() + [[time.time(), str(user_id), what]]))


def card_limit_reason(user_id, admin):
    """None when a new-game card (with the @everyone ping) may be posted now, else the reason it may not."""
    cards = [e for e in _log() if e[2] == 'card']
    if len(cards) >= CARDS_PER_DAY:
        return f'the server already had {CARDS_PER_DAY} new-game pings today'
    if not admin and len([e for e in cards if e[1] == str(user_id)]) >= CARDS_PER_DEV:
        return f'you already made {CARDS_PER_DEV} new-game pings today'
    return None


async def check_release(urls, texts, file_path=None):
    """Looks at the pictures and words that would be shown to everyone. {'ok': looked fine or not, 'flagged': bool, 'reason': str}.
    ok False = it could not look (treated as not allowed by the caller)."""
    images = [{'type': 'image', 'source': {'type': 'url', 'url': u}} for u in dict.fromkeys(urls or []) if u][:4]
    if file_path and Path(file_path).exists():
        ext = Path(file_path).suffix.lower().lstrip('.')
        media = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp'}.get(ext, 'image/png')
        images.append({'type': 'image', 'source': {'type': 'base64', 'media_type': media, 'data': base64.b64encode(Path(file_path).read_bytes()).decode()}})
    try:
        out = await moderate_release([t for t in texts if t], images)
        return {'ok': True, 'flagged': bool(out.get('flagged')), 'reason': str(out.get('reason') or 'something not allowed')[:120]}
    except Exception as e:
        print('release check', repr(e))
        return {'ok': False, 'flagged': False, 'reason': 'could not check'}
