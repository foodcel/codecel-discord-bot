"""New posts in the bug forum: Claude checks them, tags them, asks for missing info, spots duplicates, exploits and trolls."""
import asyncio
import io
import re

import discord

from bot.features.bugs import replies
from bot.discord_ui.card import words
from bot.features.bugs.nums import label
from bot.core.ai import analyze_report, still_broken
from bot.discord_ui.components import allowed
from bot.core.ctx import fetch_channel, dm, get_member, sleep
from bot.core.db import (add_timer, all_, bug_by_id, bug_by_thread, cancel_timers, kv_get, kv_set, now, run, update_bug)
from bot.features.bugs.devboard import post_exploit, route_bug
from bot.features.bugs.fixes import reopen
from bot.core.perms import is_staff, level
from bot.features.bugs.strikes import strike_user
from bot.features.bugs.tags import applied_ids, find_device_tag, find_game_tag, game_tags, set_tags, tag_name, thread_game_tag
from bot.discord_ui.ui import E

DAY = 86400000
MAX_ASKS = 3  # questions to the player; after that the report is logged anyway and a dev is told to look into it
CONFIDENT = 0.85
_IMG = re.compile(r'^image/(png|jpe?g|gif|webp)')


async def fetch_starter(thread):
    for _ in range(4):
        try:
            return await thread.fetch_message(thread.id)
        except Exception:
            await sleep(1500)
    return None


def _text(m):
    """The words of a message: its text, or for a post made by the bot (a card, or an old embed) its text parts."""
    return words(m)


async def gather(thread, bug):
    msgs = [m async for m in thread.history(limit=50)]
    # a post made by /bug or /suggest is written by the bot for the player: its first message counts as the player's own
    def is_player_answer(m):  # anyone who is not the bot and not staff may answer the questions (another player who saw the same bug, for example)
        return not m.author.bot and not (isinstance(m.author, discord.Member) and level(m.author) in ('admin', 'dev', 'jr'))
    mine = sorted((m for m in msgs if str(m.author.id) == bug['reporter_id'] or (bug.get('source') == 'form' and m.id == thread.id) or is_player_answer(m)),
                  key=lambda m: m.created_at)
    atts = [a for m in mine for a in m.attachments]
    return {
        'text': '\n---\n'.join(_text(m) for m in mine if _text(m)),
        'images': [a.url for a in atts if _IMG.search(a.content_type or '')],
        'videos': [a.filename for a in atts if (a.content_type or '').startswith('video/')],
    }


async def intake_thread(thread, silent=False):
    if bug_by_thread(thread.id):
        return
    if thread.flags.pinned:
        return
    starter = await fetch_starter(thread)
    if not starter or starter.author.bot:
        return
    cur = run('INSERT INTO bugs(thread_id,reporter_id,title,status,created_at,last_msg_id) VALUES(?,?,?,?,?,?)',
              str(thread.id), str(starter.author.id), thread.name, 'new', now(), str(thread.last_message_id or starter.id))
    await analyze_and_act(bug_by_id(cur.lastrowid), thread, silent=silent)


async def analyze_and_act(bug, thread, silent=False, followup=False):
    from bot.core.ai import allow_user
    if not silent and not allow_user(bug['reporter_id']):
        print('ai: hourly limit for', bug['reporter_id'], '- report', bug['id'], 'waits')
        return  # stays as it is; the catch-up checks it again
    report = await gather(thread, bug)
    games = [t['name'] for t in game_tags()]
    picked = [n for n in (tag_name(i) for i in applied_ids(thread)) if n]
    known = all_("""SELECT id,title,summary,status,game_name FROM bugs
        WHERE kind='bug' AND id<>? AND status IN ('new','needs_info','investigating','fixing','fixed') AND deleted IN (0,1)
          AND COALESCE(source,'') <> 'tester'
        ORDER BY id DESC LIMIT 40""", bug['id'])  # never the private tester reports: a duplicate reply would show their title and link in public
    try:
        a = await analyze_report(re.sub(r'^#\d+\s+', '', thread.name), report['text'], picked, games,
                                 report['images'], report['videos'], known, bug['asks'])
    except Exception as e:
        print('analyze failed:', e)
        return  # stays status=new, routed=0; catch-up retries later

    game_tag = thread_game_tag(thread) or find_game_tag(a.get('game'))
    device_tag = find_device_tag(a.get('device'))
    update_bug(bug['id'], {
        'game_tag_id': game_tag['id'] if game_tag else None,
        'game_name': game_tag['name'] if game_tag else (a.get('game') or None),
        'title': a.get('title') or bug['title'], 'summary': a['summary'], 'severity': a['severity'],
    })
    bug = bug_by_id(bug['id'])
    reporter_member = await get_member(bug['reporter_id'])
    staff_reporter = is_staff(reporter_member)
    dev_report = reporter_member is not None and level(reporter_member) in ('admin', 'dev', 'jr')  # a developer reporting a bug themselves: no questions, nothing closed
    gid = game_tag['id'] if game_tag else None
    did = device_tag['id'] if device_tag else None

    # 1. Exploit: never leave it public.
    if a['exploit'] and not staff_reporter:
        # The post is deleted, so the reporter is told it was received and why, and gets a message again when a dev changes its status.
        dm_ok = True
        if not silent:
            update_bug(bug['id'], {'status': 'exploit', 'deleted': 1})
            dm_ok = await dm(bug['reporter_id'],
                             f"{E['lock']} **REPORT RECEIVED**\nThanks for telling us. Your report \"{bug['title']}\" was removed from the channel on purpose, because it explains how to abuse a bug and others could copy it. The developers have it now. I will message you here when it is fixed, so please do not post it again.")
        await post_exploit(bug, report['text'], silent, dm_ok)  # straight into the owner's dev board as a high-priority card
        if not silent:
            try:
                await thread.delete(reason='Possible exploit report')
            except Exception as e:
                print('delete exploit', e)
        return

    # 2. Troll.
    # a message saved with !bug was written by someone who did not report it: never close it as trolling or strike its author
    if a['troll']['is_troll'] and a['troll']['confidence'] >= CONFIDENT and not silent and not dev_report and not bug.get('saved_by'):
        update_bug(bug['id'], {'status': 'not_a_bug'})
        await set_tags(thread, game=gid, status='not_a_bug')
        try:
            view, files = replies.troll_closed('bug')
            await thread.send(view=view, files=files)
        except Exception:
            pass
        try:
            await thread.edit(archived=True)
        except Exception:
            pass
        if not followup:
            await strike_user(bug['reporter_id'], a['troll'].get('reason') or 'Trolling in bug reports', bug['id'])
        return

    # 3. Duplicate.
    dup = bug_by_id(a['duplicate_of']) if a.get('duplicate_of') in {k['id'] for k in known} else None  # only a report the AI was shown
    if dup and dup['kind'] == 'bug' and not silent and not dev_report:
        update_bug(bug['id'], {'status': 'duplicate', 'dup_of': dup['id']})
        await set_tags(thread, game=gid, device=did, status='duplicate')
        try:
            view, files = replies.duplicate(bug['reporter_id'], dup, 'bug')
            await thread.send(view=view, files=files, allowed_mentions=allowed(users=[bug['reporter_id']]))
        except Exception:
            pass
        try:
            await thread.edit(archived=True)
        except Exception:
            pass
        add_timer('delete_thread', thread.id, now() + DAY)
        return

    # 4. Missing info.
    incomplete = (not a['complete']) or not (game_tag or a.get('game'))
    if incomplete and not silent and not dev_report and bug['asks'] < MAX_ASKS:
        asks = bug['asks'] + 1
        update_bug(bug['id'], {'status': 'needs_info', 'asks': asks})
        await set_tags(thread, game=gid, device=did, status='needs_info')
        missing = a['missing'] if a['missing'] else ['More detail about what happened']
        if not game_tag and not any(re.search(r'game', m, re.I) for m in a['missing']):
            missing.insert(0, 'Which game')
        try:
            view, files = replies.needs_info(bug['reporter_id'], missing, 'bug', a.get('multiple_bugs'), a.get('personal_info'))
            await thread.send(view=view, files=files, allowed_mentions=allowed(users=[bug['reporter_id']]))
        except Exception:
            pass
        cancel_timers('stale', thread.id)
        add_timer('stale', thread.id, now() + 3 * DAY)
        return

    # 5. Complete (or silent import).
    was_asked = bug['status'] == 'needs_info'
    low_info = incomplete and not silent and not dev_report  # asked MAX_ASKS times and still not enough: logged anyway, the dev is told
    cancel_timers('stale', thread.id)
    update_bug(bug['id'], {'status': 'new', 'low_info': 1 if low_info else 0})
    if not silent:
        await set_tags(thread, game=gid, device=did, status=None)
        if not re.match(r'^#\d+\s', thread.name):
            try:
                await thread.edit(name=f"{label(bug_by_id(bug['id']))} {thread.name}"[:100])
            except Exception:
                pass
        try:
            view, files = replies.logged(bug_by_id(bug['id']), low_info, dev_report, was_asked)
            await thread.send(view=view, files=files)
        except Exception:
            pass
    await route_bug(bug_by_id(bug['id']), silent=silent)


_timers = {}


INFO_PING_GAP = 10 * 60 * 1000  # a bug pings its dev about new info at most this often


async def add_info(bug, msg, by=None):
    """Words or files that came after "LOGGED": they are added to the report, the message gets a 📎, and the owner is pinged (at most every 10 minutes)."""
    text = (msg.content or '').strip()
    line = f"[{by or msg.author.display_name}] {text}" + (f" (+{len(msg.attachments)} file(s))" if msg.attachments else '')
    update_bug(bug['id'], {'body': ((bug.get('body') or '') + chr(10) + line)[-3000:]})
    try:
        await msg.add_reaction('📎')
    except Exception:
        pass
    key = f"info:{bug['id']}"
    last = kv_get(key)
    if last and now() - int(last) < INFO_PING_GAP:
        return
    kv_set(key, now())
    from bot.features.bugs.devboard import notify_info
    await notify_info(bug_by_id(bug['id']), msg)


async def attach_clips(msg):
    """The reporter pasted clip links (Medal, Streamable, ...): the videos are downloaded and posted under the message."""
    from bot.features.bugs.linkvideo import fetch_all, video_links
    from bot.features.bugs.transcript import upload_limit
    urls = video_links(msg.content)
    if not urls:
        return
    try:
        await msg.add_reaction('⏳')
    except Exception:
        pass
    got, failed = await fetch_all(urls, upload_limit())
    for g in got:
        try:
            await msg.reply(content=f"🎬 {g['title'][:150]}", file=discord.File(io.BytesIO(g['data']), filename=re.sub(r'[^\w.\-]', '_', g['name'])[:80]),
                            mention_author=False, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            print('clip post', repr(e)[:120])
    try:
        await msg.remove_reaction('⏳', msg.guild.me)
        if failed and not got:
            await msg.add_reaction('⚠️')  # the link could not be downloaded: it stays a link
    except Exception:
        pass


async def log_unanswered(bug):
    """3 days with no answer: the report is not closed (a real bug would be lost). It goes to the developer as it is, marked low info."""
    thread = await fetch_channel(bug['thread_id'])
    update_bug(bug['id'], {'status': 'new', 'low_info': 1})
    cancel_timers('stale', bug['thread_id'])
    if thread:
        await set_tags(thread, status=None)
        if not re.match(r'^#\d+\s', thread.name):
            try:
                await thread.edit(name=f"{label(bug_by_id(bug['id']))} {thread.name}"[:100])
            except Exception:
                pass
        try:
            view, files = replies.logged(bug_by_id(bug['id']), low_info=True)
            await thread.send(view=view, files=files)
        except Exception:
            pass
    await route_bug(bug_by_id(bug['id']))


def handle_bug_message(msg):
    """Debounced handling of messages inside bug posts (a reporter answering, or "still broken" on a fixed bug)."""
    bug = bug_by_thread(msg.channel.id)
    if not bug:
        return
    run('UPDATE bugs SET last_msg_id=? WHERE id=?', str(msg.id), bug['id'])
    if not msg.author.bot and str(msg.author.id) == bug['reporter_id'] and msg.content:
        asyncio.ensure_future(attach_clips(msg))
    if (not msg.author.bot and bug['status'] in ('new', 'investigating', 'fixing') and not bug['deleted'] and bug['routed']
            and (msg.content or msg.attachments) and (not isinstance(msg.author, discord.Member) or level(msg.author) not in ('admin', 'dev', 'jr'))):
        asyncio.ensure_future(add_info(bug, msg))  # something new for a report that is already with the developer
    staff = isinstance(msg.author, discord.Member) and level(msg.author) in ('admin', 'dev', 'jr')
    if msg.author.bot or (str(msg.author.id) != bug['reporter_id'] and (staff or bug['status'] != 'needs_info')):
        return
    loop = asyncio.get_running_loop()
    if bug['status'] == 'needs_info':
        old = _timers.pop(bug['id'], None)
        if old:
            old.cancel()

        async def later():
            _timers.pop(bug['id'], None)
            fresh = bug_by_id(bug['id'])
            if fresh and fresh['status'] == 'needs_info':
                try:
                    await analyze_and_act(fresh, msg.channel, followup=True)
                except Exception as e:
                    print(repr(e))

        _timers[bug['id']] = loop.call_later(15, lambda: asyncio.ensure_future(later()))
    elif bug['status'] == 'fixed' and not bug['deleted'] and msg.content:
        async def check():
            try:
                if await still_broken(msg.content):
                    await reopen(bug_by_id(bug['id']))
            except Exception as e:
                print(repr(e))
        asyncio.ensure_future(check())
