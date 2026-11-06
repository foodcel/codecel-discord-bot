"""Personal MCP tokens: one active token per dev, stored hashed (the token itself is shown once, in /mcp setup), with a rate limit per dev."""
import hashlib
import secrets
import time
from collections import defaultdict, deque

from bot.core.db import db, now, one, run

db.execute("""CREATE TABLE IF NOT EXISTS mcp_tokens(
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at INTEGER NOT NULL, last_used INTEGER, revoked INTEGER NOT NULL DEFAULT 0)""")

for _ddl in ('ALTER TABLE mcp_tokens ADD COLUMN expires_at INTEGER',):
    try:
        db.execute(_ddl)
    except Exception:
        pass
db.execute("CREATE TABLE IF NOT EXISTS mcp_usage(user_id TEXT NOT NULL, day TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, day))")

PER_MINUTE = 60
LIFETIME_DAYS = 30
CONNECTED_MINUTES = 10  # no permanent connection exists: "connected" means it called this recently
_calls = defaultdict(deque)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue(user_id):
    """A new token for this dev; the old one stops working. Returns the token (the only time it is readable)."""
    run('UPDATE mcp_tokens SET revoked=1 WHERE user_id=?', str(user_id))
    token = 'cdl_' + secrets.token_urlsafe(32)
    run('INSERT INTO mcp_tokens(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)', _hash(token), str(user_id), now(), now() + LIFETIME_DAYS * 86400000)
    return token


def revoke(user_id):
    """True when the dev had an active token."""
    return run('UPDATE mcp_tokens SET revoked=1 WHERE user_id=? AND revoked=0', str(user_id)).rowcount > 0


def verify(token):
    """The dev's user id for a valid token, else None."""
    if not token or not token.startswith('cdl_'):
        return None
    row = one('SELECT user_id, expires_at FROM mcp_tokens WHERE token_hash=? AND revoked=0', _hash(token))
    if not row or (row['expires_at'] and row['expires_at'] < now()):
        return None
    run('UPDATE mcp_tokens SET last_used=? WHERE token_hash=?', now(), _hash(token))
    run('INSERT INTO mcp_usage(user_id,day,calls) VALUES(?,?,1) ON CONFLICT(user_id,day) DO UPDATE SET calls=calls+1', row['user_id'], time.strftime('%Y-%m-%d', time.gmtime()))
    return row['user_id']


def limited(user_id):
    """True when this dev made more than PER_MINUTE calls in the last minute."""
    q, t = _calls[str(user_id)], time.monotonic()
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= PER_MINUTE:
        return True
    q.append(t)
    return False


def paused():
    from bot.core.db import kv_get
    return kv_get('mcp_paused') == '1'


def set_paused(on):
    from bot.core.db import kv_set
    kv_set('mcp_paused', '1' if on else '0')


def overview():
    """One row per dev with an active token, for the admin: who, when it was made, when it last called, and how many calls today (a count, never what was asked)."""
    day = time.strftime('%Y-%m-%d', time.gmtime())
    from bot.core.db import all_
    rows = all_('SELECT user_id, created_at, last_used, expires_at FROM mcp_tokens WHERE revoked=0 ORDER BY last_used DESC')
    out = []
    for r in rows:
        u = one('SELECT calls FROM mcp_usage WHERE user_id=? AND day=?', r['user_id'], day)
        out.append({**r, 'today': u['calls'] if u else 0, 'expired': bool(r['expires_at'] and r['expires_at'] < now()),
                    'connected': bool(r['last_used'] and now() - r['last_used'] < CONNECTED_MINUTES * 60000)})
    return out
