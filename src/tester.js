import { ActionRowBuilder, AttachmentBuilder, ChannelType, MessageFlags, ModalBuilder, TextInputBuilder, TextInputStyle } from 'discord.js';
import { cfg } from './env.js';
import { fetchChannel } from './ctx.js';
import { db, now, bugById, updateBug } from './db.js';
import { level } from './perms.js';
import { tagName } from './tags.js';
import { summarizeTesterReport } from './ai.js';
import { routeBug } from './devboard.js';
import { uploadLimit } from './transcript.js';
import { E, SEVERITY, columns, cut, describe, flat, head, labeled, sentence } from './ui.js';

const EPH = MessageFlags.Ephemeral;

// /bug takes up to 10 screenshots and 5 videos: screenshot, screenshot_2 ... screenshot_10, video, video_2 ... video_5
export const ATTACH = {
  screenshots: Array.from({ length: 10 }, (_, k) => (k ? `screenshot_${k + 1}` : 'screenshot')),
  videos: Array.from({ length: 5 }, (_, k) => (k ? `video_${k + 1}` : 'video')),
};
const safe = (n) => String(n).replace(/[^\w.\-]+/g, '_').slice(0, 60);

// Attachments chosen on the slash command must survive until the form is submitted.
const pending = new Map(); // token -> { files, t }
const keep = (files) => {
  const token = Math.random().toString(36).slice(2, 10);
  for (const [k, v] of pending) if (Date.now() - v.t > 15 * 60000) pending.delete(k);
  pending.set(token, { files, t: Date.now() });
  return token;
};

// Testers, plus devs and admins. Only inside the tester channel.
export const isTester = (m) => !!m && (level(m) !== 'none' || cfg.testerRoles.some((r) => m.roles.cache.has(r)));

export async function commandBug(i) {
  if (!cfg.testingId) return i.reply({ content: 'Tester reports are not set up.', flags: EPH });
  if (!isTester(i.member)) return i.reply({ content: 'This command is for testers.', flags: EPH });
  if (i.channelId !== cfg.testingId) return i.reply({ content: `Please use /bug in <#${cfg.testingId}>.`, flags: EPH });
  const tagId = i.options.getString('game');
  if (!tagName(tagId)) return i.reply({ content: 'Pick a game from the list.', flags: EPH });
  const files = [...ATTACH.screenshots, ...ATTACH.videos].map((n) => i.options.getAttachment(n)).filter(Boolean)
    .map((a) => ({ url: a.url, name: a.name, size: a.size, type: a.contentType || '' }));
  const token = keep(files);
  const field = (id, label, style, required, max, placeholder) => new ActionRowBuilder().addComponents(
    new TextInputBuilder().setCustomId(id).setLabel(label).setStyle(style).setRequired(required).setMaxLength(max)
      .setPlaceholder(placeholder));
  return i.showModal(new ModalBuilder().setCustomId(`tb:${tagId}:${token}`).setTitle(`Bug report · ${tagName(tagId)}`.slice(0, 45)).addComponents(
    field('title', 'Short title', TextInputStyle.Short, true, 80, 'e.g. Car falls through the map'),
    field('what', 'What happened', TextInputStyle.Paragraph, true, 1000, 'Describe the bug'),
    field('steps', 'Steps to reproduce', TextInputStyle.Paragraph, true, 1000, '1. ... 2. ... 3. ...'),
    field('expected', 'What should happen (optional)', TextInputStyle.Paragraph, false, 500, ''),
    field('device', 'Device / platform / build (optional)', TextInputStyle.Short, false, 60, 'e.g. PC, PS5, iPhone 14')));
}

// The report card posted inside the tester thread.
export function testerReportEmbed(bug, form, testerId, extra = {}) {
  const e = flat().setTitle(head('🧪', `#${bug.id} · ${bug.game_name}`));
  describe(e, `### ${bug.title}\n${bug.summary || ''}`);
  columns(e, [
    { name: head(E.user, 'Tester'), lines: [`<@${testerId}>`] },
    { name: head(E.severity, 'Severity'), lines: [SEVERITY[bug.severity] || '?'] },
    { name: head(E.device, 'Device'), lines: [form.device || 'Not given'] },
  ]);
  labeled(e, head(E.note, 'What happened'), sentence(form.what));
  labeled(e, head('🔁', 'Steps to reproduce'), form.steps);
  if (form.expected) labeled(e, head(E.fixed, 'Should happen'), sentence(form.expected));
  if (extra.tooBig?.length) labeled(e, head(E.video, 'Too big to attach'), `${extra.tooBig.join('\n')}\nPost the file in this thread.`);
  if (extra.image) e.setImage(`attachment://${extra.image}`);
  e.setFooter({ text: 'Tester report · devs reply in this thread' }).setTimestamp(bug.created_at);
  return e;
}

async function download(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
}

// Form submitted: make the thread, save the bug, send it to the dev board.
export async function modalBug(i, tagId, token) {
  await i.deferReply({ flags: EPH });
  const game = tagName(tagId);
  const form = {
    title: i.fields.getTextInputValue('title').trim(), what: i.fields.getTextInputValue('what').trim(),
    steps: i.fields.getTextInputValue('steps').trim(), expected: i.fields.getTextInputValue('expected').trim(),
    device: i.fields.getTextInputValue('device').trim(),
  };
  const chosen = pending.get(token)?.files ?? [];
  pending.delete(token);

  let ai = { title: form.title, summary: cut(form.what, 200), severity: 'medium' };
  try { ai = await summarizeTesterReport({ game, ...form }); } catch (e) { console.error('summarizeTesterReport', e.message); }

  // Re-upload the files into the thread so they never expire. Discord allows 10 files and one upload limit per message,
  // so they go out in batches. Files that are too big or fail become links on the card.
  const limit = uploadLimit();
  const batches = [[]];
  const tooBig = [];
  const placed = [];
  let used = 0;
  for (const [n, f] of chosen.entries()) {
    if (f.size > limit) { tooBig.push(`[${f.name}](${f.url})`); continue; }
    let cur = batches[batches.length - 1];
    if (cur.length >= 10 || used + f.size > limit) { cur = []; batches.push(cur); used = 0; }
    try {
      const name = `${n + 1}-${safe(f.name)}`;
      cur.push(new AttachmentBuilder(await download(f.url), { name }));
      placed.push({ f, name, first: batches.length === 1 });
      used += f.size;
    } catch { tooBig.push(`[${f.name}](${f.url})`); }
  }
  const firstImage = placed.find((p) => p.first && /^image\/(png|jpe?g|gif|webp)/.test(p.f.type));

  const testing = await fetchChannel(cfg.testingId);
  const thread = await testing.threads.create({
    name: cut(ai.title || form.title, 90), type: ChannelType.PublicThread, autoArchiveDuration: 10080,
    reason: `Tester report by ${i.user.tag}`,
  });
  const body = `What happened: ${form.what}\nSteps: ${form.steps}${form.expected ? `\nShould happen: ${form.expected}` : ''}`;
  const id = db.prepare(`INSERT INTO bugs(thread_id,reporter_id,game_tag_id,game_name,title,summary,severity,status,created_at,
    device,body,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)`)
    .run(thread.id, i.user.id, tagId, game, ai.title || form.title, ai.summary, ai.severity, 'new', now(), form.device || null, body, 'tester').lastInsertRowid;
  const bug = bugById(id);
  await thread.setName(cut(`#${id} ${bug.title}`, 100)).catch(() => {});
  const sent = await thread.send({
    embeds: [testerReportEmbed(bug, form, i.user.id, { tooBig, image: firstImage ? firstImage.name : null })],
    files: batches[0], allowedMentions: { parse: [] },
  });
  for (const [k, extra] of batches.slice(1).entries()) {
    if (extra.length) await thread.send({ content: `📎 **MORE FILES** · ${k + 2} of ${batches.length}`, files: extra, allowedMentions: { parse: [] } });
  }
  updateBug(id, { last_msg_id: sent.id });
  await routeBug(bugById(id)); // ghost ping to the owner and the dev board
  return i.editReply(`${E.fixed} **SENT** · #${id} went to the ${game} developer. Follow it here: ${thread.url}`);
}
