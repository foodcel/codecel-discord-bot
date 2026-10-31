"""Audits /release and /unrelease against the live bounty-board: every claim is released and moved back with a fake owner,
a fake stranger and a fake admin, and the lists are compared with the board each time. Puts everything back."""
import asyncio
from types import SimpleNamespace

from _boot import boot, finish

from bot.bounty import get_claims
from bot.db import run
from bot.env import cfg
from bot.games import NONE, clean_name, command_gamelink, command_release, game_embeds, game_lists, key


def member(id_, admin=False, dev=False):
    roles = [SimpleNamespace(id=int(cfg.dev_role))] if dev else []
    return SimpleNamespace(id=id_, roles=roles, guild_permissions=SimpleNamespace(administrator=admin))


async def call(user, undo, game, link=None):
    out = []

    async def send_message(content=None, **kw):
        out.append(content)

    i = SimpleNamespace(user=user, response=SimpleNamespace(send_message=send_message))
    await command_release(i, {'game': game, 'link': link}, undo)
    return out[0]


async def main():
    client = await boot()
    run('DELETE FROM game_status')
    claims = get_claims()
    keys = [key(c['name']) for c in claims]
    problems = []
    print('claims:', len(claims), '| distinct keys:', len(set(keys)))
    if len(set(keys)) != len(keys):
        problems.append('two bounty-board entries share one key: ' + str([k for k in set(keys) if keys.count(k) > 1]))
    admin = member(1, admin=True)
    stranger = member(2, dev=True)
    for c in claims:
        k = key(c['name'])
        owner = member(int(c['owners'][0]), dev=True) if c['owners'] else None
        who = f"{clean_name(c['name'])} (owners {c['owners'] or 'none'})"
        if c['owners']:
            r = await call(stranger, False, c['name'])
            if 'Only the dev' not in r:
                problems.append(f'{who}: a stranger could release it: {r}')
        for user, label in ((owner, 'owner'), (admin, 'admin')):
            if user is None:
                continue
            r = await call(user, False, c['name'], 'https://example.com/play')
            lists = game_lists()
            ok = ('RELEASED' in r and any(x['key'] == k for x in lists['released'])
                  and not any(x['key'] == k for x in lists['unreleased']) and len(lists['unreleased']) == len(claims) - 1)
            if not ok:
                problems.append(f'{who}: release as {label} failed: {r}')
            await game_embeds(lists)  # the board still builds
            r = await call(user, True, c['name'])
            lists = game_lists()
            ok = ('UNRELEASED' in r and not lists['released'] and len(lists['unreleased']) == len(claims))
            if not ok:
                problems.append(f'{who}: unrelease as {label} failed: {r}')
        if not c['owners']:  # nobody owns it: only an admin may change it
            r = await call(stranger, False, c['name'])
            if 'Only the dev' not in r:
                problems.append(f'{who}: a dev could release a game nobody owns: {r}')
    # /gamelink: the link shows on the unreleased game, survives release / unrelease, and a stranger cannot set it
    c = claims[0]
    out = []

    async def send_message(content=None, **kw):
        out.append(content)

    async def link(user, url):
        out.clear()
        await command_gamelink(SimpleNamespace(user=user, response=SimpleNamespace(send_message=send_message)), {'game': c['name'], 'link': url})
        return out[0]

    if c['owners'] and 'Only the dev' not in await link(stranger, 'https://store.steampowered.com/app/1'):
        problems.append('a stranger could set a game link')
    if 'LINKED' not in await link(admin, 'https://store.steampowered.com/app/1'):
        problems.append('/gamelink failed')
    if 'http://' not in await link(admin, 'ftp://x'):
        problems.append('/gamelink accepted a bad link')
    shown = [f.value for e in await game_embeds() for f in e.fields]
    if not any('](https://store.steampowered.com/app/1)' in v for v in shown):
        problems.append('the link is not shown on the unreleased board')
    await call(admin, False, c['name'], 'https://www.roblox.com/games/1')
    shown = [f.value for e in await game_embeds() for f in e.fields]
    if not any('](https://www.roblox.com/games/1)' in v for v in shown):
        problems.append('the Roblox link is not shown on the released board')
    if 'LINKED' not in await link(admin, 'https://www.roblox.com/games/2'):
        problems.append('/gamelink failed on a released game')
    if not any(r['link'] == 'https://www.roblox.com/games/2' for r in game_lists()['released']):
        problems.append('/gamelink did not change the Roblox link of a released game')
    await call(admin, True, c['name'])
    if game_lists()['unreleased'][0].get('source_link') is None and not any(g.get('source_link') for g in game_lists()['unreleased']):
        problems.append('the source link was lost after unrelease')
    print('empty-list entry:', await call(admin, False, NONE))
    print('empty-list entry (unrelease):', await call(admin, True, NONE))
    # a released game that the bounty-board no longer lists must stay in Released, and /unrelease must bring it back
    run("INSERT INTO game_status(key,name,owners,since,status,released_at) VALUES('gonegame','Gone Game','1','2026-01-01','released',1700000000000)")
    r = await call(admin, True, 'Gone Game')
    print('unrelease of a game that left the board:', r)
    run('DELETE FROM game_status')
    lists = game_lists()
    print('final: unreleased', len(lists['unreleased']), '| released', len(lists['released']))
    print('PROBLEMS:' if problems else 'ALL OK', *problems, sep='\n  ')
    await finish(client)


asyncio.run(main())
