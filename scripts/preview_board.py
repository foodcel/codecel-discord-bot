"""Posts the board (Top suggestions, Unreleased games, Released games) into the test channel: the real forum posts, votes and
claims, with PLACEHOLDER progress, release dates and links so the layout can be judged. Nothing in the real board channel or
on any forum post is touched; the local database is cleaned after.
    python scripts/preview_board.py            placeholders
    python scripts/preview_board.py --real     exactly what the live board would show now"""
import asyncio
import re
import sys
import time

from _boot import boot, finish

from bot import board
from bot.db import kv_del, run
from bot.env import cfg
from bot.games import game_embeds, game_lists


def sample_lists():
    """Every third game shown as released (some with a Roblox link), the rest with made-up progress."""
    live = game_lists()
    now = int(time.time() * 1000)
    released, unreleased = [], []
    for n, g in enumerate(live['unreleased']):
        if n % 3 == 0:
            released.append({'key': g['key'], 'name': g['name'], 'owners': ','.join(g['owners']),
                             'released_at': now - len(released) * 86400000 * 2,
                             'link': f'https://www.roblox.com/games/{1000 + n}' if n % 2 == 0 else None})
        else:
            g = dict(g)
            if n % 4 == 1:
                g['progress'], g['working'] = 15 + (n * 13) % 80, 1
            elif n % 4 == 2:
                g['progress'], g['working'] = 10 + (n * 7) % 60, 0
            if n % 5 == 0:
                g['source_link'] = f'https://store.steampowered.com/app/{2000 + n}'
            unreleased.append(g)
    return {'released': released, 'unreleased': unreleased}


async def main():
    client = await boot(members=True, claims=False)

    async def no_tag(*a, **k):
        return True
    board.set_post_tag = no_tag  # never touch the real forum's tags
    board.tag_if_highly_requested = no_tag

    ch = await client.fetch_channel(int(cfg.bounty_id))
    old = [m async for m in ch.history(limit=50) if m.author.bot]
    text = next(e.description for m in old for e in m.embeds if 'Claimed' in (e.title or ''))
    forum_id = (await client.fetch_channel(int(re.search(r'/channels/\d+/(\d+)\)', text).group(1)))).parent_id
    for t in ('board_claims', 'board_posts', 'game_status'):
        run(f'DELETE FROM {t}')
    kv_del('board')
    board.import_old_board(old)
    board.save_cfg({'forum_id': str(forum_id), 'channel_id': cfg.test_id, 'role_id': cfg.dev_role, 'top': None, 'claims': None, 'completed': None})
    await board.sync_forum()  # real posts and votes (this also posts and pins the three messages in the test channel; they are removed below)
    c = board.board_cfg()
    tch = await client.fetch_channel(int(cfg.test_id))
    for k in ('top', 'claims', 'completed'):
        try:
            m = await tch.fetch_message(int(c[k]))
            await m.delete()
        except Exception:
            pass
    board.released_from_claims()
    from bot import bounty
    bounty.set_claims(board.live_claims())
    top = board.top_embed()
    if '--real' in sys.argv:
        released, unreleased = await game_embeds()
    else:
        released, unreleased = await game_embeds(sample_lists())
    for e in (top, unreleased, released):
        await tch.send(embed=e)
    print('posted 3 messages')
    for t in ('board_claims', 'board_posts', 'game_status'):
        run(f'DELETE FROM {t}')
    kv_del('board')
    await finish(client)


asyncio.run(main())
