import { SlashCommandBuilder, MessageFlags } from 'discord.js';
import { ctx, fetchChannel } from './ctx.js';
import { db, kvGet, kvSet, kvDel, now } from './db.js';
import { getClaims } from './bounty.js';
import { canManage, level } from './perms.js';
import { onBoardsRefreshed } from './devboard.js';
import { cleanGameNames } from './ai.js';
import { E, columns, cut, describe, flat, head } from './ui.js';

// Released / unreleased games, rows sorted by dev. The games in development come from the bounty-board claims.
// A dev marks a game released with /release (stored here, so it stays after the bounty-board drops it).
// Names typed on the bounty-board ("YOU SHOULD MAKE DELTARUNE PLEASE") are turned into proper titles by Claude once and cached.
const EPH = MessageFlags.Ephemeral;
const key = (s) => String(s).toLowerCase().replace(/[^a-z0-9]/g, '');
const http = (u) => /^https?:\/\//i.test(u || '');
const shortDate = (ts) => new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
const ownerIds = (g) => (Array.isArray(g.owners) ? g.owners : String(g.owners || '').split(',').filter(Boolean));

// ---- proper game names ----
const tidy = (s) => {
  const t = String(s).replace(/\b(please|pls|bro)\b/gi, '').replace(/\s+/g, ' ').trim();
  return t === t.toUpperCase() && t.length > 5 ? t.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()) : t;
};
export const cleanName = (raw) => db.prepare('SELECT clean FROM game_names WHERE key=?').get(key(raw))?.clean ?? tidy(raw);

// Keeps a title inside the column: drops a leading "The" and a "Call of Duty:" prefix when it is too long.
const shorten = (t) => {
  let s = String(t).trim();
  if (s.length <= 19) return s;
  s = s.replace(/^(call of duty|cod):\s*/i, '').replace(/^(the|a)\s+/i, '');
  return s;
};

// Asks Claude for the proper title of every name that has none yet. A failed call is retried next time.
export async function ensureNames() {
  const raws = new Set([...getClaims().map((c) => c.name), ...db.prepare('SELECT name FROM game_status').all().map((r) => r.name)]);
  const missing = [...raws].filter((r) => !db.prepare('SELECT 1 FROM game_names WHERE key=?').get(key(r))).slice(0, 60);
  if (!missing.length) return;
  let titles = null;
  try { titles = await cleanGameNames(missing); } catch (e) { console.error('cleanGameNames', e.message); }
  if (!titles || titles.length !== missing.length) return;
  const ins = db.prepare('INSERT OR IGNORE INTO game_names(key,raw,clean,manual) VALUES(?,?,?,0)');
  missing.forEach((raw, i) => ins.run(key(raw), raw, cut(shorten(titles[i] || tidy(raw)), 40)));
}

// ---- the lists ----
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
    if (r.status === 'unreleased' && !seen.has(r.key)) unreleased.push({ key: r.key, name: r.name, owners: ownerIds(r), since: r.since });
  }
  return { released, unreleased };
}

// ---- the table ----
async function devName(id) {
  const m = await ctx.guild.members.fetch(id).catch(() => null);
  return m?.displayName ?? 'Unknown';
}

// Rows are sorted by dev, so all the games of one dev sit right under each other (dev with most games first).
// A game with two owners shows once under each owner.
async function rowsByDev(entries) {
  const per = new Map();
  for (const e of entries) for (const o of (e.owners.length ? e.owners : ['none'])) {
    if (!per.has(o)) per.set(o, []);
    per.get(o).push(e);
  }
  const devs = await Promise.all([...per].map(async ([id, list]) => ({ id, name: id === 'none' ? 'No dev' : await devName(id), list })));
  devs.sort((a, b) => b.list.length - a.list.length || a.name.localeCompare(b.name));
  return devs.flatMap((d) => d.list.sort((a, b) => a.name.localeCompare(b.name)).map((g) => ({ dev: d.id === 'none' ? '—' : `<@${d.id}>`, ...g })));
}

// Three columns. Game names are cut to 19 characters so no column grows past its third of the embed: that is what keeps the
// columns in the same place in both embeds. A long list is split into several rows of columns (a field holds 1024 characters).
function table(e, headings, rows) {
  let chunk = [];
  let len = [0, 0, 0];
  let first = true;
  const flush = () => {
    columns(e, headings.map((name, i) => ({ name: first ? name : '​', lines: chunk.map((r) => r[i]) })), first ? undefined : '');
    chunk = []; len = [0, 0, 0]; first = false;
  };
  for (const r of rows) {
    if (chunk.length && r.some((cell, i) => len[i] + cell.length + 1 > 960)) flush();
    chunk.push(r);
    r.forEach((cell, i) => { len[i] += cell.length + 1; });
  }
  if (chunk.length) flush();
}

export async function gameEmbeds(lists = gameLists()) {
  const rel = await rowsByDev(lists.released.map((r) => ({ name: cleanName(r.name), owners: ownerIds(r), at: r.released_at, link: r.link })));
  const dev = await rowsByDev(lists.unreleased.map((g) => ({ name: cleanName(g.name), owners: g.owners, since: g.since })));
  const nGames = (rows) => new Set(rows.map((r) => r.name)).size;

  const e1 = flat().setTitle(head('✅', 'Released games'));
  describe(e1, `${E.fixed} **${nGames(rel)}** released`);
  if (rel.length) {
    table(e1, [head(E.user, 'Dev'), head(E.game, 'Game'), head(E.date, 'Released')],
      rel.map((r) => [r.dev, http(r.link) ? `[**${cut(r.name, 19)}**](${r.link})` : `**${cut(r.name, 19)}**`, `<t:${Math.floor(r.at / 1000)}:d>`]));
  } else e1.addFields({ name: '​', value: 'None yet.' });

  const e2 = flat().setTitle(head('🛠️', 'Unreleased games'))
    .setFooter({ text: 'Game owners: /release when a game is out, /unrelease to move it back.' });
  describe(e2, `🛠️ **${nGames(dev)}** in development`);
  if (dev.length) {
    table(e2, [head(E.user, 'Dev'), head(E.game, 'Game'), head(E.date, 'Since')],
      dev.map((r) => [r.dev, `**${cut(r.name, 19)}**`, Number.isNaN(Date.parse(r.since)) ? '—' : `<t:${Math.floor(Date.parse(r.since) / 1000)}:d>`]));
  } else e2.addFields({ name: '​', value: 'None yet.' });
  return [e1, e2];
}

// ---- the live board message (posted once with /games post, then kept up to date) ----
export async function refreshGameBoard() {
  const ref = kvGet('gameboard');
  if (!ref) return;
  const { channelId, messageId } = JSON.parse(ref);
  const ch = await fetchChannel(channelId);
  const msg = ch ? await ch.messages.fetch(messageId).catch(() => null) : null;
  if (!msg) { kvDel('gameboard'); return; }
  await ensureNames();
  await msg.edit({ embeds: await gameEmbeds() }).catch((e) => console.error('game board', e.message));
}
onBoardsRefreshed(refreshGameBoard);

// ---- commands ----
export const gameCommandDefs = [
  new SlashCommandBuilder().setName('release').setDescription('Mark one of your games as released')
    .addStringOption((o) => o.setName('game').setDescription('Game').setAutocomplete(true).setRequired(true))
    .addStringOption((o) => o.setName('link').setDescription('Link players use to play it (optional)')),
  new SlashCommandBuilder().setName('unrelease').setDescription('Move a released game back to unreleased')
    .addStringOption((o) => o.setName('game').setDescription('Game').setAutocomplete(true).setRequired(true)),
  new SlashCommandBuilder().setName('games').setDescription('Admin: the released / unreleased games board')
    .addSubcommand((s) => s.setName('post').setDescription('Post the board in this channel (it updates by itself)'))
    .addSubcommand((s) => s.setName('rename').setDescription('Fix the name shown for a game')
      .addStringOption((o) => o.setName('game').setDescription('Game').setAutocomplete(true).setRequired(true))
      .addStringOption((o) => o.setName('name').setDescription('The correct name').setRequired(true).setMaxLength(40))),
];

// Shows the proper name, answers with the typed name (that is what the lists are keyed on).
export async function autocompleteGames(i) {
  const q = String(i.options.getFocused()).toLowerCase();
  const { released, unreleased } = gameLists();
  const all = i.commandName === 'release' ? unreleased : i.commandName === 'unrelease' ? released : [...unreleased, ...released];
  const out = all.map((g) => ({ name: cleanName(g.name).slice(0, 100), value: g.name.slice(0, 100) }))
    .filter((c) => c.name.toLowerCase().includes(q) || c.value.toLowerCase().includes(q));
  await i.respond(out.slice(0, 25));
}

const find = (name) => {
  const k = key(name);
  const { released, unreleased } = gameLists();
  return { k, rel: released.find((g) => g.key === k), dev: unreleased.find((g) => g.key === k) };
};

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
  const shown = cleanName(g.name);
  return i.reply({
    content: undo ? `${E.warn} **UNRELEASED** · ${shown} is back in development.` : `${E.fixed} **RELEASED** · ${shown} is now in the released list.`,
    flags: EPH,
  });
}

export async function commandGames(i) {
  if (level(i.member) !== 'admin') return i.reply({ content: 'Only admins can use this.', flags: EPH });
  if (i.options.getSubcommand() === 'rename') {
    const raw = i.options.getString('game');
    const g = [...gameLists().unreleased, ...gameLists().released].find((x) => x.key === key(raw));
    if (!g) return i.reply({ content: 'I do not know that game.', flags: EPH });
    const clean = i.options.getString('name').trim();
    db.prepare('INSERT INTO game_names(key,raw,clean,manual) VALUES(?,?,?,1) ON CONFLICT(key) DO UPDATE SET clean=excluded.clean, manual=1').run(key(raw), g.name, clean);
    await refreshGameBoard();
    return i.reply({ content: `Now shown as **${clean}**.`, flags: EPH });
  }
  await i.deferReply({ flags: EPH });
  await ensureNames();
  const old = kvGet('gameboard');
  const msg = await i.channel.send({ embeds: await gameEmbeds() });
  kvSet('gameboard', JSON.stringify({ channelId: msg.channelId, messageId: msg.id }));
  if (old) { // the previous board stops updating, remove it so there is only one
    const { channelId, messageId } = JSON.parse(old);
    const ch = await fetchChannel(channelId);
    await (await ch?.messages.fetch(messageId).catch(() => null))?.delete().catch(() => {});
  }
  return i.editReply('Posted. It updates by itself when a game is released or claimed.');
}
