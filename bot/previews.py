"""Posts the finished embeds (real bugs, real games) into the test channel so they can be judged before anything goes live."""
import time

import discord

from .announce import build_embeds, draft_payload, polish_dev_updates
from .botnews import board_news_embeds, bot_news_embeds, tester_news_embeds
from .bugview import bug_embeds
from .components import NO_MENTIONS, button, disable_all, make_view
from .ctx import ctx, fetch_channel
from .db import all_, create_pending, del_pending, get_game, kv_keys, one
from .devboard import board_embed, exploit_buttons, exploit_card
from .env import cfg
from .fixlog import log_components, log_embed, render_log
from .games import ensure_names, game_embeds, game_lists
from .media import live_media
from .strikes import LADDER_TEXT, rules_embed, strike_embed
from .tester import tester_report_embed
from .transcript import single_transcript
from .ui import E, EM


def sample_lists():
    """The first three unreleased games shown as released so both embeds can be judged. Nothing is saved."""
    live = game_lists()
    released = [{'key': g['key'], 'name': g['name'], 'owners': ','.join(g['owners']),
                 'released_at': int(time.time() * 1000) - k * 86400000,
                 'link': 'https://www.roblox.com/games/1' if k == 0 else None}
                for k, g in enumerate(live['unreleased'][:3])]
    rest = [dict(g) for g in live['unreleased'][3:]]
    for n, g in enumerate(rest):  # made-up progress so the tree can be judged
        if n % 3 == 0:
            g['progress'], g['working'] = 20 + (n * 17) % 75, 1
        elif n % 3 == 1:
            g['progress'], g['working'] = 10 + (n * 11) % 60, 0
    return {'released': released, 'unreleased': rest}


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


async def post_previews(what='all'):
    """Anything that could change a real bug, strike or announcement is shown with its buttons switched off.
    Only the fix log keeps live dropdowns, because they just read. 'all' wipes the channel first."""
    ch = await fetch_channel(cfg.test_id)
    if not ch:
        raise RuntimeError('Set TEST_CHANNEL_ID in .env')

    async def send(content, **extra):
        kw = {'content': content, 'allowed_mentions': NO_MENTIONS}
        kw.update(extra)
        return await ch.send(**kw)

    def want(k):
        return what == 'all' or what == k

    n = 0
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
        own = next((r['k'][len('devthread:'):] for r in kv_keys('devthread:') if r['k'][len('devthread:'):] != 'unclaimed'), None)
        if own:
            await send("**Dev board** · the first message of each dev's post (dropdowns not shown here)", embeds=[board_embed(own)])
            n += 1
        await send('**Dev board · unclaimed games**', embeds=[board_embed('unclaimed')])
        n += 1
    if want('bug'):
        for b in sample:
            await send(f"**Bug page** · what a dev sees when browsing #{b['id']} (buttons not shown here)", embeds=await bug_embeds(b))
            n += 1
    fixed = all_("SELECT * FROM bugs WHERE status='fixed' AND game_tag_id IS NOT NULL ORDER BY fixed_at DESC LIMIT 40")
    tag_id = fixed[0]['game_tag_id'] if fixed else None
    if want('announcement') and tag_id:
        game = get_game(tag_id) or {'tag_id': tag_id, 'name': fixed[0]['game_name']}
        mine = [f for f in fixed if f['game_tag_id'] == tag_id]
        lines = [f['title'] for f in mine[:6]]
        typed = ['added new map harbor', 'fixed bug where cars flip over randomly lol', 'made menu faster']
        polished = await polish_dev_updates(game['name'], typed)  # what the dev typed, rewritten by Claude
        pid = create_pending({'tagId': tag_id, 'bugIds': [f['id'] for f in mine[:6]], 'bugfixes': lines, 'updates': polished,
                              'version': 'v1.1', 'owners': [], 'offer': True})
        draft = await draft_payload(pid)
        del_pending(pid)
        await send('**Announcement draft** · what the dev gets (buttons off)',
                   content=f"**Announcement draft** · what the dev gets (buttons off)\n{draft['content']}",
                   embeds=draft['embeds'], view=disable_all(draft['view']))
        n += 1
        await send('**Public announcement** · what players see',
                   embeds=await build_embeds(game, lines, polished, 'v1.1'))
        n += 1
    if want('fixlog'):
        await send('**Fix log board** · the pinned post in #dev-bugs (dropdown works, read only)', embeds=[log_embed()], view=log_components())
        n += 1
        top = one("SELECT game_tag_id t FROM bugs WHERE status='fixed' GROUP BY game_tag_id ORDER BY COUNT(*) DESC LIMIT 1")
        page = await render_log((top['t'] or 'none') if top else 'all', 0)
        await send('**Fix log game page** · what the dropdown opens', **{**page, 'content': '**Fix log game page** · what the dropdown opens'})
        n += 1
    if want('rules'):
        await send('**Rules** · `/botrules`', embeds=[rules_embed()])
        n += 1
    if want('mod') and sample:
        card = strike_embed(str(ctx.client.user.id), 3, 'kick', 'Spam reports in #bugs (example)', sample[0]['id'], True)
        row = make_view([[button('x1', 'Confirm kick', discord.ButtonStyle.danger, True),
                          button('x2', 'Dismiss', discord.ButtonStyle.secondary, True)]])
        await send('**Mod-log · strike that needs a dev** (example user, buttons off)', embeds=[card], view=row)
        n += 1
        await send('**High-priority exploit card** · posted straight into the dev board, not mod-log (example, button off)',
                   embeds=[exploit_card(sample[0], 'Example text of a report that explains how to abuse a bug.', False)],
                   view=disable_all(exploit_buttons(sample[0]['id'], 'exploit')))
        n += 1
    if want('messages') and sample:
        b = sample[0]
        try:
            u = await ctx.client.fetch_user(int(b['reporter_id']))
        except Exception:
            u = None
        who = f"@{u.name if u else 'reporter'}"
        await send('\n\n'.join(t.replace(EM, ' ') for t in [
            '**Messages the bot writes** (names shown instead of pings)',
            f"{who} ❓ **NEEDS INFO**\nWhich device are you on, and what exactly happens?\n\n**STILL NEEDED**\n• Device / model\n• Steps to reproduce\n\nReply in this post and I will check again.",
            f"{E['new']} **LOGGED**{EM}·{EM}#{b['id']} is sent to the developer. Thanks for the report!",
            f"{E['investigating']} **INVESTIGATING**{EM}·{EM}A developer is looking into this.",
            f"{E['fixing']} **FIXING**{EM}·{EM}A fix is in progress.",
            f"{who} {E['fixed']} **FIXED**{EM}·{EM}{b['title']} (#{b['id']}). Thanks for reporting!",
            f"{E['duplicate']} **DUPLICATE**{EM}·{EM}of #12 \"Example\". Please add any extra details there.",
            f"{E['notbug']} **NOT A BUG**{EM}·{EM}Reviewed as intended behavior or a feature request.",
            f"{E['duplicate']} **REOPENED**{EM}·{EM}#{b['id']} is back on the board.",
            f"{E['warn']} **CLOSED**{EM}·{EM}The missing details never came in.",
            f"@dev {E['new']} **NEW BUG**{EM}·{EM}#{b['id']}{EM}·{EM}{b['game_name'] or 'Unknown game'} (ghost ping: deleted after 2 seconds)",
            f"{E['warn']} **STRIKE 1**{EM}·{EM}{ctx.guild.name} (DM)\nExample reason. This is a warning. The next steps are:\n{LADDER_TEXT}",
        ]))
        n += 1
    if want('tester'):
        form = {'title': 'Car falls through the map',
                'what': 'After the second checkpoint my car drops through the road and I fall forever',
                'steps': '1. Start a race on Harbor\n2. Drive past checkpoint 2\n3. Car falls through',
                'expected': 'The car stays on the road', 'device': 'PS5'}
        bug = {'id': 99, 'game_name': 'Example game', 'title': 'Car falls through the map after checkpoint 2',
               'summary': 'The car drops through the road after the second checkpoint and falls forever.',
               'severity': 'high', 'created_at': int(time.time() * 1000)}
        await send('**Tester report** · what /bug posts inside the thread in #testing (example)',
                   embeds=[tester_report_embed(bug, form, ctx.client.user.id, None)])
        n += 1
    if want('games'):
        await ensure_names()  # proper titles for the names typed on the bounty-board (cached)
        await send('**Games board** · built from the bounty-board, grouped by dev. SAMPLE: the first 3 unreleased games are shown as released. Post the real one with /games post',
                   embeds=await game_embeds(sample_lists()))
        n += 1
    if what == 'testernews':
        await send('**Tester announcement draft** · for the tester announcements channel. NOT posted there. Would ping: the Tester role only',
                   embeds=tester_news_embeds())
        n += 1
    if what == 'boardnews':
        await send('**Bounty board announcement draft** · for #📣┃announcements. NOT posted there, waiting for approval', embeds=board_news_embeds())
        n += 1
    if want('botnews'):
        await send('**Launch announcement draft** · for #📣┃announcements. NOT posted there, waiting for approval', embeds=bot_news_embeds())
        n += 1
    if want('transcript') and (with_media or sample):
        b = with_media[0] if with_media else sample[0]
        t = await single_transcript(b['id'])
        if t:
            await send(f"**Transcript** of #{b['id']}\n{t['note']}", files=t['files'])
            n += 1
    return n
