"""Adds a game that is on the unreleased board to the library WITHOUT announcing it: no new-game card, no @everyone ping, and it can never get a card later.
It is released like /release new does (the claim is completed, the pictures are checked), only silent. Run on the VM.
    python scripts/add_to_library.py --game="FNAF (all games)" --link=<Roblox link> --steam=<Steam app id> --title="Five Nights at Freddy's" --studio="Scott Cawthon" --yes"""
import asyncio
import sys

from _boot import boot, finish

from bot import board
from bot.cards import refresh_library
from bot.db import now, run
from bot.games import _find, clean_name, owner_ids, refresh_game_board
from bot.guard import check_release
from bot.release import roblox_info, steam_art


def arg(name):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return None


async def main():
    client = await boot()
    k, rel, dev = _find(arg('game'))
    if not dev:
        print('not in the unreleased list:', arg('game'), '| already released:', bool(rel))
        return await finish(client)
    link, title = arg('link'), arg('title') or clean_name(dev['name'])
    info = await roblox_info(link) or {}
    art = await steam_art(f"https://store.steampowered.com/app/{arg('steam')}/" if arg('steam') else dev.get('source_link'), title)
    studio = arg('studio') or art['studio']
    verdict = await check_release([art['art_hero_url'], art['art_url'], info.get('hero_url'), info.get('icon_url')], [title, info.get('name'), studio])
    print('owners:', owner_ids(dev), '| roblox:', info.get('name'), '| studio:', studio, '| art:', bool(art['art_url']), '| check:', verdict)
    if '--yes' not in sys.argv or verdict['flagged'] or not verdict['ok']:
        return await finish(client)
    run("""INSERT INTO game_status(key,name,owners,since,status,released_at,released_by,link,place_id,roblox_name,creator,hero_url,icon_url,studio,original_name,title,card_at)
        VALUES(?,?,?,?,'released',?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(key) DO UPDATE SET status='released', released_at=excluded.released_at, link=excluded.link, owners=excluded.owners, place_id=excluded.place_id,
        roblox_name=excluded.roblox_name, creator=excluded.creator, hero_url=excluded.hero_url, icon_url=excluded.icon_url, studio=excluded.studio,
        original_name=excluded.original_name, title=excluded.title, card_at=excluded.card_at""",
        k, dev['name'], ','.join(owner_ids(dev)), dev.get('since'), now(), (owner_ids(dev) or [None])[0], link, info.get('place_id'), info.get('name'),
        info.get('creator'), info.get('hero_url'), info.get('icon_url'), studio, title, title, now())
    run('UPDATE game_status SET art_url=?, art_hero_url=? WHERE key=?', art['art_url'], art['art_hero_url'], k)
    if board.is_live():
        board.set_completed(dev['name'], True)
        await board.reload_claims()
    await refresh_game_board()
    await refresh_library(force=True)
    print('added to the library, silently')
    await finish(client)


asyncio.run(main())
