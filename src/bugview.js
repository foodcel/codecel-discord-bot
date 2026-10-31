import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags, ModalBuilder, TextInputBuilder, TextInputStyle,
} from 'discord.js';
import { bugById } from './db.js';
import { ctx, fetchChannel, threadLink } from './ctx.js';
import { openBugsFor, boardComponents } from './devboard.js';
import { ownersFor } from './bounty.js';
import { canManage } from './perms.js';
import { applyStatus } from './fixes.js';
import { deviceTags, tagName } from './tags.js';
import { liveMedia } from './media.js';
import { E, FILLER, FILLER_SHORT, SEVERITY, STATUS, columns, describe, flat, head, plain } from './ui.js';

const EPH = MessageFlags.Ephemeral;

const listFor = (key, game) => openBugsFor(key).filter((b) => game === 'all' || (b.game_tag_id || 'none') === game);

export async function bugEmbeds(bug) {
  const thread = await fetchChannel(bug.thread_id);
  const media = thread ? await liveMedia(thread, bug) : { text: '', images: [], videos: [] };
  const reporter = await ctx.client.users.fetch(bug.reporter_id).catch(() => null);
  const deviceNames = deviceTags().map((t) => t.name);
  const devices = bug.device ? [bug.device] : (thread ? (thread.appliedTags || []).map(tagName).filter((n) => deviceNames.includes(n)) : []);
  const url = threadLink(bug.thread_id);
  const quote = media.text ? `\n\n> ${media.text.replace(/\n+/g, '\n> ').slice(0, 700)}` : '';
  const embed = flat().setURL(url)
    .setTitle(head(E.open, `#${bug.id} · ${bug.game_name || 'Unknown game'}`))
    .setFooter({ text: `Bug #${bug.id} · reported` }).setTimestamp(bug.created_at);
  describe(embed, `### ${bug.title}\n${bug.summary || ''}${quote}`.slice(0, 3900), media.images.length ? FILLER_SHORT : FILLER);
  columns(embed, [
    { name: head(E.status, 'Status'), lines: [STATUS[bug.status] || bug.status, '​'] },
    { name: head(E.severity, 'Severity'), lines: [SEVERITY[bug.severity] || '?', '​'] },
    { name: head(E.device, 'Device'), lines: [devices.join(', ') || 'Not given', '​'] },
  ], ''); // no rule lines on this page
  if (reporter) embed.setAuthor({ name: reporter.displayName ?? reporter.username, iconURL: reporter.displayAvatarURL() });
  if (media.videos.length) {
    plain(embed, head(E.video, 'Videos & media'), media.videos.slice(0, 6).map((v) => `[${v.label}](${v.url})`).join('\n'));
  }
  const embeds = [embed];
  if (media.images.length) {
    embed.setImage(media.images[0]);
    for (const img of media.images.slice(1)) embeds.push(flat().setURL(url).setImage(img));
  }
  return embeds;
}

const btn = (id, label, style = ButtonStyle.Secondary, disabled = false) =>
  new ButtonBuilder().setCustomId(id).setLabel(label).setStyle(style).setDisabled(disabled);

// The private page: one bug at a time, with prev/next, status buttons (only for people who may change them) and transcripts.
export async function renderView(member, key, game, bugId) {
  const list = listFor(key, game);
  if (!list.length) return { content: 'No more open bugs here 🎉', embeds: [], components: [] };
  let idx = list.findIndex((b) => b.id === bugId);
  if (idx < 0) {
    const next = list.findIndex((b) => b.id > bugId);
    idx = next < 0 ? list.length - 1 : next;
  }
  const bug = list[idx];
  const id = (act, extra = '') => `v:${act}:${key}:${game}:${bug.id}${extra}`;
  const rows = [new ActionRowBuilder().addComponents(
    btn(id('p'), '◀ Prev', ButtonStyle.Secondary, idx === 0),
    btn('v:noop', `${idx + 1} / ${list.length}`, ButtonStyle.Secondary, true),
    btn(id('n'), 'Next ▶', ButtonStyle.Secondary, idx === list.length - 1))];
  if (canManage(member, ownersFor(bug.game_tag_id, bug.game_name))) {
    rows.push(new ActionRowBuilder().addComponents(
      btn(id('st', ':investigating'), '🔎 Investigating'),
      btn(id('st', ':fixing'), '🛠️ Fixing'),
      btn(id('st', ':fixed'), '✅ Fixed', ButtonStyle.Success),
      btn(id('st', ':not_a_bug'), `${E.notbug} Not a bug`),
      btn(id('st', ':duplicate'), `${E.duplicate} Duplicate`)));
  }
  const manage = canManage(member, ownersFor(bug.game_tag_id, bug.game_name));
  rows.push(new ActionRowBuilder().addComponents(
    btn(`tr:${bug.id}`, '📋 Transcript', ButtonStyle.Primary),
    ...(manage ? [btn(id('note'), '🎮 Set game / add note')] : []),
    new ButtonBuilder().setLabel('Open post').setStyle(ButtonStyle.Link).setURL(threadLink(bug.thread_id))));
  return { content: `Bug ${idx + 1} of ${list.length}`, embeds: await bugEmbeds(bug), components: rows };
}

// Game picker on the board message.
export async function openGame(i, key, game) {
  await i.deferReply({ flags: EPH });
  i.message.edit({ components: boardComponents(key) }).catch(() => {}); // resets the picker so the same game can be picked again
  const list = listFor(key, game);
  if (!list.length) return i.editReply({ content: 'No open bugs for that game.' });
  return i.editReply(await renderView(i.member, key, game, list[0].id));
}

// Buttons inside the private page: v:<act>:<key>:<game>:<bugId>[:<status>]
export async function handleView(i) {
  const [, act, key, game, id, status] = i.customId.split(':');
  if (act === 'noop') return i.deferUpdate();
  const bugId = Number(id);
  if (act === 'note') { // modals must open before any deferral
    const bug = bugById(bugId);
    if (!bug || !canManage(i.member, ownersFor(bug.game_tag_id, bug.game_name))) return i.reply({ content: 'You cannot change this bug.', flags: EPH });
    return i.showModal(new ModalBuilder().setCustomId(`note:${bugId}`).setTitle(`Note for bug #${bugId}`).addComponents(
      new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('note').setLabel('Tell the bot what this is')
        .setStyle(TextInputStyle.Paragraph).setRequired(true).setMaxLength(500)
        .setPlaceholder('e.g. This is Vyra Station. Happens on PS5 only.'))));
  }
  await i.deferUpdate();
  if (act === 'p' || act === 'n') {
    const list = listFor(key, game);
    const idx = Math.max(0, list.findIndex((b) => b.id === bugId));
    const target = list[Math.min(list.length - 1, Math.max(0, idx + (act === 'n' ? 1 : -1)))];
    return i.editReply(await renderView(i.member, key, game, target?.id ?? bugId));
  }
  if (act === 'st') {
    const { done, skipped } = await applyStatus([bugId], status, i.member);
    if (!done.length) await i.followUp({ content: `Could not change #${bugId}: ${skipped[0] || 'unknown'}`, flags: EPH });
    return i.editReply(await renderView(i.member, key, game, bugId));
  }
}
