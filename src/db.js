import Database from 'better-sqlite3';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const dir = fileURLToPath(new URL('../data/', import.meta.url));
mkdirSync(dir, { recursive: true });
export const db = new Database(dir + 'bot.db');
db.pragma('journal_mode = WAL');

db.exec(`
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
CREATE TABLE IF NOT EXISTS timers(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, target TEXT, run_at INTEGER);
CREATE TABLE IF NOT EXISTS games(
  tag_id TEXT PRIMARY KEY, name TEXT, board_name TEXT, owner_override TEXT,
  link TEXT, icon_url TEXT, announce_channel_id TEXT, ping_role_id TEXT,
  threshold INTEGER NOT NULL DEFAULT 5, next_offer_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, created_at INTEGER);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS bug_msgs(bug_id INTEGER, channel_id TEXT, message_id TEXT);
CREATE TABLE IF NOT EXISTS dev_prefs(user_id TEXT PRIMARY KEY, ping_bugs INTEGER NOT NULL DEFAULT 1, ping_exploits INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS announcements(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tag_id TEXT, game_name TEXT, posted_at INTEGER, url TEXT, bug_ids TEXT
);
`);

for (const col of ['note TEXT', 'device TEXT', 'body TEXT', 'source TEXT']) {
  try { db.exec(`ALTER TABLE bugs ADD COLUMN ${col}`); } catch { /* already there */ }
}

export const now = () => Date.now();

export const kvGet = (k) => db.prepare('SELECT v FROM kv WHERE k=?').get(k)?.v;
export const kvSet = (k, v) =>
  db.prepare('INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v').run(k, String(v));
export const kvDel = (k) => db.prepare('DELETE FROM kv WHERE k=?').run(k);
export const kvKeys = (prefix) =>
  db.prepare('SELECT k,v FROM kv WHERE k LIKE ?').all(prefix + '%');

export const bugById = (id) => db.prepare('SELECT * FROM bugs WHERE id=?').get(id);
export const bugByThread = (t) => db.prepare('SELECT * FROM bugs WHERE thread_id=?').get(t);
export function updateBug(id, patch) {
  const keys = Object.keys(patch);
  db.prepare(`UPDATE bugs SET ${keys.map((k) => k + '=?').join(',')} WHERE id=?`).run(...keys.map((k) => patch[k]), id);
}

export const addTimer = (kind, target, runAt) =>
  db.prepare('INSERT INTO timers(kind,target,run_at) VALUES(?,?,?)').run(kind, String(target), runAt);
export const cancelTimers = (kind, target) =>
  db.prepare('DELETE FROM timers WHERE kind=? AND target=?').run(kind, String(target));

export const getGame = (tagId) => db.prepare('SELECT * FROM games WHERE tag_id=?').get(tagId);
export function upsertGame(tagId, name, patch = {}) {
  db.prepare('INSERT OR IGNORE INTO games(tag_id,name,threshold) VALUES(?,?,3)').run(tagId, name);
  const keys = Object.keys(patch);
  if (keys.length) {
    db.prepare(`UPDATE games SET ${keys.map((k) => k + '=?').join(',')} WHERE tag_id=?`).run(...keys.map((k) => patch[k]), tagId);
  }
  return getGame(tagId);
}

// Per-dev ping choices: new simple bugs, and exploit reports. Both default to on.
export const getPrefs = (userId) => {
  const r = db.prepare('SELECT * FROM dev_prefs WHERE user_id=?').get(userId);
  return { bugs: r ? !!r.ping_bugs : true, exploits: r ? !!r.ping_exploits : true };
};
export function setPrefs(userId, { bugs, exploits }) {
  db.prepare('INSERT OR IGNORE INTO dev_prefs(user_id) VALUES(?)').run(userId);
  if (bugs !== undefined) db.prepare('UPDATE dev_prefs SET ping_bugs=? WHERE user_id=?').run(bugs ? 1 : 0, userId);
  if (exploits !== undefined) db.prepare('UPDATE dev_prefs SET ping_exploits=? WHERE user_id=?').run(exploits ? 1 : 0, userId);
  return getPrefs(userId);
}

export const createPending = (data) =>
  db.prepare('INSERT INTO pending(data,created_at) VALUES(?,?)').run(JSON.stringify(data), now()).lastInsertRowid;
export const getPending = (id) => {
  const r = db.prepare('SELECT data FROM pending WHERE id=?').get(id);
  return r ? JSON.parse(r.data) : null;
};
export const setPending = (id, data) => db.prepare('UPDATE pending SET data=? WHERE id=?').run(JSON.stringify(data), id);
export const delPending = (id) => db.prepare('DELETE FROM pending WHERE id=?').run(id);
