"""Checks /release new and /release edit with fake users on this PC's own database (nothing is posted): the Roblox fetch, the studio from the
Steam page, the owner lock, and the title change. Cleans up after itself."""
import asyncio
from types import SimpleNamespace

from _boot import boot, finish

from bot.db import one, run
from bot.games import game_lists, set_source_link
from bot.release import command_release_edit, command_release_new, roblox_info, steam_studio

ADMIN = SimpleNamespace(id=1, roles=[], guild_permissions=SimpleNamespace(administrator=True))
STRANGER = SimpleNamespace(id=2, roles=[], guild_permissions=SimpleNamespace(administrator=False))
PEGGLE = 'https://www.roblox.com/games/116662126806806/Thunderball-Deluxe'


async def call(fn, user, opts):
    out = []

    async def send_message(content=None, **kw):
        out.append(content)

    async def defer(**kw):
        pass

    async def edit_original_response(content=None, **kw):
        out.append(content)

    i = SimpleNamespace(user=user, response=SimpleNamespace(send_message=send_message, defer=defer), edit_original_response=edit_original_response)
    await fn(i, opts)
    return out[-1]


async def main():
    client = await boot()
    print('roblox   ->', await roblox_info(PEGGLE))
    print('steam    ->', await steam_studio('https://store.steampowered.com/app/391540/UNDERTALE/'))
    name = 'Test Game'
    set_source_link(name, ['1'], '2026-11-01', 'https://store.steampowered.com/app/391540/UNDERTALE/')
    print('bad link ->', await call(command_release_new, ADMIN, {'game': name, 'link': 'https://example.com'}))
    print('stranger ->', await call(command_release_new, STRANGER, {'game': name, 'link': PEGGLE}))
    print('new      ->', await call(command_release_new, ADMIN, {'game': name, 'link': PEGGLE}))
    row = one('SELECT * FROM game_status')
    print('  row:', {k: row[k] for k in ('name', 'status', 'link', 'roblox_name', 'creator', 'studio', 'original_name', 'hero_url')})
    print('stranger edit ->', await call(command_release_edit, STRANGER, {'game': name, 'title': 'x'}))
    print('empty edit    ->', await call(command_release_edit, ADMIN, {'game': name}))
    print('edit     ->', await call(command_release_edit, ADMIN, {'game': name, 'title': 'My Fixed Title', 'studio': 'Toby Fox'}))
    print('  title shown:', one('SELECT title, studio FROM game_status'))
    print('released list:', [r.get('title') or r['name'] for r in game_lists()['released']])
    run('DELETE FROM game_status')
    print('cleaned up')
    await finish(client)


asyncio.run(main())
