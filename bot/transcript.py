"""Transcripts: one bug or a whole game as a zip (conversation, screenshots, full videos, a few video frames)."""
import asyncio
import io
import math
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

import aiohttp
import discord

from .ctx import ctx, fetch_channel, thread_link
from .db import bug_by_id
from .tags import applied_ids, device_tags, tag_name

FFMPEG = os.environ.get('FFMPEG_PATH') or 'ffmpeg'
MAX_IMG = 8 * 1024 * 1024
MAX_VIDEO = 100 * 1024 * 1024


def fmt(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime('%Y-%m-%d %H:%M') + ' UTC'


def safe(n):
    return re.sub(r'[^\w.\-]+', '_', str(n), flags=re.ASCII)[:60]


def upload_limit():
    """Discord upload limit by server boost level (free servers: 10 MB), minus a margin."""
    tiers = [10, 10, 50, 100]
    tier = ctx.guild.premium_tier
    mb = tiers[tier] if 0 <= tier < len(tiers) else 10
    return mb * 1024 * 1024 * 0.93


async def video_frames(buf, ext):
    """Up to 8 frames spread across the video, so an AI agent can look at what happens. Returns (duration, [jpg bytes])."""
    d = tempfile.mkdtemp(prefix='bugvid-')
    try:
        inp = os.path.join(d, f'in.{ext}')
        with open(inp, 'wb') as f:
            f.write(buf)
        dur = 0
        p = await asyncio.create_subprocess_exec(FFMPEG, '-hide_banner', '-i', inp,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, err = await p.communicate()  # ffmpeg exits with an error here (no output file) but prints the duration
        m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', err.decode('utf8', 'replace'))
        if m:
            dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        n = min(8, max(3, math.ceil(dur / 2)))
        fps = n / dur if dur > 0 else 0.5
        p = await asyncio.create_subprocess_exec(
            FFMPEG, '-hide_banner', '-loglevel', 'error', '-i', inp, '-vf', f'fps={fps:.4f},scale=960:-2',
            '-frames:v', str(n), '-q:v', '5', os.path.join(d, 'f-%02d.jpg'),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, err = await p.communicate()
        if p.returncode != 0:
            raise RuntimeError(err.decode('utf8', 'replace').strip() or 'ffmpeg failed')
        names = sorted(x for x in os.listdir(d) if x.startswith('f-'))
        frames = []
        for x in names:
            with open(os.path.join(d, x), 'rb') as f:
                frames.append(f.read())
        return dur, frames
    except Exception as e:
        print('ffmpeg', e)
        return 0, []
    finally:
        shutil.rmtree(d, ignore_errors=True)


async def download(url):
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if not 200 <= r.status < 300:
                raise RuntimeError(f'HTTP {r.status}')
            return await r.read()


async def bug_bundle(bug):
    """One bug: markdown with @@key@@ placeholders for files, plus the downloaded files themselves."""
    thread = None if bug['deleted'] else await fetch_channel(bug['thread_id'])
    msgs = []
    if thread:
        try:
            msgs = [m async for m in thread.history(limit=100)]
        except Exception:
            msgs = []
    msgs.sort(key=lambda m: m.created_at)
    if bug.get('device'):
        devices = [bug['device']]
    elif thread:
        names = [tag_name(i) for i in applied_ids(thread)]
        devices = [n for n in names if n and any(d['name'] == n for d in device_tags())]
    else:
        devices = []
    try:
        reporter = await ctx.client.fetch_user(int(bug['reporter_id']))
    except Exception:
        reporter = None
    md = [
        f"# Bug #{bug['id']}: {bug['title'] or 'untitled'}",
        f"- Game: {bug['game_name'] or 'unknown'}",
        f"- Device: {', '.join(devices) or 'not given'}",
        f"- Severity: {bug['severity'] or '?'}  ·  Status: {bug['status']}",
        f"- Reported by: {reporter.name if reporter else bug['reporter_id']} on {fmt(bug['created_at'])}",
        f"- Post: {thread_link(bug['thread_id'])}",
        *([f"- Developer note: {bug['note']}"] if bug.get('note') else []),
        *(['- Source: tester report (form)'] if bug.get('source') == 'tester' else []),
        '', '## Summary (auto-generated)', bug['summary'] or '(none)',
        *(['', '## Report as written by the tester', bug['body']] if bug.get('body') else []),
        '', '## Conversation',
    ]
    if not msgs:
        md.append('(post is no longer available)')
    assets = []
    n = 0

    def add(a):
        nonlocal n
        key = f'a{n}'
        n += 1
        assets.append({'key': key, **a})
        return key

    for m in msgs:
        if str(m.author.id) == bug['reporter_id']:
            tag = 'reporter'
        elif m.author.id == ctx.client.user.id:
            tag = 'bot'
        else:
            tag = m.author.display_name
        t = fmt(m.created_at.timestamp() * 1000)
        if (m.content or '').strip():
            md.append(f'[{t}] {tag}: {m.content.strip()}')
        for a in m.attachments:
            typ = a.content_type or ''
            try:
                if typ.startswith('image/') and a.size <= MAX_IMG and len([x for x in assets if x['kind'] == 'image']) < 10:
                    path = f'images/{n}-{safe(a.filename)}'
                    k = add({'kind': 'image', 'path': path, 'data': await download(a.url), 'url': a.url, 'name': a.filename})
                    md.append(f'[{t}] {tag} attached image: ![{a.filename}](@@{k}@@)')
                elif typ.startswith('video/') and a.size <= MAX_VIDEO:
                    buf = await download(a.url)
                    ext = (re.search(r'\.(\w{2,4})$', a.filename, re.ASCII) or [None, 'mp4'])[1]
                    dur, frames = await video_frames(buf, ext)
                    path = f'videos/{n}-{safe(a.filename)}'
                    vk = add({'kind': 'video', 'path': path, 'data': buf, 'url': a.url, 'name': a.filename})
                    md.append(f"[{t}] {tag} attached video: [{a.filename}](@@{vk}@@){f' ({round(dur)}s)' if dur else ''}. Frames sampled from it, in order:")
                    for i, f in enumerate(frames):
                        fpath = f'video-frames/{n}-{i + 1}.jpg'
                        fk = add({'kind': 'frame', 'path': fpath, 'data': f, 'url': None})
                        md.append(f'  ![frame {i + 1}](@@{fk}@@)')
                else:
                    md.append(f'[{t}] {tag} attached file: [{a.filename}]({a.url})')
            except Exception as e:
                md.append(f'[{t}] {tag} attached: [{a.filename}]({a.url}) (could not download: {e})')
    return {'folder': f"bug-{bug['id']}", 'md': '\n'.join(md), 'assets': assets}


def resolve(part, kept):
    """Files that are in the zip are referenced by path. Anything that did not fit is listed at the end with its Discord link."""
    by_key = {a['key']: a for a in part['assets']}

    def repl(m):
        k = m.group(1)
        if k in kept:
            return kept[k]['path']
        a = by_key.get(k)
        return (a['url'] if a and a['url'] is not None else None) or 'omitted'

    md = re.sub(r'@@(\w+)@@', repl, part['md'], flags=re.ASCII)
    left = [a for a in part['assets'] if a['key'] not in kept and a['url'] and a['kind'] != 'frame']
    if left:
        md += '\n\n## Files not in this zip (too big). Download them from Discord:\n' + '\n'.join(
            f"- {a['kind']}: {a['name']} - {a['url']}" for a in left)
    return md


def _build_zip(parts, kept):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for p in parts:
            k = kept[p['folder']]
            z.writestr(f"{p['folder']}/transcript.md", resolve(p, k).encode('utf8'), compress_type=zipfile.ZIP_DEFLATED)
            for a in k.values():
                z.writestr(f"{p['folder']}/{a['path']}", a['data'], compress_type=zipfile.ZIP_STORED)
    return buf.getvalue()


def pack(parts, limit):
    """Packs bugs into one zip under the upload limit. Order of priority: video frames and screenshots (what an AI agent
    actually looks at), then the whole videos, smallest first. Whatever does not fit becomes a download link."""
    budget = limit - 40 * 1024
    kept = {p['folder']: {} for p in parts}
    size = sum(len(p['md']) * 2 for p in parts)

    def by_kind(kind):
        rows = [(p, a) for p in parts for a in p['assets'] if a['kind'] == kind]
        return sorted(rows, key=lambda r: len(r[1]['data']))

    for kind in ('frame', 'image', 'video'):
        for p, a in by_kind(kind):
            if size + len(a['data']) > budget:
                continue
            kept[p['folder']][a['key']] = a
            size += len(a['data'])
    zipped = _build_zip(parts, kept)
    while len(zipped) > limit:  # zip headers added a little: drop the biggest kept file until it fits
        worst = None
        for folder, m in kept.items():
            for a in m.values():
                if worst is None or len(a['data']) > len(worst[1]['data']):
                    worst = (folder, a)
        if worst is None:
            break
        del kept[worst[0]][worst[1]['key']]
        zipped = _build_zip(parts, kept)
    dropped = sum(len([a for a in p['assets'] if a['kind'] != 'frame' and a['key'] not in kept[p['folder']]]) for p in parts)
    return {'zip': zipped, 'dropped': dropped}


def plain_md(p):
    return resolve(p, {})


def _size_of(p):
    return len(p['md']) + sum(len(a['data']) for a in p['assets'])


def _file(data, name):
    return discord.File(io.BytesIO(data), filename=name)


async def single_transcript(id_):
    bug = bug_by_id(id_)
    if not bug:
        return None
    part = await bug_bundle(bug)
    if not part['assets']:
        md = plain_md(part)
        return {'inline': md if len(md) < 1850 else None, 'files': [_file(md.encode('utf8'), f'bug-{id_}.md')], 'note': ''}
    r = pack([part], upload_limit())
    note = 'Zip with `transcript.md`, the screenshots, the full videos and a few video frames for AI agents.'
    if r['dropped']:
        note += f" {r['dropped']} file(s) were too big for the zip, so their Discord download links are at the end of `transcript.md`."
    return {'inline': None, 'files': [_file(r['zip'], f'bug-{id_}.zip')], 'note': note}


async def board_transcript(key, game='all'):
    """game: 'all', or a game tag id ('none' = bugs without a game)."""
    from .devboard import open_bugs_for  # imported here: devboard also imports this module's neighbours
    bugs = [b for b in open_bugs_for(key) if game == 'all' or (b['game_tag_id'] or 'none') == game]
    label = 'all-games' if game == 'all' else safe((bugs[0]['game_name'] if bugs else None) or 'unknown-game').lower()
    parts = [await bug_bundle(b) for b in bugs]
    limit = upload_limit()
    groups = []
    cur = []
    size = 0
    for p in parts:
        if cur and size + _size_of(p) > limit:
            groups.append(cur)
            cur = []
            size = 0
        cur.append(p)
        size += _size_of(p)
    if cur:
        groups.append(cur)
    shown = groups[:10]
    files = []
    for i, g in enumerate(shown):
        files.append(_file(pack(g, limit)['zip'], f"open-bugs-{label}{f'-part{i + 1}' if len(groups) > 1 else ''}.zip"))
    tokens = math.ceil(sum(len(plain_md(p)) for p in parts) / 4)
    return {'count': len(bugs), 'name': bugs[0]['game_name'] if bugs else None, 'files': files, 'tokens': tokens,
            'hasMedia': any(p['assets'] for p in parts), 'cut': len(groups) - len(shown)}
