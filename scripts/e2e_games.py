"""Checks /release and /unrelease against the live bounty-board with a fake admin, then puts everything back."""
import asyncio
from types import SimpleNamespace

from _boot import boot, finish

from bot.bounty import get_claims
from bot.db import run
from bot.games import command_release, game_lists

ADMIN = SimpleNamespace(id=1, roles=[], guild_permissions=SimpleNamespace(administrator=True))


async def call(undo, game, link=None):
    out = []

    async def send_message(content=None, **kw):
        out.append(content)

    i = SimpleNamespace(user=ADMIN, response=SimpleNamespace(send_message=send_message))
    await command_release(i, {'game': game, 'link': link}, undo)
    return out[0]


async def main():
    client = await boot()
    before = game_lists()
    print('claims read:', len(get_claims()), '| unreleased:', len(before['unreleased']), '| released:', len(before['released']))
    name = get_claims()[0]['name']
    print('release   ->', await call(False, name, 'https://example.com/play'))
    lists = game_lists()
    print('  now unreleased', len(lists['unreleased']), '| released', len(lists['released']), '| released row:',
          ','.join(f"{r['name']} {r['link']}" for r in lists['released']))
    print('unrelease ->', await call(True, name))
    lists = game_lists()
    print('  now unreleased', len(lists['unreleased']), '| released', len(lists['released']))
    run('DELETE FROM game_status')
    print('cleaned up')
    await finish(client)


asyncio.run(main())
