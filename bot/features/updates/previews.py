"""/preview (admins): posts the bot's cards with real bugs and real games into the test channel, so a look can be judged before it goes live.
Buttons that could change something are switched off; nothing is saved."""
import time

import discord
from discord import ui

from bot.core.ctx import ctx, fetch_channel
from bot.core.db import all_, create_pending, del_pending, get_game, one
from bot.core.env import cfg
from bot.discord_ui.components import NO_MENTIONS
from bot.features.bugs.bugview import bug_embeds
from bot.features.bugs.devboard import board_card, exploit_card
from bot.features.bugs.fixlog import log_card, render_log
from bot.features.bugs.media import live_media
from bot.features.bugs.strikes import rules_card, strike_card
from bot.features.bugs.tester import tester_report_embed
from bot.features.games.board import build_embeds
from bot.features.updates.announce import draft_payload, polish_dev_updates


async def clear_channel(ch):
    """Deletes every message in the channel (bulk delete, then one by one for anything older than 14 days)."""
    total = 0
    for _ in range(30):
        msgs = [m async for m in ch.history(limit=100)]
        if not msgs:
            break
        done = 0
        recent = [m for m in msgs if (discord.utils.utcnow() - m.created_at).total_seconds() < 14 * 86400 - 60]
        try:
            if len(recent) > 1:
                await ch.delete_messages(recent)
                done = len(recent)
        except Exception:
            done = 0
        total += done
        if not done:
            for m in msgs:
                try:
                    await m.delete()
                    total += 1
                except Exception:
                    pass
    return total


def _off(view):
    """The same card with every button and picker switched off (a preview must not change anything)."""
    for item in view.walk_children():
        if isinstance(item, (ui.Button, ui.Select)) and not (isinstance(item, ui.Button) and item.url):
            item.disabled = True
    return view


async def post_previews(what='all'):
    """'all' wipes the test channel first. Returns how many cards were posted."""
    ch = await fetch_channel(cfg.test_id)
    if not ch:
        raise RuntimeError('Set TEST_CHANNEL_ID in .env')
    n = 0

    async def show(label, built, live=False):
        nonlocal n
        view, files = built
        await ch.send(label, allowed_mentions=NO_MENTIONS)
        await ch.send(view=view if live else _off(view), files=files, allowed_mentions=NO_MENTIONS)
        n += 1

    def want(k):
        return what in ('all', k)

    if what == 'all':
        await clear_channel(ch)
    open_ = all_("SELECT * FROM bugs WHERE routed=1 AND deleted=0 AND status IN ('new','investigating','fixing') ORDER BY id DESC LIMIT 30")
    with_media = []
    for b in open_:
        t = await fetch_channel(b['thread_id'])
        m = await live_media(t, b) if t else None
        if m and (m['images'] or m['videos']):
            with_media.append(b)
        if len(with_media) >= 2:
            break
    sample = ([*with_media] + [b for b in open_ if b not in with_media])[:2]

    if want('board'):
        key = next(iter(sorted({k['v'] for k in all_("SELECT substr(k, 11) v FROM kv WHERE k LIKE 'devthread:%'")})), 'unclaimed')
        await show("**Dev board** · the first message of a dev's post", board_card(key))
    if want('bug'):
        for b in sample:
            await show(f"**Bug page** · what a dev sees when browsing {b['id']}", await bug_embeds(b))
    if want('announcement'):
        fixed = all_("SELECT * FROM bugs WHERE status='fixed' AND game_tag_id IS NOT NULL ORDER BY fixed_at DESC LIMIT 40")
        if fixed:
            tag_id = fixed[0]['game_tag_id']
            game = get_game(tag_id) or {'tag_id': tag_id, 'name': fixed[0]['game_name']}
            mine = [f for f in fixed if f['game_tag_id'] == tag_id]
            polished = await polish_dev_updates(game['name'], ['added new map harbor', 'fixed bug where cars flip over randomly lol'])
            pid = create_pending({'tagId': tag_id, 'bugIds': [f['id'] for f in mine[:6]], 'bugfixes': [f['title'] for f in mine[:6]], 'updates': polished,
                                  'version': 'v1.1', 'owners': [], 'offer': True})
            draft = await draft_payload(pid)
            del_pending(pid)
            await show('**Update draft** · what the dev sees before posting', (draft['view'], draft['files']))
    if want('fixlog'):
        await show('**Fix log** · the pinned post in the dev forum (the picker works, it only reads)', log_card(), live=True)
        top = one("SELECT game_tag_id t FROM bugs WHERE status='fixed' GROUP BY game_tag_id ORDER BY COUNT(*) DESC LIMIT 1")
        page = await render_log((top['t'] or 'none') if top else 'all', 0)
        await show('**Fix log game page** · what the picker opens', (page['view'], page['attachments']))
    if want('rules'):
        await show('**Rules** · `/botrules`', rules_card())
    if want('mod') and sample:
        await show('**Mod-log · a strike that needs a developer** (example)',
                   strike_card(str(ctx.client.user.id), 3, 'kick', 'Spam reports in #bugs (example)', sample[0]['id'], True, 0))
        await show('**High-priority exploit card** (example)', exploit_card(sample[0], 'Example text of a report that explains how to abuse a bug.', False))
    if want('tester'):
        form = {'title': 'Car falls through the map', 'what': 'After the second checkpoint my car drops through the road and I fall forever',
                'steps': '1. Start a race on Harbor\n2. Drive past checkpoint 2\n3. Car falls through', 'expected': 'The car stays on the road', 'device': 'PS5'}
        bug = {'id': 99, 'game_name': 'Example game', 'title': 'Car falls through the map after checkpoint 2',
               'summary': 'The car drops through the road after the second checkpoint and falls forever.', 'severity': 'high',
               'created_at': int(time.time() * 1000), 'kind': 'bug'}
        await show('**Tester report** · what /bug posts in the testers forum (example)', tester_report_embed(bug, form, ctx.client.user.id, None))
    if want('games'):
        for label, built in zip(('Top suggestions', 'Unreleased games', 'Released games'), await build_embeds()):
            await show(f'**Bounty board · {label}**', built, live=True)
    return n
