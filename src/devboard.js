import { ActionRowBuilder, ButtonBuilder, ButtonStyle, StringSelectMenuBuilder } from 'discord.js';
import { E, GAP, SEVERITY, STATUS, columns, cut, describe, flat, head, labeled, sentence } from './ui.js';
import { cfg } from './env.js';
import { ctx, fetchChannel, threadLink } from './ctx.js';
import { db, getPrefs, kvGet, kvSet, kvKeys, updateBug } from './db.js';
import { ownersFor, getClaims } from './bounty.js';

// One forum post per dev in #dev-bugs. The first message is the board: a summary, a game picker
// and a transcript button. Bugs are browsed in a private page (see bugview.js), never posted as messages.
const locks = new Map();
const serial = (key, fn) => {
  const p = (locks.get(key) || Promise.resolve()).then(fn).catch((e) => { console.error('devboard', e); return null; });
  locks.set(key, p);
  return p;
};

export function openBugsFor(key) {
  const rows = db.prepare(`SELECT * FROM bugs WHERE routed=1 AND deleted=0 AND status IN ('new','investigating','fixing') ORDER BY id`).all();
  return rows.filter((b) => {
    const owners = ownersFor(b.game_tag_id, b.game_name);
    return key === 'unclaimed' ? owners.length === 0 : owners.includes(key);
  });
}

export function boardEmbed(key) {
  const bugs = openBugsFor(key);
  const e = flat().setTitle(head(key === 'unclaimed' ? E.game : '😊', key === 'unclaimed' ? 'Unclaimed games' : 'Your bug board'))
    .setFooter({ text: 'Pick a game below to browse its bugs. You can also type "12 fixed", "1-5 fixed", "7 investigating" here.' });
  if (!bugs.length) return describe(e, 'No open bugs 🎉');
  const sorted = [...bugs].sort((a, b) => (a.game_name || '').localeCompare(b.game_name || '') || a.id - b.id);
  const n = (s) => bugs.filter((b) => b.status === s).length;
  // "open" = not picked up yet (status New). Investigating and fixing are counted on their own.
  describe(e, `${E.open} **${n('new')}** open${GAP}${E.investigating} **${n('investigating')}** investigating${GAP}${E.fixing} **${n('fixing')}** fixing`);
  const list = sorted.slice(0, 15);
  columns(e, [
    { name: head(E.open, 'Bug'), lines: list.map((b) => `**#${b.id}** ${cut(b.title, 26)}`) },
    { name: head(E.game, 'Game'), lines: list.map((b) => cut(b.game_name || 'Unknown', 18)) },
    { name: head(E.status, 'Status'), lines: list.map((b) => STATUS[b.status] || b.status) },
  ]);
  if (sorted.length > 15) e.addFields({ name: '​', value: `…and ${sorted.length - 15} more. Pick a game below to see them.` });
  return e;
}

// Game picker + transcript button. No picker when there is nothing open.
export function boardComponents(key) {
  const bugs = openBugsFor(key);
  if (!bugs.length) return [];
  const by = new Map();
  for (const b of bugs) {
    const k = b.game_tag_id || 'none';
    const e = by.get(k) || { name: b.game_name || 'Unknown game', n: 0 };
    e.n++;
    by.set(k, e);
  }
  const options = [{ label: `All games (${bugs.length})`, value: 'all' },
    ...[...by].slice(0, 24).map(([k, e]) => ({ label: `${e.name} (${e.n})`.slice(0, 100), value: k }))];
  const menu = (id, placeholder) => new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder().setCustomId(`${id}:${key}`).setPlaceholder(placeholder).addOptions(options));
  return [menu('bd', 'Open a game\'s bugs'), menu('trpick', '📋 Transcript by game')];
}

async function displayName(userId) {
  const m = await ctx.guild.members.fetch(userId).catch(() => null);
  return m?.displayName || userId;
}

async function _devThread(key, create) {
  const id = kvGet('devthread:' + key);
  const t = id ? await fetchChannel(id) : null;
  if (t) {
    if (t.archived) await t.setArchived(false).catch(() => {});
    return t;
  }
  if (!create) return null;
  const forum = await fetchChannel(cfg.devForumId);
  const name = key === 'unclaimed' ? 'Unclaimed games' : `${await displayName(key)} — bugs`;
  const created = await forum.threads.create({
    name: name.slice(0, 100), message: { embeds: [boardEmbed(key)], components: boardComponents(key) },
  });
  kvSet('devthread:' + key, created.id);
  created.pin().catch(() => {});
  return created;
}

export const devThread = (key, create = true) => serial('t:' + key, () => _devThread(key, create));

export async function refreshBoard(key) {
  const t = await devThread(key, openBugsFor(key).length > 0);
  if (!t) return;
  const starter = await t.fetchStarterMessage().catch(() => null);
  await starter?.edit({ embeds: [boardEmbed(key)], components: boardComponents(key) }).catch((e) => console.error('board edit', e.message));
}

const hooks = [];
export const onBoardsRefreshed = (fn) => hooks.push(fn); // lets the fix log refresh with the boards

export async function refreshAllBoards() {
  const keys = new Set(kvKeys('devthread:').map((r) => r.k.slice('devthread:'.length)));
  for (const c of getClaims()) c.owners.forEach((o) => keys.add(o));
  keys.add('unclaimed');
  for (const k of keys) await refreshBoard(k).catch((e) => console.error('refresh', k, e.message));
  for (const fn of hooks) await fn().catch((e) => console.error('board hook', e.message));
}

let boardTimer = null;
export function scheduleBoards() {
  clearTimeout(boardTimer);
  boardTimer = setTimeout(() => refreshAllBoards().catch(console.error), 3000);
}

// New bug: update the boards and ghost-ping the owner (message is deleted right after, the notification stays).
export async function routeBug(bug, { silent = false } = {}) {
  const owners = ownersFor(bug.game_tag_id, bug.game_name);
  const keys = owners.length ? owners : ['unclaimed'];
  updateBug(bug.id, { routed: 1 });
  for (const key of keys) {
    const t = await devThread(key, true);
    if (!t || silent || key === 'unclaimed' || !getPrefs(key).bugs) continue; // devs can turn this ping off with /pings
    const m = await t.send({
      content: `<@${key}> ${E.new} **NEW BUG** · #${bug.id} · ${bug.game_name || 'Unknown game'}`,
      allowedMentions: { users: [key] },
    }).catch((e) => { console.error('ping', e.message); return null; });
    if (m) setTimeout(() => m.delete().catch(() => {}), 2500);
  }
  scheduleBoards();
}

// The card for a possible exploit report. It goes straight into the owner's dev board, not into #mod-log.
const EXP_STATUS = {
  exploit: 'RECEIVED', exploit_investigating: 'INVESTIGATING', exploit_fixed: 'FIXED', exploit_closed: 'CLOSED, NOT AN EXPLOIT',
};
// The line under the title: what happened to the post, and what the reporter was told.
export const exploitStatusLine = (status, silent = false, dmOk = true) =>
  `${E.lock} **${silent ? 'OLD POST, NOT REMOVED' : 'POST REMOVED FROM #BUGS'}**${GAP}${EXP_STATUS[status] || 'RECEIVED'}${dmOk ? '' : `${GAP}COULD NOT DM THE REPORTER`}`;

// Status buttons on the card. Every change also messages the reporter, because their post was deleted.
export function exploitButtons(bugId, status) {
  if (status === 'exploit_fixed' || status === 'exploit_closed') return [];
  const b = (a, label, style) => new ButtonBuilder().setCustomId(`exp:${bugId}:${a}`).setLabel(label).setStyle(style);
  const buttons = [];
  if (status === 'exploit') buttons.push(b('investigating', `${E.investigating} Investigating`, ButtonStyle.Secondary));
  buttons.push(b('fixed', `${E.fixed} Fixed`, ButtonStyle.Success), b('closed', `${E.notbug} Not an exploit`, ButtonStyle.Secondary));
  return [new ActionRowBuilder().addComponents(buttons)];
}

export function exploitCard(bug, text, silent, status = 'exploit', dmOk = true) {
  const e = flat().setTitle(head(E.lock, 'High priority · possible exploit'))
    .setFooter({ text: 'Do not discuss exploit details in public channels.' });
  describe(e, exploitStatusLine(status, silent, dmOk));
  columns(e, [
    { name: head(E.user, 'Reporter'), lines: [`<@${bug.reporter_id}>`] },
    { name: head(E.game, 'Game'), lines: [bug.game_name || 'Unknown'] },
    { name: head(E.severity, 'Severity'), lines: [SEVERITY[bug.severity] || '?'] },
  ]);
  labeled(e, head(E.note, 'Report'), `**${bug.title || 'Untitled'}**\n${bug.summary ? `${sentence(bug.summary)}\n` : ''}>>> ${String(text || '').slice(0, 700)}`);
  return e;
}

// Posts the exploit card at once as a normal message in the dev board post of every owner (or Unclaimed).
// Owners are pinged unless they turned exploit pings off. Unclaimed pings the dev role. Old posts imported silently never ping.
export async function postExploit(bug, text, silent, dmOk = true) {
  const owners = ownersFor(bug.game_tag_id, bug.game_name);
  const keys = owners.length ? owners : ['unclaimed'];
  const card = exploitCard(bug, text, silent, 'exploit', dmOk);
  const rows = silent ? [] : exploitButtons(bug.id, 'exploit');
  for (const key of keys) {
    const t = await devThread(key, true);
    if (!t) continue;
    const ping = silent ? null : key === 'unclaimed' ? `<@&${cfg.devRole}>` : (getPrefs(key).exploits ? `<@${key}>` : null);
    await t.send({
      content: `${ping ? `${ping} ` : ''}${E.lock} **HIGH PRIORITY**`, embeds: [card], components: rows,
      allowedMentions: { users: ping && key !== 'unclaimed' ? [key] : [], roles: ping && key === 'unclaimed' ? [cfg.devRole] : [] },
    }).catch((e) => console.error('exploit post', e.message));
  }
}

// One-time cleanup: removes the per-bug messages the bot used to post (keeps the board message and dev chat).
export async function clearBugMessages() {
  for (const { k } of kvKeys('devthread:')) {
    const t = await devThread(k.slice('devthread:'.length), false);
    if (!t) continue;
    const mine = [];
    let before;
    for (;;) {
      const page = await t.messages.fetch({ limit: 100, ...(before ? { before } : {}) }).catch(() => null);
      if (!page?.size) break;
      for (const m of page.values()) if (m.author.id === ctx.client.user.id && m.id !== t.id) mine.push(m);
      before = [...page.keys()].pop();
      if (page.size < 100) break;
    }
    for (let i = 0; i < mine.length; i += 90) await t.bulkDelete(mine.slice(i, i + 90), true).catch(() => {});
    for (const m of mine) await m.delete().catch(() => {});
  }
  db.prepare('DELETE FROM bug_msgs').run();
}
