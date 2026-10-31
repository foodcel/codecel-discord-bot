import { ActionRowBuilder, ButtonBuilder, ButtonStyle } from 'discord.js';
import { E, columns, describe, flat, head, labeled, spaced, sentence } from './ui.js';
import { cfg } from './env.js';
import { ctx, dm, getMember, modlog, threadLink } from './ctx.js';
import { db, now, addTimer } from './db.js';
import { isStaff } from './perms.js';

const DAY = 86400000;
export const STEPS = ['warn', 'timeout', 'kick', 'ban7', 'permban'];
const LABEL = {
  warn: 'a warning', timeout: 'a 1-day mute', kick: 'a kick',
  ban7: 'a 7-day ban', permban: 'a permanent ban',
};

export const LADDER_TEXT = [
  '1️⃣ **Warning**',
  '2️⃣ **1-day mute**',
  '3️⃣ **Kick**',
  '4️⃣ **7-day ban**',
  '5️⃣ **Permanent ban**',
].join('\n');

const ACTION = { warn: 'Warning', timeout: '1-day mute', kick: 'Kick', ban7: '7-day ban', permban: 'Permanent ban' };

export function rulesEmbed() {
  const e = flat().setTitle(head(E.log, 'Bug report rules'));
  describe(e, 'Honest reports are always welcome, even short or incomplete ones. The bot just asks for more details.');
  // Sections are separated by one blank line instead of rule lines.
  spaced(e, head(E.warn, 'Strikes are only for'), 'Fake reports, spam, abuse, or insulting the developers.');
  spaced(e, head('🚦', 'The ladder'), `Each strike moves one step up:\n${LADDER_TEXT}`);
  spaced(e, head(E.lock, 'Kicks and bans'), 'A developer confirms every kick and ban before it happens.');
  return e;
}

// The mod-log card for one strike.
export function strikeEmbed({ userId, count, step, reason, bugId, pending }) {
  const post = bugId ? db.prepare('SELECT thread_id FROM bugs WHERE id=?').get(bugId)?.thread_id : null;
  const e = flat().setTitle(head(E.warn, `Strike ${count}`));
  describe(e, pending ? `${E.warn} **NEEDS CONFIRMATION**` : `${E.fixed} **APPLIED**`);
  columns(e, [
    { name: head(E.user, 'User'), lines: [`<@${userId}>`] },
    { name: head('🔢', 'Strike'), lines: [String(count)] },
    { name: head('🚦', 'Action'), lines: [ACTION[step]] },
  ]);
  labeled(e, head(E.note, 'Reason'), `${sentence(reason)}${post ? `\n[Open post](${threadLink(post)})` : ''}`);
  return e;
}

const stepFor = (count) => STEPS[Math.min(count, STEPS.length) - 1];

export async function strikeUser(userId, reason, bugId) {
  const member = await getMember(userId);
  if (!member) return;
  if (isStaff(member)) {
    await modlog({ content: `${E.warn} **SKIPPED** · <@${userId}> is staff (${reason}).`, allowedMentions: { parse: [] } });
    return;
  }
  db.prepare('INSERT OR IGNORE INTO strikes(user_id,count,updated_at) VALUES(?,0,?)').run(userId, now());
  db.prepare('UPDATE strikes SET count=count+1, updated_at=? WHERE user_id=?').run(now(), userId);
  const count = db.prepare('SELECT count FROM strikes WHERE user_id=?').get(userId).count;
  const step = stepFor(count);
  const heavy = step === 'kick' || step === 'ban7' || step === 'permban';
  const logId = db.prepare('INSERT INTO strike_log(user_id,step,reason,bug_id,at,state) VALUES(?,?,?,?,?,?)')
    .run(userId, step, reason, bugId ?? null, now(), heavy ? 'pending' : 'done').lastInsertRowid;
  const card = { userId, count, step, reason, bugId };

  if (!heavy) {
    await dm(userId, `${E.warn} **STRIKE ${count}** · ${ctx.guild.name}\n${reason}\nThis is ${LABEL[step]}. The next steps are:\n${LADDER_TEXT}`);
    if (step === 'timeout') {
      if (member.moderatable) await member.timeout(DAY, `Bug-report trolling: ${reason}`).catch((e) => console.error('timeout', e.message));
    }
    await modlog({ embeds: [strikeEmbed({ ...card, pending: false })], allowedMentions: { parse: [] } });
    return;
  }
  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`strike:confirm:${logId}`).setLabel(`Confirm ${ACTION[step].toLowerCase()}`).setStyle(ButtonStyle.Danger),
    new ButtonBuilder().setCustomId(`strike:dismiss:${logId}`).setLabel('Dismiss').setStyle(ButtonStyle.Secondary));
  await modlog({
    content: `<@&${cfg.devRole}>`, embeds: [strikeEmbed({ ...card, pending: true })],
    components: [row], allowedMentions: { roles: [cfg.devRole], users: [] },
  });
}

export async function resolveStrike(logId, confirm, byUser) {
  const row = db.prepare('SELECT * FROM strike_log WHERE id=?').get(logId);
  if (!row || row.state !== 'pending') return 'Already handled.';
  if (!confirm) {
    db.prepare("UPDATE strike_log SET state='dismissed' WHERE id=?").run(logId);
    db.prepare('UPDATE strikes SET count=MAX(count-1,0) WHERE user_id=?').run(row.user_id);
    return `Dismissed by <@${byUser}>. Strike removed.`;
  }
  db.prepare("UPDATE strike_log SET state='done' WHERE id=?").run(logId);
  const g = ctx.guild;
  const note = `${E.warn} **${ACTION[row.step].toUpperCase()}** · ${g.name}\nRepeated trolling in bug reports: ${row.reason}`;
  await dm(row.user_id, note);
  try {
    if (row.step === 'kick') await g.members.kick(row.user_id, `Bug-report trolling: ${row.reason}`);
    else if (row.step === 'ban7') {
      await g.members.ban(row.user_id, { reason: `7-day ban, bug-report trolling: ${row.reason}` });
      addTimer('unban', row.user_id, now() + 7 * DAY);
    } else await g.members.ban(row.user_id, { reason: `Permanent ban, bug-report trolling: ${row.reason}` });
  } catch (e) {
    return `Confirmed by <@${byUser}> but the action failed: ${e.message}`;
  }
  return `Confirmed by <@${byUser}>. ${LABEL[row.step]} applied.`;
}

export async function pardon(userId) {
  db.prepare('UPDATE strikes SET count=MAX(count-1,0) WHERE user_id=?').run(userId);
  const m = await getMember(userId);
  if (m?.communicationDisabledUntilTimestamp > now()) await m.timeout(null, 'Pardoned').catch(() => {});
  return db.prepare('SELECT count FROM strikes WHERE user_id=?').get(userId)?.count ?? 0;
}

export function strikeInfo(userId) {
  const count = db.prepare('SELECT count FROM strikes WHERE user_id=?').get(userId)?.count ?? 0;
  const log = db.prepare('SELECT * FROM strike_log WHERE user_id=? ORDER BY id DESC LIMIT 5').all(userId);
  return { count, log };
}
