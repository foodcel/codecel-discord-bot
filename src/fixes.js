import { cfg } from './env.js';
import { fetchChannel, threadLink } from './ctx.js';
import { bugById, updateBug, addTimer, cancelTimers, now } from './db.js';
import { ownersFor } from './bounty.js';
import { canManage } from './perms.js';
import { setTags, threadGameTag, tagName } from './tags.js';
import { scheduleBoards, routeBug } from './devboard.js';
import { maybeOffer } from './announce.js';
import { snapshotBug } from './fixlog.js';
import { E } from './ui.js';

const DAY = 86400000;

const NOTE = {
  investigating: `${E.investigating} **INVESTIGATING** · A developer is looking into this.`,
  fixing: `${E.fixing} **FIXING** · A fix is in progress.`,
  not_a_bug: `${E.notbug} **NOT A BUG** · Reviewed as intended behavior or a feature request. Thanks for reporting! Suggestions go in the suggestions channel.`,
  duplicate: `${E.duplicate} **DUPLICATE** · This was already reported. Please follow the original report.`,
};

export async function markFixed(bug, actorId) {
  updateBug(bug.id, { status: 'fixed', fixed_at: now(), fixed_by: actorId });
  // Keep the conversation and screenshots: the post is deleted in 24h but the fix log still offers a transcript.
  snapshotBug(bugById(bug.id)).catch((e) => console.error('snapshot', e.message));
  const thread = bug.deleted ? null : await fetchChannel(bug.thread_id);
  if (thread) {
    await setTags(thread, { status: 'fixed' });
    const starter = await thread.fetchStarterMessage().catch(() => null);
    let extra = [];
    const eyes = starter?.reactions.cache.get('👀');
    if (eyes) {
      const users = await eyes.users.fetch({ limit: 11 }).catch(() => null);
      extra = [...(users?.values() ?? [])].filter((u) => !u.bot && u.id !== bug.reporter_id).slice(0, 10).map((u) => u.id);
    }
    const pings = [bug.reporter_id, ...extra];
    await thread.send({
      content: `${pings.map((id) => `<@${id}>`).join(' ')}\n${E.fixed} **FIXED** · ${bug.title} (#${bug.id}). Thanks for reporting!\n` +
        `This post closes now and is deleted in 24 hours. If it is still broken, reply here before then.`,
      allowedMentions: { users: pings },
    }).catch((e) => console.error('fixed msg', e.message));
    await thread.setArchived(true).catch(() => {});
    cancelTimers('delete_thread', bug.thread_id);
    addTimer('delete_thread', bug.thread_id, now() + DAY);
  }
  scheduleBoards();
  maybeOffer(bug.game_tag_id).catch((e) => console.error('offer', e.message));
}

export async function setBugStatus(bug, status, actorId) {
  if (status === 'fixed') return markFixed(bug, actorId);
  updateBug(bug.id, { status });
  const thread = bug.deleted ? null : await fetchChannel(bug.thread_id);
  if (thread) {
    await setTags(thread, { status: status === 'new' ? null : status });
    if (NOTE[status]) await thread.send(NOTE[status]).catch(() => {});
    if (status === 'not_a_bug' || status === 'duplicate') await thread.setArchived(true).catch(() => {});
  }
  scheduleBoards();
}

// Reporter said "still broken" inside the 24h window.
export async function reopen(bug) {
  cancelTimers('delete_thread', bug.thread_id);
  updateBug(bug.id, { status: 'new', fixed_at: null, announced: 0 });
  const thread = await fetchChannel(bug.thread_id);
  if (thread) {
    await setTags(thread, { status: null });
    await thread.send(`${E.duplicate} **REOPENED** · #${bug.id} is back on the board. The developer has been notified.`).catch(() => {});
  }
  await routeBug(bugById(bug.id));
  maybeOffer(bug.game_tag_id).catch((e) => console.error('offer', e.message)); // drops it from a pending draft
}

// ids: bug numbers. Returns a short summary for the dev.
export async function applyStatus(ids, status, member) {
  const done = [];
  const skipped = [];
  for (const id of ids) {
    const bug = bugById(id);
    if (!bug || ['removed', 'closed'].includes(bug.status) || bug.status.startsWith('exploit')) { skipped.push(`#${id} not found`); continue; }
    const owners = ownersFor(bug.game_tag_id, bug.game_name);
    if (!canManage(member, owners)) { skipped.push(`#${id} not your game`); continue; }
    try { await setBugStatus(bug, status, member.id); done.push(`#${id}`); }
    catch (e) { console.error('applyStatus', e); skipped.push(`#${id} error`); }
  }
  return { done, skipped };
}
