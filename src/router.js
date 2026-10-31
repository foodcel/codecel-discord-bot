import { cfg } from './env.js';
import { getMember } from './ctx.js';
import { db, kvSet, bugByThread } from './db.js';
import { level } from './perms.js';
import { parseCommand } from './parse.js';
import { applyStatus } from './fixes.js';
import { handleBugMessage } from './intake.js';

async function handleDev(msg) {
  const member = msg.member ?? await getMember(msg.author.id);
  const lvl = level(member);
  if (lvl === 'jr') {
    await msg.delete().catch(() => {});
    const n = await msg.channel.send(`<@${msg.author.id}> Jr developers can't write in the dev board.`).catch(() => null);
    if (n) setTimeout(() => n.delete().catch(() => {}), 6000);
    return;
  }
  if (lvl !== 'admin' && lvl !== 'dev') return;
  const cmd = parseCommand(msg.content);
  if (!cmd || !cmd.ids.length) return;
  const { done, skipped } = await applyStatus(cmd.ids, cmd.status, member);
  await msg.react(done.length ? '✅' : '❌').catch(() => {});
  if (skipped.length) await msg.reply({ content: `Skipped: ${skipped.join(', ')}`, allowedMentions: { repliedUser: false } }).catch(() => {});
}

async function handleBugThread(msg) {
  const bug = bugByThread(msg.channel.id);
  if (bug) db.prepare('UPDATE bugs SET last_msg_id=? WHERE id=?').run(msg.id, bug.id);
  if (msg.author.bot) return;
  const member = msg.member ?? await getMember(msg.author.id);
  if (['admin', 'dev'].includes(level(member))) {
    const cmd = parseCommand(msg.content);
    if (cmd) {
      const ids = cmd.ids.length ? cmd.ids : (bug ? [bug.id] : []);
      if (ids.length) {
        const { done } = await applyStatus(ids, cmd.status, member);
        if (done.length) { await msg.react('✅').catch(() => {}); return; }
      }
    }
  }
  handleBugMessage(msg);
}

export async function handleMessage(msg) {
  if (!msg.guild || !msg.channel.isThread()) return;
  const ch = msg.channel;
  if (ch.parentId === cfg.devForumId) {
    kvSet(`devlast:${ch.id}`, msg.id);
    if (msg.author.bot) return;
    return handleDev(msg);
  }
  if (ch.parentId === cfg.bugsId || (cfg.testingId && ch.parentId === cfg.testingId)) return handleBugThread(msg);
}
