import { ctx, fetchChannel } from './ctx.js';
import { db, now, bugById, bugByThread, updateBug } from './db.js';
import { setTags } from './tags.js';
import { scheduleBoards } from './devboard.js';
import { E } from './ui.js';

async function exec(t) {
  if (t.kind === 'delete_thread') {
    const bug = bugByThread(t.target);
    if (bug && !['fixed', 'duplicate'].includes(bug.status)) return; // reopened meanwhile
    const thread = await fetchChannel(t.target);
    if (thread) await thread.delete('Fixed or duplicate bug, 24h passed').catch((e) => console.error('delete thread', e.message));
    if (bug) updateBug(bug.id, { deleted: 1 });
    scheduleBoards();
  } else if (t.kind === 'unban') {
    await ctx.guild.members.unban(t.target, '7-day ban finished').catch(() => {});
  } else if (t.kind === 'stale') {
    const bug = bugByThread(t.target);
    if (!bug || bug.status !== 'needs_info') return;
    const thread = await fetchChannel(t.target);
    updateBug(bug.id, { status: 'closed' });
    if (thread) {
      await setTags(thread, { status: null });
      await thread.send(`${E.warn} **CLOSED** · The missing details never came in. Post a new report with everything filled in and it will be looked at. <@${bug.reporter_id}>`).catch(() => {});
      await thread.setArchived(true).catch(() => {});
    }
  }
}

// Overdue timers also run on startup, so a PC that was off catches up.
export async function runTimers() {
  const due = db.prepare('SELECT * FROM timers WHERE run_at<=? ORDER BY run_at').all(now());
  for (const t of due) {
    db.prepare('DELETE FROM timers WHERE id=?').run(t.id);
    try { await exec(t); } catch (e) { console.error('timer', t.kind, e); }
  }
}
