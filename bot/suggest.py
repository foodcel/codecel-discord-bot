"""The suggestions forum: Claude checks each post, tags it, asks for missing info, spots duplicates and sends it to the dev who owns
the game. A post that is really a bug becomes a normal bug. Statuses, dev boards and announcements are shared with the bug side
(a suggestion is a row in the same table with kind='suggestion'; "fixed" means Added)."""
import asyncio
import re

from .nums import label
from .ai import analyze_suggestion
from .board import vote_count
from .components import allowed
from .ctx import fetch_channel, get_member, thread_link
from .db import add_timer, all_, bug_by_id, bug_by_thread, cancel_timers, now, run, update_bug
from .devboard import route_bug, schedule_boards
from .env import cfg
from .intake import CONFIDENT, DAY, MAX_ASKS, fetch_starter, gather
from .perms import is_staff, level
from .strikes import strike_user
from .tags import canonical_game, find_game_tag, game_tags, set_tags, tag_name, thread_game_tag, applied_ids
from .ui import E, EM

_timers = {}


async def count_votes(thread):
    """The forum's vote emoji (default reaction) on the first message of the post."""
    try:
        starter = await thread.fetch_message(thread.id)
        emoji = thread.parent.default_reaction_emoji if thread.parent else None
        return vote_count(starter.reactions, emoji)
    except Exception:
        return 0


async def intake_suggestion(thread, silent=False):
    if bug_by_thread(thread.id) or thread.flags.pinned:
        return
    starter = await fetch_starter(thread)
    if not starter or starter.author.bot:
        return
    cur = run("INSERT INTO bugs(thread_id,reporter_id,title,status,created_at,last_msg_id,kind,votes) VALUES(?,?,?,?,?,?,'suggestion',?)",
              str(thread.id), str(starter.author.id), thread.name, 'new', now(), str(thread.last_message_id or starter.id),
              await count_votes(thread))
    await analyze_and_act(bug_by_id(cur.lastrowid), thread, silent=silent)


async def analyze_and_act(bug, thread, silent=False, followup=False):
    from .ai import allow_user
    if not silent and not allow_user(bug['reporter_id']):
        print('ai: hourly limit for', bug['reporter_id'], '- report', bug['id'], 'waits')
        return  # stays as it is; the catch-up checks it again
    report = await gather(thread, bug)
    games = [t['name'] for t in game_tags()]
    picked = []
    for i in applied_ids(thread):
        n = tag_name(i)
        c = canonical_game(n) if n else None
        if c:
            picked.append(c['name'])
    known = all_("""SELECT id,title,summary,status,game_name FROM bugs
        WHERE kind='suggestion' AND id<>? AND status IN ('new','needs_info','fixed','declined') AND deleted IN (0,1)
        ORDER BY id DESC LIMIT 40""", bug['id'])
    try:
        a = await analyze_suggestion(re.sub(r'^#\d+\s+', '', thread.name), report['text'], picked, games, report['images'], known, bug['asks'])
    except Exception as e:
        print('analyze suggestion failed:', e)
        return  # stays status=new, routed=0; catch-up retries later

    game_tag = thread_game_tag(thread) or find_game_tag(a.get('game')) or canonical_game(a.get('game'))
    update_bug(bug['id'], {
        'game_tag_id': game_tag['id'] if game_tag else None,
        'game_name': game_tag['name'] if game_tag else (a.get('game') or None),
        'title': a.get('title') or bug['title'], 'summary': a['summary'], 'severity': a['severity'],
    })
    bug = bug_by_id(bug['id'])
    gid = game_tag['id'] if game_tag else None
    staff_reporter = is_staff(await get_member(bug['reporter_id']))
    ping = allowed(users=[bug['reporter_id']])

    # 1. It is a bug: it becomes a normal bug on the owner's bug board.
    if a['type'] == 'bug' and not staff_reporter:
        update_bug(bug['id'], {'kind': 'bug', 'source': 'suggestions', 'status': 'new'})
        if not silent:
            await set_tags(thread, game=gid, kind='bug')
            try:
                await thread.send(
                    content=f"<@{bug['reporter_id']}> 🐛 **THIS IS A BUG**{EM}·{EM}That is something broken, not a suggestion. I logged it as bug {label(bug)} "
                            f"and sent it to the developer. Next time please post bugs in <#{cfg.bugs_id}>.",
                    allowed_mentions=ping)
            except Exception:
                pass
        from .intake import analyze_and_act as bug_check
        await bug_check(bug_by_id(bug['id']), thread, silent=silent)  # exploit hiding, duplicates and missing info, like any bug
        return

    # 2. Troll.
    reporter = await get_member(bug['reporter_id'])
    dev_post = reporter is not None and level(reporter) in ('admin', 'dev', 'jr')
    if a['troll']['is_troll'] and a['troll']['confidence'] >= CONFIDENT and not silent and not dev_post and not bug.get('saved_by'):
        update_bug(bug['id'], {'status': 'declined'})
        await set_tags(thread, game=gid, status='declined', kind='suggestion')
        try:
            await thread.send(f"{E['warn']} **CLOSED**{EM}·{EM}Fake or abusive posts lead to strikes.")
        except Exception:
            pass
        try:
            await thread.edit(archived=True)
        except Exception:
            pass
        if not followup:
            await strike_user(bug['reporter_id'], a['troll'].get('reason') or 'Trolling in suggestions', bug['id'])
        return

    # 3. Duplicate.
    dup = bug_by_id(a['duplicate_of']) if a.get('duplicate_of') in {k['id'] for k in known} else None  # only a post the AI was shown
    if dup and dup['kind'] == 'suggestion' and not silent:
        update_bug(bug['id'], {'status': 'duplicate', 'dup_of': dup['id']})
        ref = (f"{label(dup)} \"{dup['title']}\"" if dup['deleted']
               else f"[{label(dup)} {dup['title']}]({thread_link(dup['thread_id'])})")
        if dup['status'] == 'fixed':
            text = f"<@{bug['reporter_id']}> {E['duplicate']} **DUPLICATE**{EM}·{EM}already added on <t:{(dup['fixed_at'] or now()) // 1000}:D>: {ref}."
        else:
            text = (f"<@{bug['reporter_id']}> {E['duplicate']} **DUPLICATE**{EM}·{EM}someone already suggested this: {ref}. "
                    "Add your vote there. This post is removed in 24 hours.")
        await set_tags(thread, game=gid, status='duplicate', kind='suggestion')
        try:
            await thread.send(content=text, allowed_mentions=ping)
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
    if incomplete and not silent and bug['asks'] < MAX_ASKS:
        update_bug(bug['id'], {'status': 'needs_info', 'asks': bug['asks'] + 1})
        await set_tags(thread, game=gid, status='needs_info', kind='suggestion')
        missing = a['missing'] if a['missing'] else ['A bit more detail about what you would like']
        if not game_tag and not any(re.search(r'game', m, re.I) for m in a['missing']):
            missing.insert(0, 'Which game')
        bullets = '\n'.join(f'• {m}' for m in missing)
        msg = (f"<@{bug['reporter_id']}> ❓ **NEEDS INFO**\n{a['reply'] or 'Thanks for the idea! A few details are missing.'}\n\n"
               f"**STILL NEEDED**\n{bullets}\n\nReply in this post and I will check again.")
        try:
            await thread.send(content=msg, allowed_mentions=ping)
        except Exception:
            pass
        cancel_timers('stale', thread.id)
        add_timer('stale', thread.id, now() + 3 * DAY)
        return

    # 5. Complete (or silent import).
    was_asked = bug['status'] == 'needs_info'
    low_info = incomplete and not silent
    cancel_timers('stale', thread.id)
    update_bug(bug['id'], {'status': 'new', 'low_info': 1 if low_info else 0})
    if not silent:
        await set_tags(thread, game=gid, status=None, kind='suggestion')
        if not re.match(r'^#\d+\s', thread.name):
            try:
                await thread.edit(name=f"{label(bug_by_id(bug['id']))} {thread.name}"[:100])
            except Exception:
                pass
        try:
            if low_info:
                await thread.send(f"{E['new']} **LOGGED**{EM}·{EM}{label(bug_by_id(bug['id']))} Thanks! Some details are still missing, so a developer "
                                  'will come and look at it themselves, or ask you here.')
            else:
                await thread.send(f"{E['new']} **LOGGED**{EM}·{EM}{label(bug_by_id(bug['id']))} is sent to the developer. "
                                  f"{'Thanks, that covers it.' if was_asked else 'Thanks for the idea!'} Votes help it get noticed.")
        except Exception:
            pass
    await route_bug(bug_by_id(bug['id']), silent=silent)


def handle_suggestion_message(msg):
    """Debounced handling of messages inside suggestion posts (a player answering what was missing)."""
    bug = bug_by_thread(msg.channel.id)
    if not bug or bug['kind'] != 'suggestion':
        return
    run('UPDATE bugs SET last_msg_id=? WHERE id=?', str(msg.id), bug['id'])
    if msg.author.bot or str(msg.author.id) != bug['reporter_id'] or bug['status'] != 'needs_info':
        return
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

    _timers[bug['id']] = asyncio.get_running_loop().call_later(15, lambda: asyncio.ensure_future(later()))


async def on_vote_change(channel_id, message_id):
    """A reaction changed on the first message of a suggestion post: keep the vote count the boards show."""
    if str(message_id) != str(channel_id):
        return
    bug = bug_by_thread(channel_id)
    if not bug or bug['kind'] != 'suggestion' or bug['deleted']:
        return
    thread = await fetch_channel(channel_id)
    if thread is None:
        return
    votes = await count_votes(thread)
    if votes != bug['votes']:
        update_bug(bug['id'], {'votes': votes})
        schedule_boards()
