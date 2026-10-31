import { ActionRowBuilder, ButtonBuilder, ButtonStyle } from 'discord.js';
import { E, GAP, columns, describe, flat, head, section } from './ui.js';
import { cfg } from './env.js';
import { ctx, fetchChannel } from './ctx.js';
import { db, getGame, upsertGame, createPending, getPending, setPending, delPending, kvGet, kvSet, kvDel, updateBug } from './db.js';
import { ownersFor } from './bounty.js';
import { draftBugFixes, polishUpdates } from './ai.js';
import { devThread, scheduleBoards } from './devboard.js';
import { tagName } from './tags.js';

export const unannounced = (tagId) =>
  db.prepare("SELECT * FROM bugs WHERE game_tag_id=? AND status='fixed' AND announced=0 ORDER BY id").all(tagId);

async function resolveIcon(game) {
  if (game.icon_url) return game.icon_url;
  const m = (game.link || '').match(/roblox\.com\/(?:[a-z-]+\/)?games\/(\d+)/i);
  if (!m) return null;
  try {
    const r = await fetch(`https://thumbnails.roblox.com/v1/places/gameicons?placeIds=${m[1]}&returnPolicy=PlaceHolder&size=256x256&format=Png&isCircular=false`);
    const url = (await r.json()).data?.[0]?.imageUrl;
    if (url) upsertGame(game.tag_id, game.name, { icon_url: url });
    return url || null;
  } catch { return null; }
}

function chunkLines(lines, max = 1000) {
  const out = [];
  let cur = '';
  for (const l of lines) {
    const line = `• ${l}\n`;
    if (cur.length + line.length > max) { out.push(cur.trimEnd()); cur = ''; }
    cur += line;
  }
  if (cur) out.push(cur.trimEnd());
  return out;
}

const httpUrl = (u) => /^https?:\/\//i.test(u || '');
const HALF_RULE = '─'.repeat(28); // fills one half of the embed

// Dev-written update lines, rewritten by Claude into clear patch-note wording (falls back to what the dev typed).
export async function polishDevUpdates(gameName, lines) {
  if (!lines.length) return lines;
  try {
    const out = await polishUpdates(gameName, lines);
    if (out.length === lines.length) return out;
  } catch (e) { console.error('polishUpdates', e.message); }
  return lines;
}

// The public announcement: same flat look, game icon top right, game name links to the game.
export async function buildEmbeds(game, { bugfixes, updates, version }) {
  const icon = await resolveIcon(game);
  const fixChunks = chunkLines(bugfixes, 880);
  const updChunks = chunkLines(updates, 880);
  const first = flat().setTitle(`${game.name.toUpperCase()}${version ? ` · ${version}` : ''}`);
  describe(first, `${E.update} **UPDATE**${GAP}${E.date} <t:${Math.floor(Date.now() / 1000)}:D>${httpUrl(game.link) ? `${GAP}[PLAY](${game.link})` : ''}`);
  if (httpUrl(game.link)) first.setURL(game.link);
  if (httpUrl(icon)) first.setThumbnail(icon);
  const embeds = [first];
  let cur = first;
  let size = 300;
  const room = (chars) => { // start a new embed when this one is full
    if ((cur.data.fields?.length ?? 0) >= 22 || size + chars > 5000) { cur = flat(); embeds.push(cur); size = 0; }
    size += chars;
  };
  if (fixChunks.length && updChunks.length) {
    // Bug fixes and updates side by side, so the full width of the embed is used.
    for (let i = 0; i < Math.max(fixChunks.length, updChunks.length); i++) {
      const a = fixChunks[i];
      const b = updChunks[i];
      room((a?.length ?? 0) + (b?.length ?? 0) + 120);
      columns(cur, [
        { name: head(E.open, i ? 'Bug fixes (cont.)' : 'Bug fixes'), lines: a ? a.split('\n') : ['—'] },
        { name: head('✨', i ? 'Updates (cont.)' : 'Updates'), lines: b ? b.split('\n') : ['—'] },
      ], HALF_RULE);
    }
  } else if (fixChunks.length || updChunks.length) {
    const only = fixChunks.length ? fixChunks : updChunks;
    const label = fixChunks.length ? ['Bug fixes', E.open] : ['Updates', '✨'];
    only.forEach((v, i) => { room(v.length + 80); section(cur, head(label[1], i ? `${label[0]} (cont.)` : label[0]), v); });
  } else {
    room(80);
    section(cur, head('✨', 'Update'), 'Small improvements.');
  }
  embeds[embeds.length - 1].setFooter({ text: 'Thanks to everyone who reported these.' });
  return embeds.slice(0, 10);
}

const draftRow = (id) => new ActionRowBuilder().addComponents(
  new ButtonBuilder().setCustomId(`ann:post:${id}`).setLabel('Post').setStyle(ButtonStyle.Success),
  new ButtonBuilder().setCustomId(`ann:edit:${id}`).setLabel('Edit').setStyle(ButtonStyle.Primary),
  new ButtonBuilder().setCustomId(`ann:later:${id}`).setLabel('Later').setStyle(ButtonStyle.Secondary));

export async function draftPayload(pendingId) {
  const p = getPending(pendingId);
  const game = getGame(p.tagId);
  const warn = (game.announce_channel_id || cfg.updatesId) ? '' : `\n${E.warn} **NO CHANNEL YET** · set one with \`/config set\``;
  return {
    content: p.offer ? offerText(game, p) : `${E.update} **DRAFT** · ${game.name}${warn}`,
    embeds: await buildEmbeds(game, p), components: [draftRow(pendingId)],
    allowedMentions: { parse: [] },
  };
}

// Polishes the pending bug fixes with Claude (falls back to raw titles).
export async function polishFixes(tagId, game) {
  const fixes = unannounced(tagId);
  let lines = fixes.map((f) => f.title);
  try {
    const out = await draftBugFixes(game.name, fixes);
    if (out.length === fixes.length) lines = out;
  } catch (e) { console.error('draftBugFixes', e.message); }
  return { fixes, lines };
}

const offerText = (game, p) =>
  `${p.owners.length ? p.owners.map((o) => `<@${o}>`).join(' ') + ' ' : ''}${E.update} **${p.bugIds.length} FIXES READY** · ${game.name}` +
  ((game.announce_channel_id || cfg.updatesId) ? '' : `\n${E.warn} **NO CHANNEL YET** · set one with \`/config set\``);

// Starts an offer once the game has enough fixes (default 3). While the draft is open it keeps growing
// as more bugs are fixed (3 → 4 → 5 ...), and edits itself in place.
export async function maybeOffer(tagId) {
  if (!tagId) return;
  const game = upsertGame(tagId, tagName(tagId) || tagId);
  const fixes = unannounced(tagId);
  const open = kvGet(`offer:${tagId}`);
  if (open) {
    const pid = Number(open);
    const p = getPending(pid);
    if (p?.messageId) return refreshDraft(pid, p, game, fixes);
    delPending(pid); // stale draft from before live updates existed
    kvDel(`offer:${tagId}`);
  }
  if (fixes.length < Math.max(game.threshold, game.next_offer_at)) return;
  const { lines } = await polishFixes(tagId, game);
  const owners = ownersFor(tagId, game.name);
  const pid = createPending({ tagId, bugIds: fixes.map((f) => f.id), bugfixes: lines, updates: [], version: '', owners, offer: true });
  const t = await devThread(owners[0] || 'unclaimed', true);
  if (!t) return;
  const p = getPending(pid);
  const payload = await draftPayload(pid);
  payload.content = offerText(game, p);
  payload.allowedMentions = { users: owners };
  const sent = await t.send(payload);
  setPending(pid, { ...p, channelId: t.id, messageId: sent.id });
  kvSet(`offer:${tagId}`, pid);
}

async function refreshDraft(pid, p, game, fixes) {
  const have = new Set(p.bugIds);
  const fresh = fixes.filter((f) => !have.has(f.id));
  const gone = p.bugIds.filter((id) => !fixes.some((f) => f.id === id));
  if (!fresh.length && !gone.length) return;
  let bugIds = [...p.bugIds];
  let bugfixes = [...p.bugfixes];
  if (gone.length && bugfixes.length === bugIds.length) { // reopened bugs leave the draft (only when lines still line up)
    for (const id of gone) { const i = bugIds.indexOf(id); bugIds.splice(i, 1); bugfixes.splice(i, 1); }
  } else bugIds = bugIds.filter((id) => !gone.includes(id));
  if (fresh.length) {
    let lines = fresh.map((f) => f.title);
    try {
      const out = await draftBugFixes(game.name, fresh);
      if (out.length === fresh.length) lines = out;
    } catch (e) { console.error('draftBugFixes', e.message); }
    bugIds.push(...fresh.map((f) => f.id));
    bugfixes.push(...lines); // manual edits to older lines are kept, new fixes are appended
  }
  const next = { ...p, bugIds, bugfixes };
  setPending(pid, next);
  const ch = await fetchChannel(p.channelId);
  const msg = ch ? await ch.messages.fetch(p.messageId).catch(() => null) : null;
  if (!msg) { delPending(pid); kvDel(`offer:${p.tagId}`); return; }
  const payload = await draftPayload(pid);
  await msg.edit({ content: offerText(game, next), embeds: payload.embeds, components: payload.components, allowedMentions: { parse: [] } });
}

export async function postAnnouncement(pendingId) {
  const p = getPending(pendingId);
  if (!p) return { ok: false, msg: 'This draft no longer exists.' };
  const game = getGame(p.tagId);
  const ch = await fetchChannel(game.announce_channel_id || cfg.updatesId);
  if (!ch) return { ok: false, msg: 'Set an announcement channel first with `/config set`.' };
  const sent = await ch.send({
    content: game.ping_role_id ? `<@&${game.ping_role_id}>` : undefined,
    embeds: await buildEmbeds(game, p), allowedMentions: { roles: game.ping_role_id ? [game.ping_role_id] : [] },
  });
  for (const id of p.bugIds) updateBug(id, { announced: 1 });
  db.prepare('INSERT INTO announcements(tag_id,game_name,posted_at,url,bug_ids) VALUES(?,?,?,?,?)')
    .run(p.tagId, game.name, Date.now(), sent.url, JSON.stringify(p.bugIds));
  scheduleBoards();
  delPending(pendingId);
  kvDel(`offer:${p.tagId}`);
  upsertGame(p.tagId, game.name, { next_offer_at: 0 });
  return { ok: true, url: sent.url };
}

export function snooze(pendingId) {
  const p = getPending(pendingId);
  if (!p) return;
  upsertGame(p.tagId, getGame(p.tagId).name, { next_offer_at: unannounced(p.tagId).length + 3 });
  delPending(pendingId);
  kvDel(`offer:${p.tagId}`);
}

export { setPending, getPending };
