import { AttachmentBuilder } from 'discord.js';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, writeFile, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { zipSync, strToU8 } from 'fflate';
import { ctx, fetchChannel, threadLink } from './ctx.js';
import { bugById } from './db.js';
import { deviceTags, tagName } from './tags.js';
import { openBugsFor } from './devboard.js';

const run = promisify(execFile);
const FFMPEG = process.env.FFMPEG_PATH || 'ffmpeg';
const MAX_IMG = 8 * 1024 * 1024;
const MAX_VIDEO = 100 * 1024 * 1024;
const fmt = (ts) => new Date(ts).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
const safe = (n) => String(n).replace(/[^\w.\-]+/g, '_').slice(0, 60);

// Discord upload limit by server boost level (free servers: 10 MB), minus a margin.
export const uploadLimit = () => ([10, 10, 50, 100][ctx.guild.premiumTier] ?? 10) * 1024 * 1024 * 0.93;

// Up to 8 frames spread across the video, so an AI agent can look at what happens.
export async function videoFrames(buf, ext) {
  const dir = await mkdtemp(join(tmpdir(), 'bugvid-'));
  try {
    const inp = join(dir, `in.${ext}`);
    await writeFile(inp, buf);
    let dur = 0;
    try { await run(FFMPEG, ['-hide_banner', '-i', inp]); } catch (e) {
      const m = /Duration: (\d+):(\d+):([\d.]+)/.exec(e.stderr || '');
      if (m) dur = +m[1] * 3600 + +m[2] * 60 + +m[3];
    }
    const n = Math.min(8, Math.max(3, Math.ceil(dur / 2)));
    const fps = dur > 0 ? n / dur : 0.5;
    await run(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-i', inp, '-vf', `fps=${fps.toFixed(4)},scale=960:-2`,
      '-frames:v', String(n), '-q:v', '5', join(dir, 'f-%02d.jpg')]);
    const names = (await readdir(dir)).filter((f) => f.startsWith('f-')).sort();
    return { dur, frames: await Promise.all(names.map((f) => readFile(join(dir, f)))) };
  } catch (e) {
    console.error('ffmpeg', e.message);
    return { dur: 0, frames: [] };
  } finally {
    await rm(dir, { recursive: true, force: true }).catch(() => {});
  }
}

async function download(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
}

// One bug: markdown with @@key@@ placeholders for files, plus the downloaded files themselves.
export async function bugBundle(bug) {
  const thread = bug.deleted ? null : await fetchChannel(bug.thread_id);
  const msgs = thread ? await thread.messages.fetch({ limit: 100 }).catch(() => null) : null;
  const sorted = [...(msgs?.values() ?? [])].sort((a, b) => a.createdTimestamp - b.createdTimestamp);
  const devices = bug.device ? [bug.device] : (thread ? (thread.appliedTags || []).map(tagName).filter((n) => deviceTags().some((d) => d.name === n)) : []);
  const reporter = await ctx.client.users.fetch(bug.reporter_id).catch(() => null);
  const md = [
    `# Bug #${bug.id}: ${bug.title || 'untitled'}`,
    `- Game: ${bug.game_name || 'unknown'}`,
    `- Device: ${devices.join(', ') || 'not given'}`,
    `- Severity: ${bug.severity || '?'}  ·  Status: ${bug.status}`,
    `- Reported by: ${reporter?.username ?? bug.reporter_id} on ${fmt(bug.created_at)}`,
    `- Post: ${threadLink(bug.thread_id)}`,
    ...(bug.note ? [`- Developer note: ${bug.note}`] : []),
    ...(bug.source === 'tester' ? ['- Source: tester report (form)'] : []),
    '', '## Summary (auto-generated)', bug.summary || '(none)',
    ...(bug.body ? ['', '## Report as written by the tester', bug.body] : []),
    '', '## Conversation',
  ];
  if (!sorted.length) md.push('(post is no longer available)');
  const assets = [];
  let n = 0;
  const add = (a) => { const key = `a${n++}`; assets.push({ key, ...a }); return key; };
  for (const m of sorted) {
    const tag = m.author.id === bug.reporter_id ? 'reporter' : (m.author.id === ctx.client.user.id ? 'bot' : (m.member?.displayName ?? m.author.username));
    const t = fmt(m.createdTimestamp);
    if (m.content.trim()) md.push(`[${t}] ${tag}: ${m.content.trim()}`);
    for (const a of m.attachments.values()) {
      const type = a.contentType || '';
      try {
        if (type.startsWith('image/') && a.size <= MAX_IMG && assets.filter((x) => x.kind === 'image').length < 10) {
          const k = add({ kind: 'image', path: `images/${n}-${safe(a.name)}`, data: await download(a.url), url: a.url, name: a.name });
          md.push(`[${t}] ${tag} attached image: ![${a.name}](@@${k}@@)`);
        } else if (type.startsWith('video/') && a.size <= MAX_VIDEO) {
          const buf = await download(a.url);
          const { dur, frames } = await videoFrames(buf, (a.name.match(/\.(\w{2,4})$/) || [, 'mp4'])[1]);
          const vk = add({ kind: 'video', path: `videos/${n}-${safe(a.name)}`, data: buf, url: a.url, name: a.name });
          md.push(`[${t}] ${tag} attached video: [${a.name}](@@${vk}@@)${dur ? ` (${Math.round(dur)}s)` : ''}. Frames sampled from it, in order:`);
          frames.forEach((f, i) => {
            const fk = add({ kind: 'frame', path: `video-frames/${n}-${i + 1}.jpg`, data: f, url: null });
            md.push(`  ![frame ${i + 1}](@@${fk}@@)`);
          });
        } else {
          md.push(`[${t}] ${tag} attached file: [${a.name}](${a.url})`);
        }
      } catch (e) {
        md.push(`[${t}] ${tag} attached: [${a.name}](${a.url}) (could not download: ${e.message})`);
      }
    }
  }
  return { folder: `bug-${bug.id}`, md: md.join('\n'), assets };
}

// Files that are in the zip are referenced by path. Anything that did not fit is listed at the end with its Discord link.
function resolve(part, kept) {
  const byKey = new Map(part.assets.map((a) => [a.key, a]));
  let md = part.md.replace(/@@(\w+)@@/g, (_, k) => (kept.has(k) ? kept.get(k).path : (byKey.get(k)?.url ?? 'omitted')));
  const left = part.assets.filter((a) => !kept.has(a.key) && a.url && a.kind !== 'frame');
  if (left.length) md += '\n\n## Files not in this zip (too big). Download them from Discord:\n' + left.map((a) => `- ${a.kind}: ${a.name} - ${a.url}`).join('\n');
  return md;
}

// Packs bugs into one zip under the upload limit. Order of priority: video frames and screenshots (what an AI agent
// actually looks at), then the whole videos, smallest first. Whatever does not fit becomes a download link.
export function pack(parts, limit) {
  const budget = limit - 40 * 1024;
  const kept = new Map(parts.map((p) => [p.folder, new Map()]));
  let size = parts.reduce((s, p) => s + p.md.length * 2, 0);
  const byKind = (kind) => parts.flatMap((p) => p.assets.filter((a) => a.kind === kind).map((a) => [p, a]))
    .sort((x, y) => x[1].data.length - y[1].data.length);
  for (const kind of ['frame', 'image', 'video']) {
    for (const [p, a] of byKind(kind)) {
      if (size + a.data.length > budget) continue;
      kept.get(p.folder).set(a.key, a);
      size += a.data.length;
    }
  }
  const build = () => {
    const files = {};
    for (const p of parts) {
      const k = kept.get(p.folder);
      files[`${p.folder}/transcript.md`] = strToU8(resolve(p, k));
      for (const a of k.values()) files[`${p.folder}/${a.path}`] = [new Uint8Array(a.data), { level: 0 }];
    }
    return zipSync(files);
  };
  let zip = build();
  while (zip.length > limit) { // zip headers added a little: drop the biggest kept file until it fits
    let worst = null;
    for (const [folder, m] of kept) for (const a of m.values()) if (!worst || a.data.length > worst.a.data.length) worst = { folder, a };
    if (!worst) break;
    kept.get(worst.folder).delete(worst.a.key);
    zip = build();
  }
  const dropped = parts.reduce((s, p) => s + p.assets.filter((a) => a.kind !== 'frame' && !kept.get(p.folder).has(a.key)).length, 0);
  return { zip, dropped };
}

export const plainMd = (p) => resolve(p, new Map());
const sizeOf = (p) => p.md.length + p.assets.reduce((s, a) => s + a.data.length, 0);

export async function singleTranscript(id) {
  const bug = bugById(id);
  if (!bug) return null;
  const part = await bugBundle(bug);
  if (!part.assets.length) {
    const md = plainMd(part);
    return { inline: md.length < 1850 ? md : null, files: [new AttachmentBuilder(Buffer.from(md, 'utf8'), { name: `bug-${id}.md` })], note: '' };
  }
  const { zip, dropped } = pack([part], uploadLimit());
  return {
    inline: null, files: [new AttachmentBuilder(Buffer.from(zip), { name: `bug-${id}.zip` })],
    note: `Zip with \`transcript.md\`, the screenshots, the full videos and a few video frames for AI agents.` +
      (dropped ? ` ${dropped} file(s) were too big for the zip, so their Discord download links are at the end of \`transcript.md\`.` : ''),
  };
}

// game: 'all', or a game tag id ('none' = bugs without a game).
export async function boardTranscript(key, game = 'all') {
  const bugs = openBugsFor(key).filter((b) => game === 'all' || (b.game_tag_id || 'none') === game);
  const label = game === 'all' ? 'all-games' : safe(bugs[0]?.game_name || 'unknown-game').toLowerCase();
  const parts = [];
  for (const b of bugs) parts.push(await bugBundle(b));
  const limit = uploadLimit();
  const groups = [];
  let cur = [];
  let size = 0;
  for (const p of parts) {
    if (cur.length && size + sizeOf(p) > limit) { groups.push(cur); cur = []; size = 0; }
    cur.push(p); size += sizeOf(p);
  }
  if (cur.length) groups.push(cur);
  const shown = groups.slice(0, 10);
  const files = shown.map((g, i) => {
    const { zip } = pack(g, limit);
    return new AttachmentBuilder(Buffer.from(zip), { name: `open-bugs-${label}${groups.length > 1 ? `-part${i + 1}` : ''}.zip` });
  });
  const tokens = Math.ceil(parts.reduce((s, p) => s + plainMd(p).length, 0) / 4);
  return { count: bugs.length, name: bugs[0]?.game_name, files, tokens, hasMedia: parts.some((p) => p.assets.length), cut: groups.length - shown.length };
}
