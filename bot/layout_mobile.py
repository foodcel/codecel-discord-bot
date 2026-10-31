"""Design B, saved for later: the Unreleased games embed for phones. NOT used by the bot right now.

One field per dev and one line per game, with the progress on the game's own line. There are no columns, so nothing can drift
out of line under the dev mention, and the embed only needs about 360px (the two-column layout needs about 520px).

    ⟨dev mention⟩ · 3/7 working
    ├─ Aviassembly · ▰▰▰▱▱▱▱▱ 30%
    ├─ Mini Metro · ⏸ 20%
    └─ Turmoil · —

To switch the live board to it, call `unreleased_embed(rows, n_games)` instead of the two-column `tree_rows` + `table` code in
`games.game_embeds`, and do the same for the Released games embed (date instead of progress). `rows` is what `games.rows_by_dev` returns.
Try it in the test channel with `python scripts/preview_widths.py`.
"""
from .games import cut, http
from .ui import HF, ZW, describe, flat, gap, head

BLOCKS = 8  # width of the progress bar
FILLER = HF * 24  # sets the embed width (the two-column layout uses 34)
NAME = 18  # longest game name shown


def progress(r):
    p, w = r.get('progress'), r.get('working')
    if w == 0:
        return f'⏸ {p}%' if p is not None else '⏸ paused'
    if p is not None:
        n = round(p / 100 * BLOCKS)
        return f'{chr(0x25B0) * n}{chr(0x25B1) * (BLOCKS - n)} {p}%'
    return '▶ working' if w else '—'


def name(r):
    return f"[**{cut(r['name'], NAME)}**]({r['link']})" if http(r['link']) else f"**{cut(r['name'], NAME)}**"


def unreleased_embed(rows, n_games):
    """`rows`: the games sorted by dev, each with 'dev' (a mention), 'first' (first row of a dev), 'name', 'link',
    'progress' and 'working'."""
    e = flat()
    e.title = head('🛠️', 'Unreleased games')
    describe(e, f'🛠️ **{n_games}** in development', FILLER)
    groups = []
    for r in rows:
        if r['first']:
            groups.append([])
        groups[-1].append(r)
    for g in groups:
        g.sort(key=lambda r: 0 if (r.get('working') or (r.get('working') is None and r.get('progress'))) else 1)  # worked on first
        flagged = [r for r in g if r.get('working') is not None or r.get('progress') is not None]
        active = [r for r in flagged if r.get('working') != 0]
        lines = [f"{g[0]['dev']} · {len(active)}/{len(g)} working" if flagged else g[0]['dev']]
        for k, r in enumerate(g):
            lines.append(f"{'└─' if k == len(g) - 1 else '├─'} {name(r)} · {progress(r)}")
        e.add_field(name=ZW, value='\n'.join(lines)[:1024], inline=False)
    return gap(e)
