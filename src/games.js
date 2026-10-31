import { SlashCommandBuilder, MessageFlags } from 'discord.js';
import { ctx, fetchChannel } from './ctx.js';
import { db, kvGet, kvSet, kvDel, now } from './db.js';
import { getClaims } from './bounty.js';
import { canManage, level } from './perms.js';
import { onBoardsRefreshed } from './devboard.js';
import { E, GAP, columns, cut, describe, flat, head } from './ui.js';

// Released / unreleased games. The list of games in development comes from the bounty-board claims.
// A dev marks a game released with /release (it is stored here, so it stays even after it leaves the bounty-board).
const EPH = MessageFlags.Ephemeral;
const key = (s) => String(s).toLowerCase().replace(/[^a-z0-9]/g, '');
const http = (u) => /^https?:\/\//i.test(u || '');
const day = (ts) => (ts ? `<t:${Math.floor(ts / 1000)}:d>` : '—');
const dayText = (s) => { const t = Date.parse(s); return Number.isNaN(t) ? '—' : day(t); };
const devs = (owners) => (owners.length ? owners.map((o) => `<@${o}>`).join(' ') : '—');

export function gameLists() {
  const rows = db.prepare('SELECT * FROM game_status').all();
  const released = rows.filter((r) => r.status === 'released').sort((a, b) => b.released_at - a.released_at);
  const releasedKeys = new Set(released.map((r) => r.key));
  const unreleased = [];
  const seen = new Set();
  for (const c of getClaims()) {
    const k = key(c.name);
    seen.add(k);
    if (!releasedKeys.has(k)) unreleased.push({ key: k, name: c.name, owners: c.owners, since: c.since });
  }
  // moved back to unreleased after it had left the bounty-board
  for (const r of rows) {
    if (r.status === 'unreleased' && !seen.has(r.key)) unreleased.push({ key: r.key, name: r.name, owners: (r.owners || '').split(',').filter(Boolean), since: r.since });
  }
  unreleased.sort((a, b) => a.name.localeCompare(b.name));
  return { released, unreleased };
}

// Adds the rows as three columns. Long lists are split into several rows of columns (a field holds 1024 characters).
function table(e, headings, rows) {
  if (!rows.length) { e.addFields({ name: '​', value: 'None yet.' }); return; }
  let chunk = [];
  let len = [0, 0, 0];
  const flush = (first) => {
    columns(e, headings.map((name, i) => ({ name: first ? name : '​', lines: chunk.map((r) => r[i]) })), first ? undefined : '');
    chunk = []; len = [0, 0, 0];
  };
  let first = true;
  for (const r of rows) {
    if (chunk.length && r.some((cell, i) => len[i] + cell.length + 1 > 960)) { flush(first); first = false; }
    chunk.push(r);
    r.forEach((cell, i) => { len[i] += cell.length + 1; });
  }
  if (chunk.length) flush(first);
}

export function gameEmbeds(lists = gameLists()) {
  const { released, unreleased } = lists;
  const rel = flat().setTitle(head('✅', 'Released games'));
  describe(rel, `${E.fixed} **${released.length}** released`);
  table(rel, [head(E.game, 'Game'), head(E.user, 'Dev'), head(E.date, 'Released')],
    released.map((r) => [http(r.link) ? `[**${cut(r.name, 30)}**](${r.link})` : `**${cut(r.name, 30)}**`, devs((r.owners || '').split(',').filter(Boolean)), day(r.released_at)]));
  const dev = flat().setTitle(head('🛠️', 'Unreleased games'))
    .setFooter({ text: 'Game owners: /release when a game is out, /unrelease to move it back.' });
  describe(dev, `🛠️ **${unreleased.length}** in development${GAP}${E.fixed} **${released.length}** released`);
  table(dev, [head(E.game, 'Game'), head(E.user, 'Dev'), head(E.date, 'Since')],
    unreleased.map((g) => [`**${cut(g.name, 30)}**`, devs(g.owners), dayText(g.since)]));
  return [rel, dev];
}

// ---- the live board message (posted once with /games post, then kept up to date) ----
export async function refreshGameBoard() {
  const ref = kvGet('gameboard');
  if (!ref) return;
  const { channelId, messageId } = JSON.parse(ref);
  const ch = await fetchChannel(channelId);
  const msg = ch ? await ch.messages.fetch(messageId).catch(() => null) : null;
  if (!msg) { kvDel('gameboard'); return; }
  await msg.edit({ embeds: gameEmbeds() }).catch((e) => console.error('game board', e.message));
}
onBoardsRefreshed(refreshGameBoard);

// ---- commands ----
export const gameCommandDefs = [
  new SlashCommandBuilder().setName('release').setDescription('Mark one of your games as released')
    .addStringOption((o) => o.setName('game').setDescription('Game').setAutocomplete(true).setRequired(true))
    .addStringOption((o) => o.setName('link').setDescription('Link players use to play it (optional)')),
  new SlashCommandBuilder().setName('unrelease').setDescription('Move a released game back to unreleased')
    .addStringOption((o) => o.setName('game').setDescription('Game').setAutocomplete(true).setRequired(true)),
  new SlashCommandBuilder().setName('games').setDescription('Admin: post the released / unreleased games board in this channel'),
];

export async function autocompleteGames(i) {
  const q = String(i.options.getFocused()).toLowerCase();
  const { released, unreleased } = gameLists();
  const list = (i.commandName === 'release' ? unreleased : released).map((g) => g.name);
  await i.respond(list.filter((n) => n.toLowerCase().includes(q)).slice(0, 25).map((n) => ({ name: n.slice(0, 100), value: n.slice(0, 100) })));
}

const find = (name) => {
  const k = key(name);
  const { released, unreleased } = gameLists();
  return { k, rel: released.find((g) => g.key === k), dev: unreleased.find((g) => g.key === k) };
};
const ownerIds = (g) => (Array.isArray(g.owners) ? g.owners : String(g.owners || '').split(',').filter(Boolean));

export async function commandRelease(i, undo = false) {
  const name = i.options.getString('game');
  const { k, rel, dev } = find(name);
  const g = undo ? rel : dev;
  if (!g) return i.reply({ content: undo ? 'That game is not in the released list.' : 'That game is not in the unreleased list. Claim it on the bounty-board first.', flags: EPH });
  if (!canManage(i.member, ownerIds(g))) return i.reply({ content: 'Only the dev who owns this game, or an admin, can change it.', flags: EPH });
  if (undo) {
    db.prepare("UPDATE game_status SET status='unreleased', released_at=NULL WHERE key=?").run(k);
  } else {
    const link = i.options.getString('link');
    if (link && !http(link)) return i.reply({ content: 'The link must start with http:// or https://', flags: EPH });
    db.prepare(`INSERT INTO game_status(key,name,owners,since,status,released_at,released_by,link) VALUES(?,?,?,?,'released',?,?,?)
      ON CONFLICT(key) DO UPDATE SET status='released', released_at=excluded.released_at, released_by=excluded.released_by,
      link=COALESCE(excluded.link, game_status.link), owners=excluded.owners, name=excluded.name`)
      .run(k, g.name, ownerIds(g).join(','), g.since ?? null, now(), i.user.id, link || null);
  }
  await refreshGameBoard();
  return i.reply({
    content: undo ? `${E.warn} **UNRELEASED** · ${g.name} is back in development.` : `${E.fixed} **RELEASED** · ${g.name} is now in the released list.`,
    flags: EPH,
  });
}

export async function commandGames(i) {
  if (level(i.member) !== 'admin') return i.reply({ content: 'Only admins can post the board.', flags: EPH });
  const old = kvGet('gameboard');
  const msg = await i.channel.send({ embeds: gameEmbeds() });
  kvSet('gameboard', JSON.stringify({ channelId: msg.channelId, messageId: msg.id }));
  if (old) { // the previous board stops updating, remove it so there is only one
    const { channelId, messageId } = JSON.parse(old);
    const ch = await fetchChannel(channelId);
    await (await ch?.messages.fetch(messageId).catch(() => null))?.delete().catch(() => {});
  }
  return i.reply({ content: `Posted. It updates by itself when a game is released or claimed.`, flags: EPH });
}
