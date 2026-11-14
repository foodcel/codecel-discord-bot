"""/testing: put a game in testing, change its test link or note, take it out, and post a tester update.
A tester update works like /update for players: a private draft with the tester reports fixed since the last one, Edit and Post,
then the update card on the tester board (gone after 3 days), pinging the testers who signed up for the game (the tester board). The fixes it posts are
marked tested; once the game is released, tester fixes also go into the public /update like any other fix."""
import re

import discord
from discord import ui

from bot.core.db import all_, create_pending, del_pending, get_pending, run, set_pending
from bot.core.env import cfg
from bot.discord_ui.card import notice
from bot.discord_ui.components import NO_MENTIONS, FormModal, allowed, button
from bot.discord_ui.ui import E, EM

NL = chr(10)
DAYS = 3  # a tester update stays on the tester board this long


def _game(name):
    """(key, game row, shown name) of a game on the games lists, or (None, None, None)."""
    from bot.features.games.games import _find, clean_name
    k, rel, dev = _find(name)
    g = dev or rel
    return (k, g, g.get('title') or clean_name(g['name'])) if g else (None, None, None)


def waiting(k, names=()):
    """The tester reports of a game that are fixed and not in a tester update yet, oldest first."""
    from bot.features.bugs.tags import tag_name
    from bot.features.games.games import key
    keys = {k, *(key(n) for n in names if n)}
    rows = all_("SELECT * FROM bugs WHERE COALESCE(source,'')='tester' AND kind='bug' AND status='fixed' AND tested=0 AND deleted<>2 ORDER BY id")
    return [b for b in rows if key(b['game_name'] or '') in keys or (b['game_tag_id'] and key(tag_name(b['game_tag_id']) or '') in keys)]


def close_for_release(k, names=()):
    """The game is out: the tester fixes made before the release never reach the public update (players never had those bugs)."""
    from bot.features.bugs.tags import tag_name
    from bot.features.games.games import key
    keys = {k, *(key(n) for n in names if n)}
    rows = all_("SELECT id, game_name, game_tag_id FROM bugs WHERE COALESCE(source,'')='tester' AND status='fixed' AND announced=0")
    for b in rows:
        if key(b['game_name'] or '') in keys or (b['game_tag_id'] and key(tag_name(b['game_tag_id']) or '') in keys):
            run('UPDATE bugs SET announced=1 WHERE id=?', b['id'])


def _lines(text):
    return [l for l in (re.sub(r'^[\s•*\-–]+', '', x).strip() for x in (text or '').split(NL)) if l]


def _card(p, ping_text=None):
    from bot.core.db import one
    from bot.features.games.cards import update_card
    row = one('SELECT art_url, icon_url, hero_url, test_link FROM game_status WHERE key=?', p['key']) or {}
    return update_card({'name': p['name'], 'link': row.get('test_link')}, row, p['fixes'], p['test'], [], p.get('version') or '', ping_text,
                       poster=(p.get('owners') or [None])[0], testers=True)


def draft(pid):
    """The private draft: the card exactly as it will be posted, and Post / Edit / Cancel under it."""
    from bot.features.testers.testerboard import testers_of
    p = get_pending(pid)
    view, files = _card(p)
    n = len(testers_of(p['key']))
    view.add_item(ui.ActionRow(button(f'tup:post:{pid}', f"Post · pings {n} tester{'s' if n != 1 else ''}" if n else 'Post', discord.ButtonStyle.success),
                               button(f'tup:edit:{pid}', 'Edit'), button(f'tup:cancel:{pid}', 'Cancel', discord.ButtonStyle.danger)))
    return view, files


async def command_testing(i, sub, opts):
    from bot.features.games.games import apply_progress, owner_ids, owns
    name = opts.get('game')
    if sub != 'update':
        if sub == 'edit' and opts.get('link') is None and opts.get('note') is None:
            return await i.response.send_message('Give a new `link` or `note` (a single - removes it).', ephemeral=True)
        k, g, _ = _game(name)
        if sub in ('edit', 'off') and g and not g.get('testing_at'):
            return await i.response.send_message('That game is not in testing. Use `/testing on` first.', ephemeral=True)
        await i.response.defer(ephemeral=True, thinking=True)
        ok, text = await apply_progress(i.user, name, testing={'on': 'on', 'off': 'off'}.get(sub), link=opts.get('link'), note=opts.get('note'),
                                        ping=True, channel_is_test=str(i.channel_id) == str(cfg.test_id))
        if not ok:
            return await i.edit_original_response(content=text)
        return await i.edit_original_response(view=notice(f"{E['fixed']} **TESTING**{EM}·{EM}{text}")[0])
    k, g, shown = _game(name)
    if not g:
        return await i.response.send_message('That game is not in the list.', ephemeral=True)
    if not owns(i.user, owner_ids(g)):
        return await i.response.send_message('Only the dev who owns this game, or an admin, can post its tester updates.', ephemeral=True)
    if not g.get('testing_at'):
        return await i.response.send_message(f'{shown} is not in testing. Use `/testing on` first.', ephemeral=True)
    await i.response.defer(ephemeral=True, thinking=True)
    bugs = waiting(k, (g['name'], shown))
    lines = [b['title'] for b in bugs]
    if bugs:
        try:
            from bot.core.ai import draft_bug_fixes
            out = await draft_bug_fixes(shown, bugs)
            lines = out if len(out) == len(bugs) else lines
        except Exception as e:
            print('tester update lines', repr(e)[:120])
    pid = create_pending({'kind': 'testupdate', 'key': k, 'name': shown, 'owners': owner_ids(g), 'ids': [b['id'] for b in bugs],
                          'fixes': lines, 'test': [], 'version': ''})
    view, files = draft(pid)
    await i.edit_original_response(view=view, attachments=files)
    if not bugs:
        await i.followup.send('No fixed tester reports are waiting. Press Edit to write what changed and what to test.', ephemeral=True)


async def on_button(i, action, pid):
    from bot.features.games.games import owns
    pid = int(pid)
    p = get_pending(pid)
    if not p or p.get('kind') != 'testupdate':
        return await i.response.edit_message(view=notice('This draft is gone.')[0], attachments=[])
    if not owns(i.user, p['owners']):
        return await i.response.send_message('Only the dev who owns this game, or an admin, can do that.', ephemeral=True)
    if action == 'edit':
        def box(id_, label, style, value, mx):
            return {'id': id_, 'label': label, 'style': style, 'required': False, 'max': mx, 'value': value[:mx]}
        return await i.response.send_modal(FormModal(f'tupm:{pid}', 'Tester update', [
            box('fixes', 'Bug fixes (one per line)', 'paragraph', NL.join(p['fixes']), 3000),
            {**box('test', 'What to test (one per line, # line = heading)', 'paragraph', NL.join(p['test']), 3000),
             'placeholder': '# 🗺️ Chapter 2  (a line that starts with # is a heading; the lines under it are its points)'},
            box('version', 'Version or build (optional)', 'short', p.get('version') or '', 40)]))
    if action == 'cancel':
        del_pending(pid)
        return await i.response.edit_message(view=notice(f"{E['warn']} **CANCELLED**{EM}·{EM}Nothing was posted.")[0], attachments=[])
    if not p['fixes'] and not p['test']:
        return await i.response.send_message('Nothing to post yet. Press Edit and write a fix or what to test.', ephemeral=True)
    await i.response.defer()
    del_pending(pid)  # first, so a double press cannot post twice
    try:
        url, pinged = await publish(p)
    except Exception:
        set_pending(pid, p)  # not posted: the draft stays
        raise
    if not url:
        return await i.followup.send('The tester board channel is not set up.', ephemeral=True)
    who = f'{pinged} tester(s) pinged' if pinged else 'no ping'
    await i.edit_original_response(view=notice(f"{E['fixed']} **POSTED**{EM}·{EM}{url} ({who})")[0], attachments=[])


async def publish(p, ping=True):
    """Posts a tester update on the tester board: p = {'key', 'name', 'owners', 'ids', 'fixes', 'test', 'version'}. The /testing update button and the MCP use it.
    ping: the testers who joined the game are pinged. The card goes after DAYS days; the fixes it lists are marked tested. Returns (url, how many were pinged)."""
    from bot.core.ctx import fetch_channel
    from bot.core.db import add_timer, kv_set, now
    from bot.features.testers.testerboard import testers_of
    ch = await fetch_channel(cfg.future_games_id) if cfg.future_games_id else None
    if not ch:
        return None, 0
    testers = testers_of(p['key']) if ping else []
    view, files = _card(p, ' '.join(f'<@{u}>' for u in testers) or None)
    sent = await ch.send(view=view, files=files, allowed_mentions=allowed(users=testers) if testers else NO_MENTIONS)
    add_timer('delete_card', f'{ch.id}:{sent.id}', now() + DAYS * 86400000)  # the tester board stays short: the update goes after 3 days
    for b in p['ids']:
        run('UPDATE bugs SET tested=1 WHERE id=?', b)
    kv_set(f"testupdate:{p['key']}", now())  # when the last one went out (the MCP waits between posts)
    return sent.jump_url, len(testers)


async def on_modal(i, pid, fields):
    from bot.features.games.games import owns
    pid = int(pid)
    p = get_pending(pid)
    if not p or p.get('kind') != 'testupdate':
        return await i.response.send_message('This draft is gone.', ephemeral=True)
    if not owns(i.user, p['owners']):
        return await i.response.send_message('Only the dev who owns this game, or an admin, can do that.', ephemeral=True)
    p.update(fixes=_lines(fields.get('fixes')), test=_lines(fields.get('test')), version=(fields.get('version') or '').strip()[:40])
    set_pending(pid, p)
    view, files = draft(pid)
    await i.response.edit_message(view=view, attachments=files)
