"""Personal MCP tokens: one active token per dev, stored hashed (the token itself is shown once, in /mcp setup), with a rate limit per dev."""
import hashlib
import secrets
import time
from collections import defaultdict, deque

from bot.core.db import db, now, one, run

db.execute("""CREATE TABLE IF NOT EXISTS mcp_tokens(
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at INTEGER NOT NULL, last_used INTEGER, revoked INTEGER NOT NULL DEFAULT 0)""")

PER_MINUTE = 60
_calls = defaultdict(deque)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue(user_id):
    """A new token for this dev; the old one stops working. Returns the token (the only time it is readable)."""
    run('UPDATE mcp_tokens SET revoked=1 WHERE user_id=?', str(user_id))
    token = 'cdl_' + secrets.token_urlsafe(32)
    run('INSERT INTO mcp_tokens(token_hash,user_id,created_at) VALUES(?,?,?)', _hash(token), str(user_id), now())
    return token


def revoke(user_id):
    """True when the dev had an active token."""
    return run('UPDATE mcp_tokens SET revoked=1 WHERE user_id=? AND revoked=0', str(user_id)).rowcount > 0


def verify(token):
    """The dev's user id for a valid token, else None."""
    if not token or not token.startswith('cdl_'):
        return None
    row = one('SELECT user_id FROM mcp_tokens WHERE token_hash=? AND revoked=0', _hash(token))
    if not row:
        return None
    run('UPDATE mcp_tokens SET last_used=? WHERE token_hash=?', now(), _hash(token))
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
