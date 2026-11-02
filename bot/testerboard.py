"""The tester board: one pinned message in #future-games that lists every game in testing with its dev and its volunteer testers (shown as
mentions), a dropdown to volunteer for a game and a button to leave one. When a game goes into testing a small card with an "I want to test"
button is posted for a day and pings Helpers. Everything is answered by custom id (tbd:...), so the buttons keep working after a restart."""
import json
from datetime import datetime, timezone

import discord
from discord import ui

from .botnews import make, strip, tree
from .components import NO_MENTIONS
from .ctx import fetch_channel
from .db import add_timer, all_, kv_get, kv_set, now, one, run
from .env import cfg
from .games import clean_name, game_lists, key, owner_ids
from .perms import level
from .ui import E, flat, head, section, gap

CARD_HOURS = 24
NL = chr(10)
FOOTER = [
    '🙋 · pick the games you test: pick again to change the list',
    '/progress testing:on · put your game in testing',
    '/bug · testers report them in the testing channel',
]


def testing_games():
    """The games in the testing phase (unreleased and released), newest first: dicts with key, name, owners, since (ms) and the row's link."""
    lists = game_lists()
    out = []
    for g in [*lists['unreleased'], *lists['released']]:
        if g.get('testing_at'):
            out.append({'key': g['key'], 'name': g.get('title') or clean_name(g['name']), 'owners': owner_ids(g), 'since': g['testing_at'], 'link': g.get('link')})
    return sorted(out, key=lambda g: -g['since'])


def testers_of(game_key):
    return [r['user_id'] for r in all_('SELECT user_id FROM game_testers WHERE game_key=? ORDER BY at', game_key)]


def date(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%b %d').replace(' 0', ' ')


def can_volunteer(member):
    """Testers, Helpers, devs and admins."""
    if level(member) != 'none':
        return True
    roles = {str(r.id) for r in getattr(member, 'roles', [])}
    return bool(roles & set(cfg.tester_roles)) or cfg.helpers_role in roles


def board_embed():
    e = flat()
    e.title = head('🧪', 'Tester board')
    games = testing_games()
    if not games:
        e.description = 'No game is in testing right now.'
    for g in games:
        rows = [('Dev', ' '.join(f'<@{o}>' for o in g['owners']) or '—'), ('Since', date(g['since']))]
        rows += [('Tester', f'<@{u}>') for u in testers_of(g['key'])] or [('Testers', 'nobody yet')]
        section(e, head('🎮', g['name']), tree(*rows))
    gap(e)
    e.set_footer(text=NL.join(FOOTER))
    e.set_image(url='attachment://width.png')
    return e


def board_view():
    """One dropdown where you pick every game you test (pick none to leave them all). Nobody needs a leave button."""
    view = ui.View(timeout=None)
    games = testing_games()[:25]
    if games:
        view.add_item(ui.Select(custom_id='tbd:pick', placeholder='🙋 Pick the games you test…', min_values=0, max_values=len(games),
                                options=[discord.SelectOption(label=g['name'][:100], value=g['key'], description=f"testing since {date(g['since'])}") for g in games]))
    return view


async def refresh_board():
    """Keeps one pinned message in #future-games up to date; posted again when it was deleted."""
    ch = await fetch_channel(cfg.future_games_id)
    if not ch:
        return
    embed, view = board_embed(), board_view()
    ref = json.loads(kv_get('testing_board') or '{}')
    if ref.get('message') and str(ref.get('channel')) == str(ch.id):
        try:
            await ch.get_partial_message(int(ref['message'])).edit(embeds=[embed], view=view, attachments=[strip()])
            return
        except Exception:
            pass
    msg = await ch.send(embeds=[embed], view=view, files=[strip()])
    kv_set('testing_board', json.dumps({'channel': str(ch.id), 'message': str(msg.id)}))
    try:
        await msg.pin()
        async for m in ch.history(limit=5):  # the "pinned a message" line is removed
            if m.type == discord.MessageType.pins_add:
                await m.delete()
    except Exception as e:
        print('pin tester board', repr(e))


async def post_card(g, ping=True):
    """The small card for a game that just went into testing: pings Helpers, has the volunteer button, and goes away after a day."""
    ch = await fetch_channel(cfg.future_games_id)
    if not ch:
        return None
    row = one('SELECT art_url, icon_url, hero_url FROM game_status WHERE key=?', g['key']) or {}
    e = make(g['name'] + ' needs testers', [
        ('🙋', 'Volunteer', [('Dev', ' '.join(f'<@{o}>' for o in g['owners']) or '—'), ('Testers', 'press the button to join')])],
        ['🙋 · volunteer as a tester', 'The tester board is updated by itself'], emoji='🧪')
    cover = row.get('art_url') or row.get('icon_url') or row.get('hero_url')
    if cover:
        e.set_thumbnail(url=cover)
    view = ui.View(timeout=None)
    view.add_item(ui.Button(custom_id=f"tbd:join:{g['key']}", label='I want to test', style=discord.ButtonStyle.success, emoji='🙋'))
    role = cfg.helpers_role if ping else None
    sent = await ch.send(content=f'<@&{role}>' if role else None, embeds=[e], files=[strip()], view=view,
                         allowed_mentions=discord.AllowedMentions(roles=[discord.Object(id=int(role))]) if role else NO_MENTIONS)
    add_timer('delete_card', f'{ch.id}:{sent.id}', now() + CARD_HOURS * 3600000)
    return sent


async def _join(i, k):
    games = {g['key']: g for g in testing_games()}
    if k not in games:
        return await i.edit_original_response(content='That game is not in testing any more.')
    if not can_volunteer(i.user):
        return await i.edit_original_response(content='Only testers and helpers can volunteer.')
    if str(i.user.id) in testers_of(k):
        return await i.edit_original_response(content=f"You already test **{games[k]['name']}**.")
    run('INSERT OR IGNORE INTO game_testers(game_key,user_id,at) VALUES(?,?,?)', k, str(i.user.id), now())
    await refresh_board()
    return await i.edit_original_response(content=f"{E['fixed']} You test **{games[k]['name']}** now. The tester board shows you.")


async def on_button(i, action, arg):
    if action == 'join':  # the button on the card of a game that just went into testing
        await i.response.defer(ephemeral=True)
        return await _join(i, arg)


async def on_select(i, action, values):
    """The dropdown on the board: the games you picked are the games you test (what you picked before is replaced)."""
    if action != 'pick':
        return
    await i.response.defer(ephemeral=True)
    if not can_volunteer(i.user):
        return await i.edit_original_response(content='Only testers and helpers can volunteer.')
    shown = {g['key']: g for g in testing_games()[:25]}
    chosen = [v for v in values if v in shown]
    me = str(i.user.id)
    for k in shown:
        if k not in chosen:
            run('DELETE FROM game_testers WHERE game_key=? AND user_id=?', k, me)
    for k in chosen:
        run('INSERT OR IGNORE INTO game_testers(game_key,user_id,at) VALUES(?,?,?)', k, me, now())
    await refresh_board()
    text = (f"{E['fixed']} You test " + ', '.join(f"**{shown[k]['name']}**" for k in chosen) + '. Pick again any time to change the list.') if chosen else 'You no longer test any game.'
    return await i.edit_original_response(content=text)
