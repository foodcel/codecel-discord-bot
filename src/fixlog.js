import { ActionRowBuilder, AttachmentBuilder, ButtonBuilder, ButtonStyle, MessageFlags, StringSelectMenuBuilder } from 'discord.js';
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { cfg } from './env.js';
import { ctx, fetchChannel } from './ctx.js';
import { db, bugById, kvGet, kvSet } from './db.js';
import { onBoardsRefreshed } from './devboard.js';
import { bugBundle, pack, plainMd, uploadLimit } from './transcript.js';
import { E, GAP, columns, cut, describe, flat, head, section } from './ui.js';

const EPH = MessageFlags.Ephemeral;
const DIR = fileURLToPath(new URL('../data/archive/', import.meta.url));
const PER_PAGE = 8;
const gameWhere = (tag) => (tag === 'all' ? ['1=1', []] : tag === 'none' ? ['game_tag_id IS NULL', []] : ['game_tag_id = ?', [tag]]);

// ---- stored transcripts: taken when a bug is fixed, because the post is deleted 24h later ----
const zipPath = (id) => `${DIR}bug-${id}.zip`;
const mdPath = (id) => `${DIR}bug-${id}.md`;
const exists = (p) => stat(p).then(() => true, () => false);

export async function snapshotBug(bug) {
  await mkdir(DIR, { recursive: true });
  const part = await bugBundle(bug);
  if (part.assets.length) {
    await writeFile(zipPath(bug.id), pack([part], uploadLimit()).zip);
  } else {
    await writeFile(mdPath(bug.id), plainMd(part), 'utf8');
  }
}

// Fixed bugs from before the log existed.
export async function backfillSnapshots() {
  const fixed = db.prepare("SELECT * FROM bugs WHERE status='fixed'").all();
  for (const b of fixed) {
    if (await exists(zipPath(b.id)) || await exists(mdPath(b.id))) continue;
    await snapshotBug(b).catch((e) => console.error('snapshot', b.id, e.message));
  }
}

async function storedTranscript(id) {
  if (await exists(zipPath(id))) return { file: new AttachmentBuilder(await readFile(zipPath(id)), { name: `bug-${id}.zip` }), note: 'Zip with the transcript, screenshots and videos.' };
  if (await exists(mdPath(id))) return { file: new AttachmentBuilder(await readFile(mdPath(id)), { name: `bug-${id}.md` }), note: '' };
  return null;
}

// ---- the board ----
export function stats() {
  const rows = db.prepare(`SELECT game_tag_id tag, MAX(game_name) name,
    SUM(status='fixed') fixed, SUM(status IN ('new','investigating','fixing')) open, MAX(fixed_at) last_fix
    FROM bugs GROUP BY game_tag_id`).all();
  const ann = new Map(db.prepare('SELECT tag_id, COUNT(*) n FROM announcements GROUP BY tag_id').all().map((r) => [r.tag_id, r.n]));
  return rows.map((r) => ({ ...r, tag: r.tag || 'none', name: r.name || 'Unknown game', updates: ann.get(r.tag) || 0 }))
    .filter((r) => r.fixed || r.open || r.updates)
    .sort((a, b) => b.fixed - a.fixed || b.open - a.open || a.name.localeCompare(b.name));
}

const nameOf = async (id) => (await ctx.guild.members.fetch(id).catch(() => null))?.displayName ?? String(id ?? '?');

export function logEmbed() {
  const rows = stats();
  const tot = rows.reduce((a, r) => ({ f: a.f + r.fixed, o: a.o + r.open }), { f: 0, o: 0 });
  const e = flat().setTitle(head(E.log, 'Bug fix log'))
    .setFooter({ text: 'Pick a game below to see its fixes, updates and transcripts.' });
  if (!rows.length) return describe(e, 'Nothing yet. Fixed bugs and posted updates show up here.');
  describe(e, `${E.fixed} **${tot.f}** fixed${GAP}${E.open} **${tot.o}** open`);
  const list = rows.slice(0, 20);
  // Discord shows at most 3 columns per row, so last fix lives in the game dropdown (see logComponents).
  columns(e, [
    { name: head(E.game, 'Game'), lines: list.map((r) => `**${cut(r.name, 22)}**`) },
    { name: head(E.fixed, 'Fixed'), lines: list.map((r) => String(r.fixed)) },
    { name: head(E.open, 'Open'), lines: list.map((r) => String(r.open)) },
  ]);
  if (rows.length > 20) e.addFields({ name: '​', value: `…and ${rows.length - 20} more games` });
  return e;
}

export function logComponents() {
  const rows = stats();
  if (!rows.length) return [];
  const date = (t) => new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const options = [{ label: `All games (${rows.reduce((s, r) => s + r.fixed, 0)} fixed)`, value: 'all' },
    ...rows.slice(0, 24).map((r) => ({
      label: `${r.name} (${r.fixed} fixed)`.slice(0, 100),
      description: (r.last_fix ? `Last fix ${date(r.last_fix)}` : 'No fixes yet') + ` · ${r.open} open`,
      value: r.tag,
    }))];
  return [new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder().setCustomId('fl').setPlaceholder('Open a game\'s log').addOptions(options))];
}

async function _ensure() {
  const id = kvGet('logthread');
  const t = id ? await fetchChannel(id) : null;
  if (t) { if (t.archived) await t.setArchived(false).catch(() => {}); return t; }
  const forum = await fetchChannel(cfg.devForumId);
  const created = await forum.threads.create({ name: '📜 Bug fix log', message: { embeds: [logEmbed()], components: logComponents() } });
  kvSet('logthread', created.id);
  created.pin().catch(() => {});
  return created;
}

export async function refreshLog() {
  const t = await _ensure();
  const starter = await t?.fetchStarterMessage().catch(() => null);
  await starter?.edit({ content: null, embeds: [logEmbed()], components: logComponents() }).catch((e) => console.error('log edit', e.message));
}
onBoardsRefreshed(refreshLog);

// ---- a game's log page (private): same look, same columns ----
export async function renderLog(tag, page = 0) {
  const [where, args] = gameWhere(tag);
  const fixes = db.prepare(`SELECT * FROM bugs WHERE status='fixed' AND ${where} ORDER BY fixed_at DESC`).all(...args);
  const pages = Math.max(1, Math.ceil(fixes.length / PER_PAGE));
  page = Math.min(Math.max(0, page), pages - 1);
  const slice = fixes.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE);
  const all = stats();
  const s = tag === 'all' ? { fixed: fixes.length, updates: all.reduce((n, r) => n + r.updates, 0), open: all.reduce((n, r) => n + r.open, 0) } : all.find((r) => r.tag === tag);
  const name = tag === 'all' ? 'All games' : (s?.name || fixes[0]?.game_name || 'Unknown game');
  const names = await Promise.all(slice.map((b) => nameOf(b.fixed_by)));
  const anns = tag === 'all' ? db.prepare('SELECT * FROM announcements ORDER BY id DESC LIMIT 5').all()
    : db.prepare('SELECT * FROM announcements WHERE tag_id=? ORDER BY id DESC LIMIT 5').all(tag);
  const e = flat().setTitle(`${E.log} ${name.toUpperCase()} · FIX LOG`)
    .setFooter({ text: `Page ${page + 1} of ${pages}${slice.some((b) => b.announced) ? ` · ${E.update} = in a posted update` : ''}` });
  describe(e, `${E.fixed} **${s?.fixed ?? fixes.length}** fixed${GAP}${E.update} **${s?.updates ?? 0}** update${s?.updates === 1 ? '' : 's'}${GAP}${E.open} **${s?.open ?? 0}** open`);
  if (slice.length) {
    columns(e, [
      { name: head(E.fix, 'Fix'), lines: slice.map((b) => `**#${b.id}** ${cut(b.title, 28)}${b.announced ? ` ${E.update}` : ''}`) },
      { name: head(E.date, 'Fixed'), lines: slice.map((b) => `<t:${Math.floor(b.fixed_at / 1000)}:d>`) },
      { name: tag === 'all' ? head(E.game, 'Game') : head(E.user, 'Fixed by'), lines: slice.map((b, i) => (tag === 'all' ? cut(b.game_name || 'Unknown', 18) : names[i])) },
    ]);
  } else section(e, head(E.fix, 'Fixes'), 'No fixes logged yet.');
  if (anns.length) {
    section(e, head(E.update, 'Updates posted'),
      anns.map((a) => `<t:${Math.floor(a.posted_at / 1000)}:d> · ${JSON.parse(a.bug_ids).length} fixes · [view](${a.url})${tag === 'all' ? ` · ${a.game_name}` : ''}`).join('\n'));
  }
  const rows = [new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`flp:${tag}:${page - 1}`).setLabel('◀ Prev').setStyle(ButtonStyle.Secondary).setDisabled(page === 0),
    new ButtonBuilder().setCustomId('flp:noop:0').setLabel(`${page + 1} / ${pages}`).setStyle(ButtonStyle.Secondary).setDisabled(true),
    new ButtonBuilder().setCustomId(`flp:${tag}:${page + 1}`).setLabel('Next ▶').setStyle(ButtonStyle.Secondary).setDisabled(page >= pages - 1))];
  if (slice.length) {
    rows.push(new ActionRowBuilder().addComponents(
      new StringSelectMenuBuilder().setCustomId(`flt:${tag}`).setPlaceholder('📋 Transcript of a fix')
        .addOptions(slice.map((b) => ({ label: `#${b.id} ${b.title}`.slice(0, 100), value: String(b.id) })))));
  }
  return { content: null, embeds: [e], components: rows };
}

export async function openLog(i, tag) {
  await i.deferReply({ flags: EPH });
  i.message.edit({ components: logComponents() }).catch(() => {}); // resets the dropdown
  return i.editReply(await renderLog(tag, 0));
}

export async function logPage(i, tag, page) {
  if (tag === 'noop') return i.deferUpdate();
  await i.deferUpdate();
  return i.editReply(await renderLog(tag, Number(page)));
}

export async function sendFixTranscript(i, id) {
  await i.deferReply({ flags: EPH });
  const t = await storedTranscript(Number(id));
  if (!t) {
    const bug = bugById(Number(id));
    return i.editReply(bug ? `No stored transcript for #${id}.` : 'That bug is not in the log.');
  }
  return i.editReply({ content: `Transcript of fix #${id}. ${t.note}`.trim(), files: [t.file] });
}
