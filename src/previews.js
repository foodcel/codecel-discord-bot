import { ActionRowBuilder, ButtonBuilder, ButtonStyle } from 'discord.js';
import { cfg } from './env.js';
import { ctx, fetchChannel } from './ctx.js';
import { db, kvKeys, createPending, delPending, getGame } from './db.js';
import { boardEmbed, exploitButtons, exploitCard } from './devboard.js';
import { bugEmbeds } from './bugview.js';
import { buildEmbeds, draftPayload, polishDevUpdates } from './announce.js';
import { rulesEmbed, strikeEmbed, LADDER_TEXT } from './strikes.js';
import { singleTranscript } from './transcript.js';
import { liveMedia } from './media.js';
import { logComponents, logEmbed, renderLog } from './fixlog.js';
import { E } from './ui.js';
import { botNewsEmbeds, testerNewsEmbeds } from './botnews.js';
import { ensureNames, gameEmbeds, gameLists } from './games.js';

// The first three unreleased games shown as released so both embeds can be judged. Nothing is saved.
const sampleLists = () => {
  const live = gameLists();
  const released = live.unreleased.slice(0, 3).map((g, k) => ({ key: g.key, name: g.name, owners: g.owners.join(','), released_at: Date.now() - k * 86400000, link: k === 0 ? 'https://www.roblox.com/games/1' : null }));
  return { released, unreleased: live.unreleased.slice(3) };
};
import { testerReportEmbed } from './tester.js';

const NONE = { parse: [] };

// Deletes every message in the channel (bulk delete, then one by one for anything older than 14 days).
export async function clearChannel(ch) {
  let total = 0;
  for (let round = 0; round < 30; round++) {
    const msgs = await ch.messages.fetch({ limit: 100 });
    if (!msgs.size) break;
    const done = await ch.bulkDelete(msgs, true).catch(() => null);
    total += done?.size ?? 0;
    if (!done?.size) for (const m of msgs.values()) if (await m.delete().then(() => true, () => false)) total++;
  }
  return total;
}

const disabled = (rows) => rows.map((r) => { r.components.forEach((c) => c.setDisabled(true)); return r; });

// Posts the finished embeds (real bugs, real games) into the test channel. 'all' wipes the channel first.
// Anything that could change a real bug, strike or announcement is shown with its buttons switched off.
// Only the fix log keeps live dropdowns, because they just read.
export async function postPreviews(what = 'all') {
  const ch = await fetchChannel(cfg.testId);
  if (!ch) throw new Error('Set TEST_CHANNEL_ID in .env');
  const send = (content, extra = {}) => ch.send({ content, allowedMentions: NONE, ...extra });
  const want = (k) => what === 'all' || what === k;
  let n = 0;
  if (what === 'all') await clearChannel(ch);

  const open = db.prepare("SELECT * FROM bugs WHERE routed=1 AND deleted=0 AND status IN ('new','investigating','fixing') ORDER BY id DESC LIMIT 30").all();
  const withMedia = [];
  for (const b of open) {
    const t = await fetchChannel(b.thread_id);
    const m = t ? await liveMedia(t, b) : null;
    if (m && (m.images.length || m.videos.length)) withMedia.push(b);
    if (withMedia.length >= 2) break;
  }
  const sample = [...withMedia, ...open.filter((b) => !withMedia.includes(b))].slice(0, 2);

  if (want('board')) {
    const own = kvKeys('devthread:').map((r) => r.k.slice('devthread:'.length)).find((k) => k !== 'unclaimed');
    if (own) { await send('**Dev board** · the first message of each dev\'s post (dropdowns not shown here)', { embeds: [boardEmbed(own)] }); n++; }
    await send('**Dev board · unclaimed games**', { embeds: [boardEmbed('unclaimed')] }); n++;
  }
  if (want('bug')) {
    for (const b of sample) { await send(`**Bug page** · what a dev sees when browsing #${b.id} (buttons not shown here)`, { embeds: await bugEmbeds(b) }); n++; }
  }
  const fixed = db.prepare("SELECT * FROM bugs WHERE status='fixed' AND game_tag_id IS NOT NULL ORDER BY fixed_at DESC LIMIT 40").all();
  const tagId = fixed[0]?.game_tag_id;
  if (want('announcement') && tagId) {
    const game = getGame(tagId) || { tag_id: tagId, name: fixed[0].game_name };
    const lines = fixed.filter((f) => f.game_tag_id === tagId).slice(0, 6).map((f) => f.title);
    const typed = ['added new map harbor', 'fixed bug where cars flip over randomly lol', 'made menu faster'];
    const polished = await polishDevUpdates(game.name, typed); // what the dev typed, rewritten by Claude
    const pid = createPending({ tagId, bugIds: fixed.filter((f) => f.game_tag_id === tagId).slice(0, 6).map((f) => f.id), bugfixes: lines, updates: polished, version: 'v1.1', owners: [], offer: true });
    const draft = await draftPayload(pid);
    delPending(pid);
    await send('**Announcement draft** · what the dev gets (buttons off)', { content: `**Announcement draft** · what the dev gets (buttons off)\n${draft.content}`, embeds: draft.embeds, components: disabled(draft.components) }); n++;
    await send('**Public announcement** · what players see', { embeds: await buildEmbeds(game, { bugfixes: lines, updates: polished, version: 'v1.1' }) }); n++;
  }
  if (want('fixlog')) {
    await send('**Fix log board** · the pinned post in #dev-bugs (dropdown works, read only)', { embeds: [logEmbed()], components: logComponents() }); n++;
    const top = db.prepare("SELECT game_tag_id t FROM bugs WHERE status='fixed' GROUP BY game_tag_id ORDER BY COUNT(*) DESC LIMIT 1").get();
    const page = await renderLog(top ? (top.t || 'none') : 'all', 0);
    await send('**Fix log game page** · what the dropdown opens', { ...page, content: '**Fix log game page** · what the dropdown opens' }); n++;
  }
  if (want('rules')) { await send('**Rules** · `/botrules`', { embeds: [rulesEmbed()] }); n++; }
  if (want('mod') && sample[0]) {
    const card = { userId: ctx.client.user.id, count: 3, step: 'kick', reason: 'Spam reports in #bugs (example)', bugId: sample[0].id, pending: true };
    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('x1').setLabel('Confirm kick').setStyle(ButtonStyle.Danger).setDisabled(true),
      new ButtonBuilder().setCustomId('x2').setLabel('Dismiss').setStyle(ButtonStyle.Secondary).setDisabled(true));
    await send('**Mod-log · strike that needs a dev** (example user, buttons off)', { embeds: [strikeEmbed(card)], components: [row] }); n++;
    await send('**High-priority exploit card** · posted straight into the dev board, not mod-log (example, button off)', { embeds: [exploitCard(sample[0], 'Example text of a report that explains how to abuse a bug.', false)], components: disabled(exploitButtons(sample[0].id, 'exploit')) }); n++;
  }
  if (want('messages') && sample[0]) {
    const b = sample[0];
    const u = await ctx.client.users.fetch(b.reporter_id).catch(() => null);
    const who = `@${u?.username ?? 'reporter'}`;
    const t = (s) => s.replace(/ /g, ' ');
    await send([
      '**Messages the bot writes** (names shown instead of pings)',
      `${who} ❓ **NEEDS INFO**\nWhich device are you on, and what exactly happens?\n\n**STILL NEEDED**\n• Device / model\n• Steps to reproduce\n\nReply in this post and I will check again.`,
      `${E.new} **LOGGED** · #${b.id} is sent to the developer. Thanks for the report!`,
      `${E.investigating} **INVESTIGATING** · A developer is looking into this.`,
      `${E.fixing} **FIXING** · A fix is in progress.`,
      `${who} ${E.fixed} **FIXED** · ${b.title} (#${b.id}). Thanks for reporting!`,
      `${E.duplicate} **DUPLICATE** · of #12 "Example". Please add any extra details there.`,
      `${E.notbug} **NOT A BUG** · Reviewed as intended behavior or a feature request.`,
      `${E.duplicate} **REOPENED** · #${b.id} is back on the board.`,
      `${E.warn} **CLOSED** · The missing details never came in.`,
      `@dev ${E.new} **NEW BUG** · #${b.id} · ${b.game_name || 'Unknown game'} (ghost ping: deleted after 2 seconds)`,
      `${E.warn} **STRIKE 1** · ${ctx.guild.name} (DM)\nExample reason. This is a warning. The next steps are:\n${LADDER_TEXT}`,
    ].map(t).join('\n\n')); n++;
  }
  if (want('tester')) {
    const form = { title: 'Car falls through the map', what: 'After the second checkpoint my car drops through the road and I fall forever', steps: '1. Start a race on Harbor\n2. Drive past checkpoint 2\n3. Car falls through', expected: 'The car stays on the road', device: 'PS5' };
    const bug = { id: 99, game_name: 'Example game', title: 'Car falls through the map after checkpoint 2', summary: 'The car drops through the road after the second checkpoint and falls forever.', severity: 'high', created_at: Date.now() };
    await send('**Tester report** · what /bug posts inside the thread in #testing (example)', { embeds: [testerReportEmbed(bug, form, ctx.client.user.id, {})] }); n++;
  }
  if (want('games')) {
    await ensureNames(); // proper titles for the names typed on the bounty-board (cached)
    await send('**Games board** · built from the bounty-board, grouped by dev. SAMPLE: the first 3 unreleased games are shown as released. Post the real one with /games post', {
      embeds: await gameEmbeds(sampleLists()),
    }); n++;
  }
  if (what === 'testernews') { await send('**Tester announcement draft** · for the tester announcements channel. NOT posted there. Would ping: the Tester role only', { embeds: testerNewsEmbeds() }); n++; }
  if (want('botnews')) { await send('**Launch announcement draft** · for #📣┃announcements. NOT posted there, waiting for approval', { embeds: botNewsEmbeds() }); n++; }
  if (want('transcript') && (withMedia[0] || sample[0])) {
    const b = withMedia[0] || sample[0];
    const t = await singleTranscript(b.id);
    if (t) { await send(`**Transcript** of #${b.id}\n${t.note}`, { files: t.files }); n++; }
  }
  return n;
}
