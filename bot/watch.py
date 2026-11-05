"""Watches the released games: every 5 minutes the bot asks Roblox if each game is still there. A game that Roblox no longer shows
(no title, deleted, taken down) is marked Offline in the library after 2 checks in a row, and its dev is pinged in dev chat. When it comes back
the bot switches it on again and says so. A game a dev marked offline by hand is never switched back on by the bot."""
import asyncio
import json


from .env import cfg
from .components import allowed
from .ctx import fetch_channel
from .db import all_, kv_get, kv_set, run
from .games import clean_name, owner_ids, refresh_game_board
from .links import roblox_place
from .release import _json
from .ui import EM

DEV_CHAT = cfg.dev_chat_id
EVERY = 300      # seconds between two checks of all games
FAILS = 2        # checks in a row that must fail before a game is called down


async def is_up(link):
    """True: Roblox shows the game. False: it does not (taken down or deleted). None: could not tell (Roblox did not answer)."""
    place = roblox_place(link)
    if not place:
        return None
    u = await _json(f'https://apis.roblox.com/universes/v1/places/{place}/universe')
    if u is None:
        return None
    uid = u.get('universeId')
    if not uid:
        return False
    g = await _json(f'https://games.roblox.com/v1/games?universeIds={uid}')
    if g is None:
        return None
    data = g.get('data') or []
    if not data:
        return False
    return 'TITLE UNAVAILABLE' not in str(data[0].get('name') or '').upper()


def _state():
    try:
        return json.loads(kv_get('watch') or '{}')
    except Exception:
        return {}


def forget(game_key):
    """A dev switched the game on or off by hand: the bot starts from nothing for it."""
    st = _state()
    if st.pop(game_key, None) is not None:
        kv_set('watch', json.dumps(st))


async def _tell(row, text):
    owners = owner_ids(row)
    ch = await fetch_channel(DEV_CHAT)
    if not ch:
        return
    ping = ' '.join(f'<@{o}>' for o in owners)
    await ch.send(f'{ping} {text}'.strip(), allowed_mentions=allowed(users=owners))


async def sweep():
    """One round over every released game."""
    st = _state()
    changed = False
    for row in all_("SELECT * FROM game_status WHERE status='released' AND link IS NOT NULL"):
        k, name = row['key'], clean_name(row.get('title') or row['name'])
        up = await is_up(row['link'])
        if up is None:
            continue
        s = st.get(k) or {'fails': 0, 'auto': False}
        offline = row.get('online') == 0
        if up:
            s['fails'] = 0
            if offline and s.get('auto'):
                run('UPDATE game_status SET online=1 WHERE key=?', k)
                s['auto'] = False
                changed = True
                await _tell(row, f"🟢 **GAME BACK**{EM}·{EM}**{name}** is on Roblox again. I switched it back on in the library.")
        else:
            s['fails'] += 1
            if s['fails'] >= FAILS and not offline:
                run('UPDATE game_status SET online=0 WHERE key=?', k)
                s['auto'] = True
                changed = True
                await _tell(row, f"🔴 **GAME DOWN**{EM}·{EM}**{name}** is gone from Roblox (no title, it looks taken down). I marked it offline in the library. "
                                 f"I check every 5 minutes and switch it back on when it returns.")
        st[k] = s
    kv_set('watch', json.dumps(st))
    if changed:
        await refresh_game_board()


async def watch_loop():
    await asyncio.sleep(60)  # let the bot finish starting
    while True:
        try:
            await sweep()
        except Exception as e:
            print('game watch', repr(e))
        await asyncio.sleep(EVERY)
