"""Posts the Unreleased games embed in three widths into the test channel (real games and devs, placeholder progress), to compare on
desktop and phone. Nothing else is touched.  Run: python scripts/preview_widths.py"""
import asyncio
import re

from _boot import boot, finish

from bot.env import cfg
from bot.games import GAP_ROW, cut, game_embeds, http, rows_by_dev, table, tree_rows
from bot.ui import E, HF, ZW, describe, flat, gap, head



def bar(p, blocks):
    n = round(p / 100 * blocks)
    return f"{chr(0x25B0) * n}{chr(0x25B1) * (blocks - n)} {p}%"


def cell(r, blocks):
    p, w = r.get('progress'), r.get('working')
    if w == 0:
        return f'⏸ {p}%' if p is not None else '⏸ paused'
    if p is not None:
        return bar(p, blocks)
    return '▶ working' if w else '—'


def name_of(r, n):
    return f"[**{cut(r['name'], n)}**]({r['link']})" if http(r['link']) else f"**{cut(r['name'], n)}**"


async def entries(lists):
    return await rows_by_dev([{'name': g['name'], 'owners': g['owners'], 'since': g['since'], 'link': g.get('source_link'),
                               'progress': g.get('progress'), 'working': g.get('working')} for g in lists['unreleased']])


def head_embed(n, filler):
    e = flat()
    e.title = head('🛠️', 'Unreleased games')
    describe(e, f'🛠️ **{n}** in development', filler)
    return e


async def variant_a(lists):
    """Two columns, narrower: shorter names, a 6 block bar, a shorter width line."""
    rows = await entries(lists)
    e = head_embed(len(rows), HF * 28)

    def progress(r):
        return cell(r, 6)

    out = []
    for r in tree_rows(rows, progress, counts=True):
        out.append(r)
    for r in out:  # shorter names
        if r is not GAP_ROW:
            r[0] = re.sub(r'\*\*(.+?)…?\*\*', lambda m: '**' + cut(m.group(1), 16) + '**', r[0]) if '├' in r[0] or '└' in r[0] else r[0]
    table(e, [head(E['game'], 'Games'), head('📊', 'Progress')], out)
    return gap(e)


async def variant_b(lists):
    """One field per dev, one line per game: the progress sits on the game's own line. No columns, so nothing can drift."""
    rows = await entries(lists)
    e = head_embed(len(rows), HF * 24)
    groups = []
    for r in rows:
        if r['first']:
            groups.append([])
        groups[-1].append(r)
    for g in groups:
        g.sort(key=lambda r: 0 if (r.get('working') or (r.get('working') is None and r.get('progress'))) else 1)
        flagged = [r for r in g if r.get('working') is not None or r.get('progress') is not None]
        active = [r for r in flagged if r.get('working') != 0]
        title = f"{g[0]['dev']} · {len(active)}/{len(g)} working" if flagged else g[0]['dev']
        lines = [title]
        for k, r in enumerate(g):
            branch = '└─' if k == len(g) - 1 else '├─'
            lines.append(f"{branch} {name_of(r, 18)} · {cell(r, 8)}")
        e.add_field(name=ZW, value='\n'.join(lines)[:1024], inline=False)
    return gap(e)


async def main():
    client = await boot(members=True, claims=False)
    # the games come from the live board's own Unreleased embed (read only)
    ch = await client.fetch_channel(int(cfg.bounty_id))
    live = next(e for m in [m async for m in ch.history(limit=20)] for e in m.embeds if 'UNRELEASED' in (e.title or '').upper())
    unreleased = []
    owner = None
    for f in live.fields:
        for line in f.value.splitlines():
            m = re.match(r'^<@!?(\d+)>', line)
            if m:
                owner = m.group(1)
                continue
            g = re.match(r'^[├└]─ (?:\[)?\*\*(.+?)\*\*(?:\]\((\S+?)\))?', line)
            if g and owner:
                unreleased.append({'key': g.group(1).lower(), 'name': g.group(1), 'owners': [owner], 'since': None,
                                   'source_link': g.group(2), 'progress': None, 'working': None})
    tch = await client.fetch_channel(int(cfg.test_id))
    lists = {'released': [], 'unreleased': unreleased}
    for n, g in enumerate(unreleased):  # placeholder progress on real games
        if n % 3 == 0:
            g['progress'], g['working'] = 15 + (n * 13) % 80, 1
        elif n % 3 == 1:
            g['progress'], g['working'] = 10 + (n * 7) % 60, 0
    _, current = await game_embeds(lists)
    await tch.send(content='**Now** (current width)', embed=current)
    await tch.send(content='**A** · two columns, narrower (names 16, bar 6, shorter width line)', embed=await variant_a(lists))
    await tch.send(content='**B** · one line per game, no columns (narrowest, nothing drifts)', embed=await variant_b(lists))
    await finish(client)
    print('posted 3 messages')


asyncio.run(main())
