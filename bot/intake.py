"""New posts in the bug forum: Claude checks them, tags them, asks for missing info, spots duplicates, exploits and trolls."""
import asyncio
import re

from .ai import analyze_report, still_broken
from .components import allowed
from .ctx import dm, get_member, sleep, thread_link
from .db import (add_timer, all_, bug_by_id, bug_by_thread, cancel_timers, now, run, update_bug)
from .devboard import post_exploit, route_bug
from .fixes import reopen
from .perms import is_staff
from .strikes import strike_user
from .tags import applied_ids, find_device_tag, find_game_tag, game_tags, set_tags, tag_name, thread_game_tag
from .ui import E, EM

DAY = 86400000
CONFIDENT = 0.85
_IMG = re.compile(r'^image/(png|jpe?g|gif|webp)')


async def fetch_starter(thread):
    for _ in range(4):
        try:
            return await thread.fetch_message(thread.id)
        except Exception:
            await sleep(1500)
    return None


async def gather(thread, bug):
    msgs = [m async for m in thread.history(limit=50)]
    mine = sorted((m for m in msgs if str(m.author.id) == bug['reporter_id']), key=lambda m: m.created_at)
    atts = [a for m in mine for a in m.attachments]
    return {
        'text': '\n---\n'.join(m.content for m in mine if m.content),
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
    report = await gather(thread, bug)
    games = [t['name'] for t in game_tags()]
    picked = [n for n in (tag_name(i) for i in applied_ids(thread)) if n]
    known = all_("""SELECT id,title,summary,status,game_name FROM bugs
        WHERE kind='bug' AND id<>? AND status IN ('new','needs_info','investigating','fixing','fixed') AND deleted IN (0,1)
        ORDER BY id DESC LIMIT 40""", bug['id'])
    try:
        a = await analyze_report(re.sub(r'^#\d+\s+', '', thread.name), report['text'], picked, games,
                                 report['images'], report['videos'], known)
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
    if a['troll']['is_troll'] and a['troll']['confidence'] >= CONFIDENT and not silent:
        update_bug(bug['id'], {'status': 'not_a_bug'})
        await set_tags(thread, game=gid, status='not_a_bug')
        try:
            await thread.send(f"{E['warn']} **CLOSED**{EM}·{EM}Fake or abusive reports lead to strikes.")
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
    dup = bug_by_id(a['duplicate_of']) if a.get('duplicate_of') and a['duplicate_of'] != bug['id'] else None
    if dup and dup['kind'] == 'bug' and not silent:
        update_bug(bug['id'], {'status': 'duplicate', 'dup_of': dup['id']})
        ref = (f"#{dup['id']} \"{dup['title']}\"" if dup['deleted']
               else f"[#{dup['id']} {dup['title']}]({thread_link(dup['thread_id'])})")
        if dup['status'] == 'fixed':
            text = f"<@{bug['reporter_id']}> {E['duplicate']} **DUPLICATE**{EM}·{EM}already fixed on <t:{(dup['fixed_at'] or now()) // 1000}:D>: {ref}."
        else:
            text = f"<@{bug['reporter_id']}> {E['duplicate']} **DUPLICATE**{EM}·{EM}of {ref}. Please add any extra details there. This post is removed in 24 hours."
        await set_tags(thread, game=gid, device=did, status='duplicate')
        try:
            await thread.send(content=text, allowed_mentions=allowed(users=[bug['reporter_id']]))
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
    if incomplete and not silent:
        asks = bug['asks'] + 1
        update_bug(bug['id'], {'status': 'needs_info', 'asks': asks})
        await set_tags(thread, game=gid, device=did, status='needs_info')
        missing = a['missing'] if a['missing'] else ['More detail about what happened']
        if not game_tag and not any(re.search(r'game', m, re.I) for m in a['missing']):
            missing.insert(0, 'Which game')
        bullets = '\n'.join(f'• {m}' for m in missing)
        msg = f"<@{bug['reporter_id']}> ❓ **NEEDS INFO**\n{a['reply'] or 'Thanks for the report! A few details are missing.'}\n\n**STILL NEEDED**\n{bullets}"
        if a['multiple_bugs']:
            msg += '\n\nPlease post each bug separately.'
        if a['personal_info']:
            msg += f"\n\n{E['warn']} Your screenshot may show personal information. Please hide it."
        msg += '\n\nReply in this post and I will check again.'
        try:
            await thread.send(content=msg, allowed_mentions=allowed(users=[bug['reporter_id']]))
        except Exception:
            pass
        cancel_timers('stale', thread.id)
        add_timer('stale', thread.id, now() + 3 * DAY)
        return

    # 5. Complete (or silent import).
    was_asked = bug['status'] == 'needs_info'
    cancel_timers('stale', thread.id)
    update_bug(bug['id'], {'status': 'new'})
    if not silent:
        await set_tags(thread, game=gid, device=did, status=None)
        if not re.match(r'^#\d+\s', thread.name):
            try:
                await thread.edit(name=f"#{bug['id']} {thread.name}"[:100])
            except Exception:
                pass
        msg = f"{E['new']} **LOGGED**{EM}·{EM}#{bug['id']} is sent to the developer. {'Thanks, that covers it.' if was_asked else 'Thanks for the report!'}"
        if a['personal_info']:
            msg += f"\n{E['warn']} Your screenshot may show personal information. Please hide it."
        try:
            await thread.send(msg)
        except Exception:
            pass
    await route_bug(bug_by_id(bug['id']), silent=silent)


_timers = {}


def handle_bug_message(msg):
    """Debounced handling of messages inside bug posts (a reporter answering, or "still broken" on a fixed bug)."""
    bug = bug_by_thread(msg.channel.id)
    if not bug:
        return
    run('UPDATE bugs SET last_msg_id=? WHERE id=?', str(msg.id), bug['id'])
    if msg.author.bot or str(msg.author.id) != bug['reporter_id']:
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
