import { ChannelFlags } from 'discord.js';
import { ctx, fetchChannel, getMember, modlog, dm, threadLink, sleep } from './ctx.js';
import { cfg } from './env.js';
import { db, now, bugById, bugByThread, updateBug, addTimer, cancelTimers } from './db.js';
import { analyzeReport, stillBroken } from './ai.js';
import { gameTags, findGameTag, findDeviceTag, threadGameTag, tagName, setTags } from './tags.js';
import { postExploit, routeBug } from './devboard.js';
import { strikeUser } from './strikes.js';
import { isStaff, level } from './perms.js';
import { ownersFor } from './bounty.js';
import { reopen } from './fixes.js';
import { E, SEVERITY, columns, describe, flat, head, section } from './ui.js';

const DAY = 86400000;
const CONFIDENT = 0.85;

async function fetchStarter(thread) {
  for (let i = 0; i < 4; i++) {
    const m = await thread.fetchStarterMessage().catch(() => null);
    if (m) return m;
    await sleep(1500);
  }
  return null;
}

async function gather(thread, bug) {
  const msgs = await thread.messages.fetch({ limit: 50 });
  const mine = [...msgs.values()].filter((m) => m.author.id === bug.reporter_id)
    .sort((a, b) => a.createdTimestamp - b.createdTimestamp);
  const atts = mine.flatMap((m) => [...m.attachments.values()]);
  return {
    text: mine.map((m) => m.content).filter(Boolean).join('\n---\n'),
    images: atts.filter((a) => /^image\/(png|jpe?g|gif|webp)/.test(a.contentType || '')).map((a) => a.url),
    videos: atts.filter((a) => (a.contentType || '').startsWith('video/')).map((a) => a.name),
  };
}

export async function intakeThread(thread, { silent = false } = {}) {
  if (bugByThread(thread.id)) return;
  if (thread.flags?.has(ChannelFlags.Pinned)) return;
  const starter = await fetchStarter(thread);
  if (!starter || starter.author.bot) return;
  const res = db.prepare('INSERT INTO bugs(thread_id,reporter_id,title,status,created_at,last_msg_id) VALUES(?,?,?,?,?,?)')
    .run(thread.id, starter.author.id, thread.name, 'new', now(), thread.lastMessageId ?? starter.id);
  await analyzeAndAct(bugById(res.lastInsertRowid), thread, { silent });
}

export async function analyzeAndAct(bug, thread, { silent = false, followup = false } = {}) {
  const report = await gather(thread, bug);
  const games = gameTags().map((t) => t.name);
  const picked = thread.appliedTags.map(tagName).filter(Boolean);
  const known = db.prepare(`SELECT id,title,summary,status,game_name FROM bugs
    WHERE id<>? AND status IN ('new','needs_info','investigating','fixing','fixed') AND deleted IN (0,1)
    ORDER BY id DESC LIMIT 40`).all(bug.id);
  let a;
  try {
    a = await analyzeReport({ title: thread.name.replace(/^#\d+\s+/, ''), text: report.text, tagNames: picked, games, images: report.images, videos: report.videos, known });
  } catch (e) {
    console.error('analyze failed:', e.message);
    return; // stays status=new, routed=0; catch-up retries later
  }

  const gameTag = threadGameTag(thread) || findGameTag(a.game);
  const deviceTag = findDeviceTag(a.device);
  updateBug(bug.id, {
    game_tag_id: gameTag?.id ?? null, game_name: gameTag?.name ?? a.game ?? null,
    title: a.title || bug.title, summary: a.summary, severity: a.severity,
  });
  bug = bugById(bug.id);
  const reporterMember = await getMember(bug.reporter_id);
  const staffReporter = isStaff(reporterMember);

  // 1. Exploit: never leave it public.
  if (a.exploit && !staffReporter) {
    // The post is deleted, so the reporter is told it was received and why, and gets a message again when a dev changes its status.
    let dmOk = true;
    if (!silent) {
      updateBug(bug.id, { status: 'exploit', deleted: 1 });
      dmOk = await dm(bug.reporter_id,
        `${E.lock} **REPORT RECEIVED**\nThanks for telling us. Your report "${bug.title}" was removed from the channel on purpose, because it explains how to abuse a bug and others could copy it. The developers have it now. I will message you here when it is fixed, so please do not post it again.`);
    }
    await postExploit(bug, report.text, silent, dmOk); // straight into the owner's dev board as a high-priority card
    if (!silent) await thread.delete('Possible exploit report').catch((e) => console.error('delete exploit', e.message));
    return;
  }

  // 2. Troll.
  if (a.troll.is_troll && a.troll.confidence >= CONFIDENT && !silent) {
    updateBug(bug.id, { status: 'not_a_bug' });
    await setTags(thread, { game: gameTag?.id, status: 'not_a_bug' });
    await thread.send(`${E.warn} **CLOSED** · Fake or abusive reports lead to strikes.`).catch(() => {});
    await thread.setArchived(true).catch(() => {});
    if (!followup) await strikeUser(bug.reporter_id, a.troll.reason || 'Trolling in bug reports', bug.id);
    return;
  }

  // 3. Duplicate.
  const dup = a.duplicate_of && a.duplicate_of !== bug.id ? bugById(a.duplicate_of) : null;
  if (dup && !silent) {
    updateBug(bug.id, { status: 'duplicate', dup_of: dup.id });
    const ref = dup.deleted ? `#${dup.id} "${dup.title}"` : `[#${dup.id} ${dup.title}](${threadLink(dup.thread_id)})`;
    const text = dup.status === 'fixed'
      ? `<@${bug.reporter_id}> ${E.duplicate} **DUPLICATE** · already fixed on <t:${Math.floor((dup.fixed_at || now()) / 1000)}:D>: ${ref}.`
      : `<@${bug.reporter_id}> ${E.duplicate} **DUPLICATE** · of ${ref}. Please add any extra details there. This post is removed in 24 hours.`;
    await setTags(thread, { game: gameTag?.id, device: deviceTag?.id, status: 'duplicate' });
    await thread.send({ content: text, allowedMentions: { users: [bug.reporter_id] } }).catch(() => {});
    await thread.setArchived(true).catch(() => {});
    addTimer('delete_thread', thread.id, now() + DAY);
    return;
  }

  // 4. Missing info.
  const incomplete = !a.complete || !(gameTag || a.game);
  if (incomplete && !silent) {
    const asks = bug.asks + 1;
    updateBug(bug.id, { status: 'needs_info', asks });
    await setTags(thread, { game: gameTag?.id, device: deviceTag?.id, status: 'needs_info' });
    const missing = a.missing.length ? a.missing : ['More detail about what happened'];
    if (!gameTag && !a.missing.some((m) => /game/i.test(m))) missing.unshift('Which game');
    let msg = `<@${bug.reporter_id}> ❓ **NEEDS INFO**\n${a.reply || 'Thanks for the report! A few details are missing.'}\n\n**STILL NEEDED**\n${missing.map((m) => `• ${m}`).join('\n')}`;
    if (a.multiple_bugs) msg += '\n\nPlease post each bug separately.';
    if (a.personal_info) msg += `\n\n${E.warn} Your screenshot may show personal information. Please hide it.`;
    msg += '\n\nReply in this post and I will check again.';
    await thread.send({ content: msg, allowedMentions: { users: [bug.reporter_id] } }).catch(() => {});
    cancelTimers('stale', thread.id);
    addTimer('stale', thread.id, now() + 3 * DAY);
    return;
  }

  // 5. Complete (or silent import).
  const wasAsked = bug.status === 'needs_info';
  cancelTimers('stale', thread.id);
  updateBug(bug.id, { status: 'new' });
  if (!silent) {
    await setTags(thread, { game: gameTag?.id, device: deviceTag?.id, status: null });
    if (!/^#\d+\s/.test(thread.name)) await thread.setName(`#${bug.id} ${thread.name}`.slice(0, 100)).catch(() => {});
    let msg = `${E.new} **LOGGED** · #${bug.id} is sent to the developer. ${wasAsked ? 'Thanks, that covers it.' : 'Thanks for the report!'}`;
    if (a.personal_info) msg += `\n${E.warn} Your screenshot may show personal information. Please hide it.`;
    await thread.send(msg).catch(() => {});
  } else if (gameTag) {
    // silent import keeps old posts untouched but still numbers them in the DB only
  }
  await routeBug(bugById(bug.id), { silent });
}

// Debounced handling of messages inside #bugs posts.
const timers = new Map();
export function handleBugMessage(msg) {
  const bug = bugByThread(msg.channel.id);
  if (!bug) return;
  db.prepare('UPDATE bugs SET last_msg_id=? WHERE id=?').run(msg.id, bug.id);
  if (msg.author.bot || msg.author.id !== bug.reporter_id) return;
  if (bug.status === 'needs_info') {
    clearTimeout(timers.get(bug.id));
    timers.set(bug.id, setTimeout(async () => {
      timers.delete(bug.id);
      const fresh = bugById(bug.id);
      if (fresh?.status === 'needs_info') await analyzeAndAct(fresh, msg.channel, { followup: true }).catch(console.error);
    }, 15000));
  } else if (bug.status === 'fixed' && !bug.deleted && msg.content) {
    stillBroken(msg.content).then((yes) => yes && reopen(bugById(bug.id))).catch(console.error);
  }
}
