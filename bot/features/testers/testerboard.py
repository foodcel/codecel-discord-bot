"""The tester board: one pinned message in #future-games that lists every game in testing with its dev and its volunteer testers (shown as
mentions), a dropdown to volunteer for a game and a button to leave one. When a game goes into testing a small card with an "I want to test"
button is posted for a day and pings Helpers. Everything is answered by custom id (tbd:...), so the buttons keep working after a restart."""
import json
import time
from datetime import datetime, timezone

import discord
from discord import ui

from bot.discord_ui.card import notice
from bot.features.updates.botnews import date_button, strip, tree
from bot.discord_ui.pngs import fit, with_strip
from bot.discord_ui.components import NO_MENTIONS
from bot.core.ctx import fetch_channel
from bot.core.db import add_timer, all_, kv_get, kv_set, now, one, run
from bot.core.env import cfg
from bot.features.games.games import clean_name, game_lists, owner_ids
from bot.core.perms import level
from bot.discord_ui.ui import E, EM

CARD_HOURS = 24
NL = chr(10)
FOOTER = [
    '🙋 · pick one or more games to join them, pick a game again to leave it',
    '`/progress testing:on` · put your game in testing',
    '`/bug` · testers report them in the testing channel',
]


def testing_games():
    """The games in the testing phase (unreleased and released), newest first: dicts with key, name, owners, since (ms) and the row's link."""
    lists = game_lists()
    out = []
    for g in [*lists['unreleased'], *lists['released']]:
        if g.get('testing_at'):
            out.append({'key': g['key'], 'name': g.get('title') or clean_name(g['name']), 'owners': owner_ids(g), 'since': g['testing_at'], 'link': g.get('link'),
                        'test_link': (one('SELECT test_link FROM game_status WHERE key=?', g['key']) or {}).get('test_link')})
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


def board_view():
    """The board as a card: the title with the date on the right, a line, the games, a line, the commands. The picker is below the card."""
    strip_ = strip()
    games = testing_games()
    items = [ui.Section('### 🧪 Tester board', accessory=date_button()), ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)]  # the date of the last change, on the right
    if not games:
        items.append(ui.TextDisplay('No game is in testing right now.'))
    for g in games:
        rows = [('Dev', ' '.join(f'<@{o}>' for o in g['owners']) or '—'), ('Since', f"<t:{g['since'] // 1000}:D>")]
        rows += [('Tester', f'<@{u}>') for u in testers_of(g['key'])] or [('Testers', 'nobody yet')]
        block = f"**🎮 {g['name']}**{NL}{tree(*rows)}"
        # a game with a test link gets its Play button on the right of its block (the only thing a card can put on the right)
        items.append(ui.Section(block, accessory=ui.Button(style=discord.ButtonStyle.link, label='Play test', url=g['test_link'], emoji='▶️')) if g.get('test_link') else ui.TextDisplay(block))
    items += [ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small), ui.TextDisplay(NL.join('-# ' + x for x in FOOTER))]
    view = ui.LayoutView(timeout=None)
    items = fit(items, keep_tail=2, extra_parts=2 if games else 0)
    items, strip_ = with_strip(items)
    view.add_item(ui.Container(*items))
    if games:  # the picker sits below the card, outside it: one dropdown where you pick every game you test (pick none to leave them all)
        picks = games[:25]
        view.add_item(ui.ActionRow(ui.Select(custom_id='tbd:pick', placeholder='🙋 Pick a game to join or leave it…', min_values=1, max_values=len(picks),
                                            options=[discord.SelectOption(label=g['name'][:100], value=g['key'], description=f"testing since {date(g['since'])}") for g in picks])))
    return view, [strip_]


async def refresh_board():
    """Keeps one pinned message in #future-games up to date. The old board was an embed: it is replaced by this card once."""
    ch = await fetch_channel(cfg.future_games_id)
    if not ch:
        return
    ref = json.loads(kv_get('testing_board') or '{}')
    view, files = board_view()
    if ref.get('message') and str(ref.get('channel')) == str(ch.id):
        try:
            await ch.get_partial_message(int(ref['message'])).edit(view=view, attachments=files, allowed_mentions=NO_MENTIONS)
            return
        except discord.NotFound:
            pass  # deleted: posted again below
        except Exception as e:
            print('tester board edit', repr(e)[:150])  # anything else: logged, never a repost (a repost loop would spam the channel)
            return
        view, files = board_view()  # the files can be sent once
    msg = await ch.send(view=view, files=files, allowed_mentions=NO_MENTIONS)
    if ref.get('message'):
        try:
            await ch.get_partial_message(int(ref['message'])).delete()
        except Exception:
            pass
    kv_set('testing_board', json.dumps({'channel': str(ch.id), 'message': str(msg.id)}))
    try:
        await msg.pin()
        async for m in ch.history(limit=5):  # the "pinned a message" line is removed
            if m.type == discord.MessageType.pins_add:
                await m.delete()
    except Exception as e:
        print('pin tester board', repr(e))


def card_view(g, ping=True):
    """The card of a game that just went into testing: (view, files, role pinged). The ping and the date are inside the card."""
    row = one('SELECT art_url, icon_url, hero_url, test_link FROM game_status WHERE key=?', g['key']) or {}
    role = cfg.tester_ping_role if ping else None
    devs = ' '.join(f'<@{o}>' for o in g['owners']) or '—'
    text = NL.join([f"### 🧪 {g['name']} needs testers", f'-# dev {devs}'] + ([f'-# <@&{role}>'] if role else []) + [f'-# <t:{int(time.time())}:D>'])  # dev, the ping and the date, one under the other
    cover = row.get('art_url') or row.get('icon_url') or row.get('hero_url')
    strip_ = strip()
    view = ui.LayoutView(timeout=None)
    parts, strip_ = with_strip([ui.Section(text, accessory=ui.Thumbnail(cover)) if cover else ui.TextDisplay(text),
                                ui.ActionRow(ui.Button(custom_id=f"tbd:join:{g['key']}", label='I want to test', style=discord.ButtonStyle.success, emoji='🙋'),
                                             *([ui.Button(style=discord.ButtonStyle.link, label='Play test', url=row['test_link'], emoji='▶️')] if row.get('test_link') else []))])
    view.add_item(ui.Container(*parts))
    return view, [strip_], role


async def post_card(g, ping=True):
    """The small card for a game that just went into testing: pings the Tester role, has the volunteer button, and goes away after a day."""
    ch = await fetch_channel(cfg.future_games_id)
    if not ch:
        return None
    view, files, role = card_view(g, ping)
    sent = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions(roles=[discord.Object(id=int(role))], everyone=False, users=False) if role else NO_MENTIONS)
    add_timer('delete_card', f'{ch.id}:{sent.id}', now() + CARD_HOURS * 3600000)
    kv_set(f"testcard:{g['key']}", json.dumps({'channel': str(ch.id), 'message': str(sent.id), 'ping': bool(role), 'owners': g['owners'], 'name': g['name']}))  # to edit it in place later (a new Play link)
    return sent


async def update_card(game_key):
    """The card of a game that went into testing, edited in place (its Play button follows the game's test link). Does nothing once the card is gone."""
    ref = json.loads(kv_get(f'testcard:{game_key}') or 'null')
    if not ref:
        return False
    try:
        ch = await fetch_channel(ref['channel'])
        msg = await ch.fetch_message(int(ref['message']))
        view, files, _ = card_view({'key': game_key, 'name': ref['name'], 'owners': ref['owners']}, ref['ping'])
        await msg.edit(view=view, attachments=files, allowed_mentions=NO_MENTIONS)  # an edit never pings again: the mention stays as it was sent
        return True
    except Exception as e:
        print('update tester card', repr(e)[:120])
        return False


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
    return await i.edit_original_response(view=notice(f"{E['fixed']} **You test it**{EM}·{EM}{games[k]['name']} now. The tester board shows you.")[0])


async def on_button(i, action, arg):
    if action == 'join':  # the button on the card of a game that just went into testing
        await i.response.defer(ephemeral=True, thinking=True)
        return await _join(i, arg)


async def on_select(i, action, values):
    """The dropdown on the board: every game you pick flips: you join it, or leave it if you already test it."""
    if action != 'pick':
        return
    await i.response.defer(ephemeral=True, thinking=True)
    if not can_volunteer(i.user):
        return await i.edit_original_response(content='Only testers and helpers can volunteer.')
    shown = {g['key']: g for g in testing_games()[:25]}
    me = str(i.user.id)
    joined, left = [], []
    for k in [v for v in values if v in shown]:
        if me in testers_of(k):
            run('DELETE FROM game_testers WHERE game_key=? AND user_id=?', k, me)
            left.append(shown[k]['name'])
        else:
            run('INSERT OR IGNORE INTO game_testers(game_key,user_id,at) VALUES(?,?,?)', k, me, now())
            joined.append(shown[k]['name'])
    await refresh_board()
    lines = ([f"{E['fixed']} You test " + ', '.join(f'**{n}**' for n in joined) + ' now.'] if joined else []) + (["🚪 You left " + ', '.join(f'**{n}**' for n in left) + '.'] if left else [])
    return await i.edit_original_response(view=notice(NL.join(lines) or 'Nothing changed.')[0])
