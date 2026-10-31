import {
  ActionRowBuilder, ChannelType, EmbedBuilder, MessageFlags, ModalBuilder, SlashCommandBuilder, StringSelectMenuBuilder,
  TextInputBuilder, TextInputStyle,
} from 'discord.js';
import { ctx, dm, fetchChannel } from './ctx.js';
import { cfg } from './env.js';
import { interpretNote } from './ai.js';
import { findDeviceTag, findGameTag, setTags } from './tags.js';
import { getPrefs, setPrefs, updateBug } from './db.js';
import { E, describe as describeEmbed } from './ui.js';
import { ATTACH, commandBug, modalBug } from './tester.js';
import { autocompleteGames, commandGames, commandRelease, gameCommandDefs } from './games.js';
import { postPreviews } from './previews.js';
import { bugById, getGame, upsertGame, getPending, setPending, createPending } from './db.js';
import { getClaims, ownersFor, boardNameFor } from './bounty.js';
import { canConfirm, canManage, level } from './perms.js';
import { gameTags, tagName } from './tags.js';
import { applyStatus } from './fixes.js';
import { draftPayload, polishDevUpdates, polishFixes, postAnnouncement, snooze, unannounced } from './announce.js';
import { pardon, resolveStrike, rulesEmbed, strikeInfo } from './strikes.js';
import { boardTranscript, singleTranscript } from './transcript.js';
import { boardComponents, exploitButtons, exploitStatusLine, openBugsFor, routeBug, scheduleBoards } from './devboard.js';
import { handleView, openGame } from './bugview.js';
import { logPage, openLog, sendFixTranscript } from './fixlog.js';

const EPH = MessageFlags.Ephemeral;
const http = (u) => /^https?:\/\//i.test(u || '');

export const commandDefs = [
  new SlashCommandBuilder().setName('config').setDescription('Set up a game for update announcements')
    .addSubcommand((s) => s.setName('set').setDescription('Change announcement settings for a game')
      .addStringOption((o) => o.setName('game').setDescription('Game').setAutocomplete(true).setRequired(true))
      .addStringOption((o) => o.setName('link').setDescription('Link to the game'))
      .addStringOption((o) => o.setName('icon').setDescription('Icon image URL (auto-pulled from a Roblox link if empty)'))
      .addChannelOption((o) => o.setName('channel').setDescription('Announcement channel')
        .addChannelTypes(ChannelType.GuildText, ChannelType.GuildAnnouncement))
      .addRoleOption((o) => o.setName('role').setDescription('Role to ping on announcements'))
      .addIntegerOption((o) => o.setName('threshold').setDescription('Fixes before an announcement is offered').setMinValue(1).setMaxValue(50))
      .addUserOption((o) => o.setName('owner').setDescription('Admin only: force the owner of this game'))
      .addStringOption((o) => o.setName('board').setDescription('Admin only: the bounty-board name of this game').setAutocomplete(true)))
    .addSubcommand((s) => s.setName('show').setDescription('Show game settings')
      .addStringOption((o) => o.setName('game').setDescription('Game').setAutocomplete(true))),
  new SlashCommandBuilder().setName('update').setDescription('Post a game update with its bug fixes')
    .addStringOption((o) => o.setName('game').setDescription('Game').setAutocomplete(true).setRequired(true)),
  (() => {
    const cmd = new SlashCommandBuilder().setName('bug').setDescription('Testers: report a bug straight to the developers')
      .addStringOption((o) => o.setName('game').setDescription('Which game').setAutocomplete(true).setRequired(true));
    ATTACH.screenshots.forEach((name, k) => cmd.addAttachmentOption((o) => o.setName(name).setDescription(`Screenshot ${k + 1} (optional)`)));
    ATTACH.videos.forEach((name, k) => cmd.addAttachmentOption((o) => o.setName(name).setDescription(`Video ${k + 1} (optional)`)));
    return cmd;
  })(),
  new SlashCommandBuilder().setName('pings').setDescription('Choose when the bot pings you')
    .addStringOption((o) => o.setName('bugs').setDescription('Ping me when a new bug arrives on my games')
      .addChoices({ name: 'On', value: 'on' }, { name: 'Off', value: 'off' }))
    .addStringOption((o) => o.setName('exploits').setDescription('Ping me for high-priority exploit reports')
      .addChoices({ name: 'On', value: 'on' }, { name: 'Off', value: 'off' })),
  new SlashCommandBuilder().setName('strikes').setDescription('Show a user\'s troll strikes')
    .addUserOption((o) => o.setName('user').setDescription('User').setRequired(true)),
  new SlashCommandBuilder().setName('pardon').setDescription('Remove one strike from a user')
    .addUserOption((o) => o.setName('user').setDescription('User').setRequired(true)),
  new SlashCommandBuilder().setName('preview').setDescription('Admin: post the finished embeds in the test channel (everything wipes it first)')
    .addStringOption((o) => o.setName('what').setDescription('Which preview').addChoices(
      { name: 'everything (clears the test channel)', value: 'all' }, { name: 'dev board', value: 'board' }, { name: 'bug page', value: 'bug' },
      { name: 'announcements', value: 'announcement' }, { name: 'fix log', value: 'fixlog' }, { name: 'rules', value: 'rules' },
      { name: 'mod cards', value: 'mod' }, { name: 'bot messages', value: 'messages' }, { name: 'transcript', value: 'transcript' },
      { name: 'launch announcement draft', value: 'botnews' }, { name: 'tester report', value: 'tester' }, { name: 'tester announcement draft', value: 'testernews' }, { name: 'games board', value: 'games' })),
  new SlashCommandBuilder().setName('botrules').setDescription('Post the bug report rules and strike ladder here'),
  ...gameCommandDefs,
];

const deny = (i, text = 'You do not have permission for that.') => i.reply({ content: text, flags: EPH });
const ownerOf = (tagId) => ownersFor(tagId, tagName(tagId) || '');

async function autocomplete(i) {
  if (i.commandName === 'release' || i.commandName === 'unrelease') return autocompleteGames(i);
  const focused = i.options.getFocused(true);
  const q = String(focused.value).toLowerCase();
  let list;
  if (focused.name === 'board') {
    list = getClaims().map((c) => ({ name: c.name.slice(0, 100), value: c.name.slice(0, 100) }));
  } else {
    const onlyMine = i.commandName === 'update' || (i.commandName === 'config' && i.options.getSubcommand() === 'set');
    list = gameTags()
      .filter((t) => !onlyMine || canManage(i.member, ownerOf(t.id)))
      .map((t) => ({ name: t.name, value: t.id }));
  }
  await i.respond(list.filter((c) => c.name.toLowerCase().includes(q)).slice(0, 25));
}

async function configSet(i) {
  const tagId = i.options.getString('game');
  const name = tagName(tagId);
  if (!name) return deny(i, 'Unknown game.');
  if (!canManage(i.member, ownerOf(tagId))) return deny(i, 'Only the dev who claimed this game (or an admin) can change it.');
  const patch = {};
  const link = i.options.getString('link');
  const icon = i.options.getString('icon');
  if (link) { if (!http(link)) return deny(i, 'The link must start with http:// or https://'); patch.link = link; }
  if (icon) { if (!http(icon)) return deny(i, 'The icon must be an image URL starting with http(s)://'); patch.icon_url = icon; }
  const ch = i.options.getChannel('channel');
  if (ch) patch.announce_channel_id = ch.id;
  const role = i.options.getRole('role');
  if (role) patch.ping_role_id = role.id;
  const th = i.options.getInteger('threshold');
  if (th) patch.threshold = th;
  const owner = i.options.getUser('owner');
  const board = i.options.getString('board');
  if (owner || board) {
    if (level(i.member) !== 'admin') return deny(i, 'Only admins can set the owner or board name.');
    if (owner) patch.owner_override = owner.id;
    if (board) patch.board_name = board;
  }
  if (!Object.keys(patch).length) return deny(i, 'Nothing to change. Pass at least one option.');
  const g = upsertGame(tagId, name, patch);
  if (patch.owner_override || patch.board_name) scheduleBoards();
  return i.reply({ content: `Saved **${g.name}**.\n${describe(g)}`, flags: EPH });
}

function describe(g) {
  const owners = ownersFor(g.tag_id, g.name);
  return [
    `Owner: ${owners.length ? owners.map((o) => `<@${o}>`).join(' ') : 'nobody (unclaimed)'}${g.owner_override ? ' (set by admin)' : ''} · board name: ${boardNameFor(g.tag_id, g.name) || 'no match'}`,
    `Link: ${g.link || '—'} · Icon: ${g.icon_url ? 'set' : 'auto/none'}`,
    `Channel: ${g.announce_channel_id ? `<#${g.announce_channel_id}>` : '—'} · Ping: ${g.ping_role_id ? `<@&${g.ping_role_id}>` : '—'}`,
    `Offer an announcement at **${g.threshold}** fixes · ready now: **${unannounced(g.tag_id).length}**`,
  ].join('\n');
}

async function configShow(i) {
  const only = i.options.getString('game');
  const tags = gameTags().filter((t) => !only || t.id === only);
  const text = tags.map((t) => `**${t.name}**\n${describe(upsertGame(t.id, t.name))}`).join('\n\n');
  return i.reply({ content: text.slice(0, 1990) || 'No games.', flags: EPH, allowedMentions: { parse: [] } });
}

const input = (id, label, style, value, required = false) => new ActionRowBuilder().addComponents(
  new TextInputBuilder().setCustomId(id).setLabel(label).setStyle(style).setRequired(required)
    .setMaxLength(style === TextInputStyle.Paragraph ? 3000 : 40).setValue((value || '').slice(0, style === TextInputStyle.Paragraph ? 3000 : 40)));

async function commandUpdate(i) {
  const tagId = i.options.getString('game');
  if (!tagName(tagId)) return deny(i, 'Unknown game.');
  if (!canManage(i.member, ownerOf(tagId))) return deny(i, 'Only the dev who claimed this game (or an admin) can post updates.');
  const modal = new ModalBuilder().setCustomId(`upd:${tagId}`).setTitle(`Update: ${tagName(tagId)}`.slice(0, 45))
    .addComponents(
      input('updates', 'Updates (one per line)', TextInputStyle.Paragraph, ''),
      input('version', 'Version (optional)', TextInputStyle.Short, ''));
  return i.showModal(modal);
}

const lines = (s) => (s || '').split('\n').map((l) => l.replace(/^[\s•*\-–]+/, '').trim()).filter(Boolean);

async function modalUpdate(i, tagId) {
  const game = upsertGame(tagId, tagName(tagId));
  await i.deferReply();
  const { fixes, lines: fixLines } = await polishFixes(tagId, game);
  const pid = createPending({
    tagId, bugIds: fixes.map((f) => f.id), bugfixes: fixLines,
    updates: await polishDevUpdates(game.name, lines(i.fields.getTextInputValue('updates'))), // Claude rewrites what the dev typed
    version: i.fields.getTextInputValue('version').trim(),
    owners: ownerOf(tagId),
  });
  return i.editReply(await draftPayload(pid));
}

async function buttonAnn(i, action, pid) {
  const p = getPending(pid);
  if (!p) return i.update({ content: 'This draft is gone.', embeds: [], components: [] });
  if (!canManage(i.member, ownerOf(p.tagId))) return deny(i);
  if (action === 'edit') {
    const modal = new ModalBuilder().setCustomId(`annedit:${pid}`).setTitle('Edit announcement').addComponents(
      input('bugfixes', 'Bug fixes (one per line)', TextInputStyle.Paragraph, p.bugfixes.join('\n')),
      input('updates', 'Updates (one per line)', TextInputStyle.Paragraph, p.updates.join('\n')),
      input('version', 'Version (optional)', TextInputStyle.Short, p.version));
    return i.showModal(modal);
  }
  if (action === 'later') {
    snooze(pid);
    return i.update({ content: `${E.update} **LATER** · I will offer this again after 3 more fixes.`, embeds: [], components: [] });
  }
  await i.deferUpdate();
  const r = await postAnnouncement(pid);
  if (!r.ok) return i.followUp({ content: r.msg, flags: EPH });
  return i.message.edit({ content: `${E.fixed} **POSTED** · ${r.url}`, embeds: [], components: [] });
}

async function modalAnnEdit(i, pid) {
  const p = getPending(pid);
  if (!p) return i.reply({ content: 'This draft is gone.', flags: EPH });
  const fromMessage = i.isFromMessage();
  if (fromMessage) await i.deferUpdate(); else await i.deferReply();
  // Only update lines the dev changed get rewritten again; untouched ones keep their wording.
  const typed = lines(i.fields.getTextInputValue('updates'));
  const updates = typed.join('\n') === p.updates.join('\n') ? p.updates : await polishDevUpdates(getGame(p.tagId).name, typed);
  setPending(pid, {
    ...p, bugfixes: lines(i.fields.getTextInputValue('bugfixes')), updates,
    version: i.fields.getTextInputValue('version').trim(),
  });
  if (fromMessage) return i.message.edit(await draftPayload(pid));
  return i.editReply(await draftPayload(pid));
}

async function buttonBug(i, id, status) {
  const bug = bugById(Number(id));
  if (!bug) return deny(i, 'That bug no longer exists.');
  await i.deferReply({ flags: EPH });
  const { done, skipped } = await applyStatus([bug.id], status, i.member);
  return i.editReply({ content: done.length ? `#${bug.id} → ${status.replace('_', ' ')}` : `Could not change #${bug.id}: ${skipped[0] || 'unknown'}` });
}

// Dev note on a bug: the bot works out the game (and device/severity), retags the post and moves the bug to the right board.
async function modalNote(i, bugId) {
  const bug = bugById(Number(bugId));
  if (!bug) return deny(i, 'That bug no longer exists.');
  if (!canManage(i.member, ownersFor(bug.game_tag_id, bug.game_name))) return deny(i);
  await i.deferReply({ flags: EPH });
  const note = i.fields.getTextInputValue('note').trim();
  let r;
  try {
    r = await interpretNote({ note, title: bug.title, summary: bug.summary || '', games: gameTags().map((t) => t.name) });
  } catch (e) {
    console.error('interpretNote', e.message);
    return i.editReply('I could not read that note right now. Try again in a minute.');
  }
  const gameTag = findGameTag(r.game);
  const patch = { note };
  if (gameTag) { patch.game_tag_id = gameTag.id; patch.game_name = gameTag.name; }
  if (r.severity) patch.severity = r.severity;
  updateBug(bug.id, patch);
  const thread = await fetchChannel(bug.thread_id);
  if (thread) await setTags(thread, { game: gameTag?.id, device: findDeviceTag(r.device)?.id, replaceGame: true });
  if (!gameTag) {
    scheduleBoards();
    return i.editReply(`Saved your note on #${bug.id}, but it does not say which game. Name the game directly, like "Vyra Station".`);
  }
  await routeBug(bugById(bug.id));
  const owners = ownersFor(gameTag.id, gameTag.name);
  return i.editReply(`✅ #${bug.id} is now **${gameTag.name}**${r.device ? ` · ${r.device}` : ''}${r.severity ? ` · ${r.severity}` : ''}. ` +
    (owners.length ? `Sent to ${owners.map((o) => `<@${o}>`).join(' ')}.` : 'Nobody has claimed that game yet, so it stays in Unclaimed.'));
}

// Status change on an exploit card. The reporter's post was deleted, so every change is also sent to them as a DM.
async function buttonExploit(i, bugId, action) {
  const bug = bugById(Number(bugId));
  if (!bug) return deny(i, 'That report no longer exists.');
  if (!canManage(i.member, ownersFor(bug.game_tag_id, bug.game_name))) return deny(i);
  await i.deferUpdate();
  const next = { investigating: 'exploit_investigating', fixed: 'exploit_fixed', closed: 'exploit_closed' }[action];
  if (!next) return;
  updateBug(bug.id, { status: next });
  const text = {
    investigating: `${E.investigating} **INVESTIGATING**
A developer is looking at your report "${bug.title}". I will message you when it is fixed.`,
    fixed: `${E.fixed} **FIXED**
The problem in your report "${bug.title}" is fixed. Thank you for reporting it safely.`,
    closed: `${E.notbug} **CLOSED**
We looked at your report "${bug.title}" and it is not an exploit we can act on. Thanks for telling us.`,
  }[action];
  const dmOk = await dm(bug.reporter_id, text);
  const card = EmbedBuilder.from(i.message.embeds[0]);
  describeEmbed(card, exploitStatusLine(next, false, dmOk));
  return i.editReply({ embeds: [card], components: exploitButtons(bug.id, next) });
}

async function buttonStrike(i, action, logId) {
  if (!canConfirm(i.member)) return deny(i, 'Only developers can confirm or dismiss this.');
  await i.deferUpdate();
  const res = await resolveStrike(Number(logId), action === 'confirm', i.user.id);
  return i.editReply({ content: `${i.message.content}\n\n${res}`, components: [], allowedMentions: { parse: [] } });
}

// Sends the transcript as a .md file (attach or paste into an AI agent chat), plus a copyable block when short.
async function buttonTranscript(i, id) {
  await i.deferReply({ flags: EPH });
  const t = await singleTranscript(Number(id));
  if (!t) return i.editReply('That bug no longer exists.');
  const how = 'Paste the text into your AI agent chat. For images and video frames, attach the files from the zip, or unzip it into your project and tell the agent to read the folder.';
  const content = t.inline ? `\`\`\`md\n${t.inline}\n\`\`\`` : (t.note ? `${t.note}\n${how}` : 'Transcript attached. Paste it into your AI agent chat.');
  return i.editReply({ content, files: t.files });
}

// Step 1: pick a game (or all games) from the open bugs on this board.
async function buttonTranscriptAll(i, key) {
  const bugs = openBugsFor(key);
  if (!bugs.length) return i.reply({ content: 'No open bugs.', flags: EPH });
  const by = new Map();
  for (const b of bugs) {
    const k = b.game_tag_id || 'none';
    const e = by.get(k) || { name: b.game_name || 'Unknown game', n: 0 };
    e.n++;
    by.set(k, e);
  }
  const options = [{ label: `All games (${bugs.length})`, value: 'all' },
    ...[...by].slice(0, 24).map(([k, e]) => ({ label: `${e.name} (${e.n})`.slice(0, 100), value: k }))];
  const menu = new StringSelectMenuBuilder().setCustomId(`trgame:${key}`).setPlaceholder('Pick a game').addOptions(options);
  return i.reply({ content: 'Which game do you want the transcript for?', components: [new ActionRowBuilder().addComponents(menu)], flags: EPH });
}

async function gameTranscriptReply(key, game) {
  const t = await boardTranscript(key, game);
  if (!t.count) return { content: 'No open bugs for that game.' };
  return {
    content: `**${t.count}** open bug(s)${game === 'all' ? '' : ` for **${t.name}**`} in ${t.files.length} zip file(s), about ${t.tokens.toLocaleString()} tokens of text. Each bug has its own folder with \`transcript.md\`${t.hasMedia ? ', screenshots and video frames' : ''}. Unzip it into your project and tell your agent to read the folder.` +
      (t.cut ? `\n⚠️ ${t.cut} more part(s) did not fit in one message. Use the per-bug buttons for those.` : ''),
    files: t.files,
  };
}

// Step 2: build it.
async function selectTranscript(i, key) {
  await i.update({ content: 'Building the transcript…', components: [] });
  return i.editReply(await gameTranscriptReply(key, i.values[0]));
}

// "Whole game" button inside the bug page.
async function buttonGameTranscript(i, key, game) {
  await i.deferReply({ flags: EPH });
  return i.editReply(await gameTranscriptReply(key, game));
}

export async function handleInteraction(i) {
  if (i.isAutocomplete()) return autocomplete(i);
  if (i.isChatInputCommand()) {
    if (i.commandName === 'bug') return commandBug(i); // testers have no dev role, so it skips the dev-only gate below
    if (level(i.member) === 'jr' || level(i.member) === 'none') return deny(i);
    switch (i.commandName) {
      case 'config': return i.options.getSubcommand() === 'set' ? configSet(i) : configShow(i);
      case 'update': return commandUpdate(i);
      case 'strikes': {
        const u = i.options.getUser('user');
        const { count, log } = strikeInfo(u.id);
        const rows = log.map((l) => `• <t:${Math.floor(l.at / 1000)}:d> ${l.step} (${l.state}): ${l.reason}`).join('\n');
        return i.reply({ content: `<@${u.id}> has **${count}** strike(s).\n${rows}`, flags: EPH, allowedMentions: { parse: [] } });
      }
      case 'pardon': {
        const u = i.options.getUser('user');
        const c = await pardon(u.id);
        return i.reply({ content: `Removed one strike from <@${u.id}>. They now have ${c}.`, flags: EPH, allowedMentions: { parse: [] } });
      }
      case 'pings': {
        const b = i.options.getString('bugs');
        const x = i.options.getString('exploits');
        const prefs = b || x ? setPrefs(i.user.id, { bugs: b ? b === 'on' : undefined, exploits: x ? x === 'on' : undefined }) : getPrefs(i.user.id);
        return i.reply({
          content: `${E.status} **YOUR PINGS**\n• New bugs on your games: **${prefs.bugs ? 'on' : 'off'}**\n• Exploit reports: **${prefs.exploits ? 'on' : 'off'}**\nChange them with \`/pings bugs:off exploits:on\`.`,
          flags: EPH,
        });
      }
      case 'preview': {
        if (level(i.member) !== 'admin') return deny(i);
        await i.deferReply({ flags: EPH });
        const n = await postPreviews(i.options.getString('what') || 'all');
        return i.editReply(`Posted ${n} preview message(s) in <#${cfg.testId}>.`);
      }
      case 'release': return commandRelease(i);
      case 'unrelease': return commandRelease(i, true);
      case 'games': return commandGames(i);
      case 'botrules':
        if (level(i.member) !== 'admin') return deny(i);
        await i.channel.send({ embeds: [rulesEmbed()] });
        return i.reply({ content: 'Posted.', flags: EPH });
    }
  }
  if (i.isButton()) {
    const [kind, a, b] = i.customId.split(':');
    if (kind === 'bug') return buttonBug(i, a, b);
    if (kind === 'ann') return buttonAnn(i, a, Number(b));
    if (kind === 'strike') return buttonStrike(i, a, b);
    if (kind === 'exp') return buttonExploit(i, a, b); // status buttons on a high-priority exploit card
    if (kind === 'v') return handleView(i);
    if (kind === 'flp') return logPage(i, a, b);
    if (kind === 'trg') return buttonGameTranscript(i, a, b);
    if (kind === 'tr') return buttonTranscript(i, a);
    if (kind === 'trall') return buttonTranscriptAll(i, a);
  }
  if (i.isStringSelectMenu()) {
    const [kind, a] = i.customId.split(':');
    if (kind === 'trgame') return selectTranscript(i, a);
    if (kind === 'bd') return openGame(i, a, i.values[0]);
    if (kind === 'fl') return openLog(i, i.values[0]);
    if (kind === 'flt') return sendFixTranscript(i, i.values[0]);
    if (kind === 'trpick') {
      await i.deferReply({ flags: EPH });
      i.message.edit({ components: boardComponents(a) }).catch(() => {}); // resets the dropdown
      return i.editReply(await gameTranscriptReply(a, i.values[0]));
    }
  }
  if (i.isModalSubmit()) {
    const [kind, a, b] = i.customId.split(':');
    if (kind === 'tb') return modalBug(i, a, b);
    if (kind === 'upd') return modalUpdate(i, a);
    if (kind === 'note') return modalNote(i, a);
    if (kind === 'annedit') return modalAnnEdit(i, Number(a));
  }
}
