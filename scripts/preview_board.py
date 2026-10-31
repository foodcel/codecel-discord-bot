"""Posts the finished bounty board (Top suggestions, Unreleased games, Released games) with the real forum posts and the real
claims into the test channel. Nothing in the real board channel or on any forum post is touched; the local database is cleaned after."""
import asyncio
import re

from _boot import boot, finish

from bot import board
from bot.db import kv_del, run
from bot.env import cfg


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
    await board.sync_forum()
    board.released_from_claims()
    await board.refresh_board()  # posts the three messages in the test channel
    c = board.board_cfg()
    tch = await client.fetch_channel(int(cfg.test_id))
    for k in ('top', 'claims', 'completed'):
        await (await tch.fetch_message(int(c[k]))).unpin()
    print('posted:', c['top'], c['claims'], c['completed'])
    for t in ('board_claims', 'board_posts', 'game_status'):
        run(f'DELETE FROM {t}')
    kv_del('board')
    await finish(client)


asyncio.run(main())
