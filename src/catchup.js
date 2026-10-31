import { cfg } from './env.js';
import { fetchChannel } from './ctx.js';
import { db, now, kvGet, kvSet, bugByThread } from './db.js';
import { runTimers } from './timers.js';
import { intakeThread, analyzeAndAct } from './intake.js';
import { handleMessage } from './router.js';
import { refreshAllBoards } from './devboard.js';

const byTime = (a, b) => a.createdTimestamp - b.createdTimestamp;

async function replay(thread, afterId) {
  const msgs = await thread.messages.fetch({ after: afterId, limit: 100 }).catch(() => null);
  for (const m of [...(msgs?.values() ?? [])].sort(byTime)) await handleMessage(m).catch(console.error);
}

// Runs on startup: handles everything that happened while the PC was off.
export async function catchup() {
  // The first run imports existing posts silently (no replies, no strikes, no tag changes).
  const silent = !kvGet('baseline_done');
  await runTimers();

  const forum = await fetchChannel(cfg.bugsId);
  const [active, archived] = await Promise.all([
    forum.threads.fetchActive(), forum.threads.fetchArchived({ limit: 50 }),
  ]);
  const threads = [...active.threads.values(), ...archived.threads.values()].sort(byTime);
  for (const t of threads) {
    const bug = bugByThread(t.id);
    if (!bug) { await intakeThread(t, { silent }).catch(console.error); continue; }
    if (t.lastMessageId && bug.last_msg_id && bug.last_msg_id !== t.lastMessageId) await replay(t, bug.last_msg_id);
  }

  // Tester threads: dev commands and "still broken" replies typed while the bot was off.
  const testing = cfg.testingId ? await fetchChannel(cfg.testingId) : null;
  if (testing) {
    const act = await testing.threads.fetchActive().catch(() => null);
    for (const t of act?.threads.values() ?? []) {
      const bug = bugByThread(t.id);
      if (bug && t.lastMessageId && bug.last_msg_id && bug.last_msg_id !== t.lastMessageId) await replay(t, bug.last_msg_id);
    }
  }

  // Reports whose analysis failed earlier (outage, daily cap).
  const stuck = db.prepare("SELECT * FROM bugs WHERE status='new' AND routed=0 AND deleted=0 AND source IS NOT 'tester' AND created_at>?").all(now() - 7 * 86400000);
  for (const bug of stuck) {
    const t = await fetchChannel(bug.thread_id);
    if (t) await analyzeAndAct(bug, t, { silent }).catch(console.error);
  }

  // Dev board messages typed while offline.
  const dev = await fetchChannel(cfg.devForumId);
  const devThreads = await dev.threads.fetchActive();
  for (const t of devThreads.threads.values()) {
    const last = kvGet(`devlast:${t.id}`);
    if (!last) { if (t.lastMessageId) kvSet(`devlast:${t.id}`, t.lastMessageId); continue; }
    if (t.lastMessageId && t.lastMessageId !== last) await replay(t, last);
  }

  if (silent) kvSet('baseline_done', '1');
  await refreshAllBoards();
}
