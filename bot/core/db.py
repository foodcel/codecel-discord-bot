"""SQLite storage. The tables are identical to the JavaScript version, so an existing data/bot.db works unchanged."""
import re
import json
import sqlite3
import time

from bot.core.env import ROOT

DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


# isolation_level=None: every statement commits at once, like better-sqlite3
db = sqlite3.connect(str(DATA_DIR / 'bot.db'), isolation_level=None, check_same_thread=False)
db.row_factory = _dict_factory
db.execute('PRAGMA journal_mode = WAL')

db.executescript("""
CREATE TABLE IF NOT EXISTS bugs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT UNIQUE NOT NULL,
  reporter_id TEXT NOT NULL,
  game_tag_id TEXT, game_name TEXT,
  title TEXT, summary TEXT, severity TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  routed INTEGER NOT NULL DEFAULT 0,
  asks INTEGER NOT NULL DEFAULT 0,
  last_msg_id TEXT,
  created_at INTEGER, fixed_at INTEGER, fixed_by TEXT,
  announced INTEGER NOT NULL DEFAULT 0,
  dup_of INTEGER,
  deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS strikes(user_id TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, updated_at INTEGER);
CREATE TABLE IF NOT EXISTS strike_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, step TEXT, reason TEXT,
  bug_id INTEGER, at INTEGER, state TEXT
);
CREATE TABLE IF NOT EXISTS timers(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, target TEXT, run_at INTEGER, tries INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS games(
  tag_id TEXT PRIMARY KEY, name TEXT, board_name TEXT, owner_override TEXT,
  link TEXT, icon_url TEXT, announce_channel_id TEXT, ping_role_id TEXT,
  threshold INTEGER NOT NULL DEFAULT 5, next_offer_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, created_at INTEGER);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS bug_msgs(bug_id INTEGER, channel_id TEXT, message_id TEXT);
CREATE TABLE IF NOT EXISTS game_names(key TEXT PRIMARY KEY, raw TEXT, clean TEXT NOT NULL, manual INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS game_status(
  key TEXT PRIMARY KEY, name TEXT, owners TEXT, since TEXT, status TEXT NOT NULL DEFAULT 'unreleased',
  released_at INTEGER, released_by TEXT, link TEXT
);
CREATE TABLE IF NOT EXISTS board_posts(  -- the suggestions forum's posts as last synced
  post_id TEXT PRIMARY KEY, title TEXT NOT NULL, votes INTEGER NOT NULL DEFAULT 0, excluded INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS board_claims(  -- a claimed game: a forum post (post_id) or a custom game (game)
  id INTEGER PRIMARY KEY AUTOINCREMENT, post_id TEXT, game TEXT, user_id TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS board_claim_post ON board_claims(post_id) WHERE post_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS board_claim_game ON board_claims(game COLLATE NOCASE) WHERE post_id IS NULL;
CREATE TABLE IF NOT EXISTS game_testers(  -- who volunteered to test which game in testing
  game_key TEXT NOT NULL, user_id TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY(game_key, user_id)
);
CREATE TABLE IF NOT EXISTS testers(  -- the tester roster
  user_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending', only_for TEXT,
  devices TEXT, recording TEXT, availability TEXT, best_for TEXT, added_at INTEGER
);
CREATE TABLE IF NOT EXISTS dev_prefs(user_id TEXT PRIMARY KEY, ping_bugs INTEGER NOT NULL DEFAULT 1, ping_exploits INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS announcements(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tag_id TEXT, game_name TEXT, posted_at INTEGER, url TEXT, bug_ids TEXT
);
""")

for _col in ("kind TEXT NOT NULL DEFAULT 'bug'", 'votes INTEGER NOT NULL DEFAULT 0', 'low_info INTEGER NOT NULL DEFAULT 0'):  # 'bug' or 'suggestion'; the vote emoji count
    try:
        db.execute(f'ALTER TABLE bugs ADD COLUMN {_col}')
    except Exception:
        pass

try:  # a fixed bug's reporter is told when the update with the fix is released (notified = they were told)
    db.execute('ALTER TABLE bugs ADD COLUMN notified INTEGER NOT NULL DEFAULT 0')
    db.execute("UPDATE bugs SET notified=1 WHERE status='fixed'")  # fixed before this existed: they were told at once
except Exception:
    pass

for _col in ('num INTEGER', 'num_scope TEXT'):  # the number people see (#3) and the game it counts in: stored, so it never shifts
    try:
        db.execute(f'ALTER TABLE bugs ADD COLUMN {_col}')
    except sqlite3.OperationalError:
        pass

try:  # timers that failed are tried again
    db.execute('ALTER TABLE timers ADD COLUMN tries INTEGER NOT NULL DEFAULT 0')
except sqlite3.OperationalError:
    pass

for _col in ('saved_by TEXT',):  # bug hunting: who replied !bug / !suggest
    try:
        db.execute(f'ALTER TABLE bugs ADD COLUMN {_col}')
    except Exception:
        pass

for _col in ('message_id TEXT', 'channel_id TEXT', 'payload TEXT', 'merged_at INTEGER'):  # where an announcement was posted, and its lines (to add to it later)
    try:
        db.execute(f'ALTER TABLE announcements ADD COLUMN {_col}')
    except Exception:
        pass

for _col in ('title TEXT', 'place_id TEXT', 'roblox_name TEXT', 'creator TEXT', 'hero_url TEXT', 'hero_file TEXT', 'studio TEXT', 'original_name TEXT', 'icon_url TEXT', 'art_url TEXT', 'art_hero_url TEXT', 'card_at INTEGER', 'online INTEGER', 'notes TEXT', 'testing_at INTEGER'):  # /release new: what Roblox and the dev say about a released game
    try:
        db.execute(f'ALTER TABLE game_status ADD COLUMN {_col}')
    except Exception:
        pass

for _col in ('source_link TEXT', 'progress INTEGER', 'working INTEGER', 'test_link TEXT', 'test_note TEXT'):  # link of the original game; % done; being worked on now
    try:
        db.execute(f'ALTER TABLE game_status ADD COLUMN {_col}')
    except Exception:
        pass

for _col in ('mcp_mode TEXT', 'mcp_count INTEGER', 'merge_hours INTEGER', 'agent_ping INTEGER'):  # update settings: when the agent posts (mode, count), the merge window in hours (0 = off), whether the agent may ping
    try:
        db.execute(f'ALTER TABLE games ADD COLUMN {_col}')
    except Exception:
        pass

for _col in ('note TEXT', 'device TEXT', 'body TEXT', 'source TEXT'):
    try:
        db.execute(f'ALTER TABLE bugs ADD COLUMN {_col}')
    except sqlite3.OperationalError:
        pass  # already there


def now() -> int:
    """Milliseconds since the epoch, like JavaScript's Date.now()."""
    return int(time.time() * 1000)


def one(sql, *params):
    """First row as a dict, or None."""
    return db.execute(sql, params).fetchone()


def all_(sql, *params):
    return db.execute(sql, params).fetchall()


def run(sql, *params):
    """Runs a write. Returns the cursor (lastrowid, rowcount)."""
    return db.execute(sql, params)


# ---- key / value ----
def kv_get(k):
    r = one('SELECT v FROM kv WHERE k=?', k)
    return r['v'] if r else None


def kv_set(k, v):
    run('INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v', k, str(v))


def kv_del(k):
    run('DELETE FROM kv WHERE k=?', k)


def kv_keys(prefix):
    return all_('SELECT k,v FROM kv WHERE k LIKE ?', prefix + '%')


# ---- bugs ----
def bug_by_id(id_):
    return one('SELECT * FROM bugs WHERE id=?', id_)


def bug_by_thread(thread_id):
    return one('SELECT * FROM bugs WHERE thread_id=?', str(thread_id))


def update_bug(id_, patch: dict):
    keys = list(patch)
    run(f"UPDATE bugs SET {','.join(k + '=?' for k in keys)} WHERE id=?", *[patch[k] for k in keys], id_)
    if 'game_name' in patch or 'kind' in patch:
        from bot.features.bugs.nums import forget
        forget()  # its number moves with it (the others keep theirs)


def hide_reports(game, kind):
    """A game went back to unreleased (its suggestions go) or lost its dev (its bugs go): hide that game's reports from the boards and the MCP.
    deleted=2 means "removed with the game"; the players' posts are left alone. Returns how many were hidden."""
    want = re.sub(r'[^a-z0-9]', '', str(game or '').lower())
    ids = [b['id'] for b in all_('SELECT id, game_name FROM bugs WHERE kind=? AND deleted=0', kind)
           if want and re.sub(r'[^a-z0-9]', '', (b['game_name'] or '').lower()) == want]
    for n in ids:
        run('UPDATE bugs SET deleted=2 WHERE id=?', n)
    return len(ids)


# ---- timers ----
def add_timer(kind, target, run_at):
    run('INSERT INTO timers(kind,target,run_at) VALUES(?,?,?)', kind, str(target), run_at)


def cancel_timers(kind, target):
    run('DELETE FROM timers WHERE kind=? AND target=?', kind, str(target))


# ---- games (announcement settings per forum tag) ----
def get_game(tag_id):
    return one('SELECT * FROM games WHERE tag_id=?', tag_id)


def upsert_game(tag_id, name, patch: dict | None = None):
    run('INSERT OR IGNORE INTO games(tag_id,name,threshold) VALUES(?,?,3)', tag_id, name)
    patch = patch or {}
    keys = list(patch)
    if keys:
        run(f"UPDATE games SET {','.join(k + '=?' for k in keys)} WHERE tag_id=?", *[patch[k] for k in keys], tag_id)
    return get_game(tag_id)


# ---- per-dev ping choices: new simple bugs, and exploit reports. Both default to on ----
def get_prefs(user_id):
    r = one('SELECT * FROM dev_prefs WHERE user_id=?', user_id)
    return {'bugs': bool(r['ping_bugs']) if r else True, 'exploits': bool(r['ping_exploits']) if r else True}


def set_prefs(user_id, bugs=None, exploits=None):
    run('INSERT OR IGNORE INTO dev_prefs(user_id) VALUES(?)', user_id)
    if bugs is not None:
        run('UPDATE dev_prefs SET ping_bugs=? WHERE user_id=?', 1 if bugs else 0, user_id)
    if exploits is not None:
        run('UPDATE dev_prefs SET ping_exploits=? WHERE user_id=?', 1 if exploits else 0, user_id)
    return get_prefs(user_id)


# ---- announcement drafts waiting for Post / Edit / Later ----
def create_pending(data) -> int:
    return run('INSERT INTO pending(data,created_at) VALUES(?,?)', json.dumps(data), now()).lastrowid


def get_pending(id_):
    r = one('SELECT data FROM pending WHERE id=?', id_)
    return json.loads(r['data']) if r else None


def set_pending(id_, data):
    run('UPDATE pending SET data=? WHERE id=?', json.dumps(data), id_)


def del_pending(id_):
    run('DELETE FROM pending WHERE id=?', id_)
