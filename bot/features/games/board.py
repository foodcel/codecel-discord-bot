"""The bounty board: a suggestions forum ranked by votes in a dev channel, and who has claimed which game.
Three pinned messages (Top suggestions, Claimed games, Completed games) kept up to date by the bot. Once an admin runs
/bounty-board, this is the source of truth for who owns a game; before that the bot only reads another bot's board."""
import asyncio
import json
import re

import discord
from discord import app_commands

from bot.discord_ui.card import card
from bot.discord_ui.components import NO_MENTIONS
from bot.core.ctx import ctx, fetch_channel
from bot.core.db import all_, hide_reports, kv_get, kv_set, one, run
from bot.core.perms import level
from bot.discord_ui.ui import E, EN, SEP, cut

TOP_LIMIT = 25  # posts listed in the top suggestions message
DESCRIPTION_LIMIT = 3800  # embed descriptions cap at 4096
DEFAULT_VOTE_EMOJI = '🔥'  # when the forum has no default reaction set
HIGHLY_REQUESTED_VOTES = 30  # a post reaching this gets the tag (never removed by the bot)
HIGHLY_REQUESTED_TAG = 'Highly Requested'
IN_DEVELOPMENT_TAG = 'In Development'  # added on /claim, removed on /claim drop
FORUM_SYNC_SECONDS = 3600
BOARD_REFRESH_DELAY = 5  # seconds; a burst of votes becomes one edit of the pinned messages
CUSTOM = 'custom:'  # autocomplete value of a game with no forum post, followed by its name
CLAIM = 'claim:'  # autocomplete value of an existing claim, followed by its id
MAX_CUSTOM_GAME = 60
FOOT_TOP = '\n'.join([
    '/claim new · take a game from the list, or your own (add its Steam page with link:)',
    '/claim edit · change the link to the original game',
    '/claim drop · drop a game you claimed, it comes back here',
    'Admins: /assign gives a game to a dev · /exclude hides a post · /include brings it back',
])

_lock = asyncio.Lock()
_refresh_task = None


# ---- settings (kept in the key-value table) ----
def board_cfg():
    raw = kv_get('board')
    return json.loads(raw) if raw else None


def save_cfg(d):
    kv_set('board', json.dumps(d))


def is_live():
    return board_cfg() is not None


# ---- data ----
def posts():
    return all_('SELECT * FROM board_posts')


def post_by_id(id_):
    return one('SELECT * FROM board_posts WHERE post_id=?', str(id_))


def claims():
    return all_('SELECT * FROM board_claims ORDER BY created_at, id')


def claim_by_id(id_):
    return one('SELECT * FROM board_claims WHERE id=?', id_)


def claim_for_post(post_id):
    return one('SELECT * FROM board_claims WHERE post_id=?', str(post_id))


def claim_for_game(name):
    return one('SELECT * FROM board_claims WHERE post_id IS NULL AND game=? COLLATE NOCASE', name)


def custom_name(text):
    return ' '.join(str(text).split())[:MAX_CUSTOM_GAME]


def claim_title(c, by_id=None):
    """The game's name: the post's title, or the custom game's name."""
    if c['post_id']:
        p = (by_id or {}).get(c['post_id']) or post_by_id(c['post_id'])
        return p['title'] if p else None
    return c['game']


def live_claims():
    """Open claims in the shape the rest of the bot reads: {'name', 'owners', 'since', 'votes'}."""
    by_id = {p['post_id']: p for p in posts()}
    out = []
    for c in claims():
        if c['completed_at']:
            continue
        name = claim_title(c, by_id)
        if name is None:
            continue
        p = by_id.get(c['post_id'])
        out.append({'name': name, 'owners': [c['user_id']], 'since': (c['created_at'] or '')[:10] or None,
                    'votes': p['votes'] if p else 0})
    return out


# ---- text ----
def escape_markdown(s):
    return discord.utils.escape_markdown(s)


def post_link(p):
    title = p['title'].replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
    return f"[{title}](https://discord.com/channels/{ctx.guild.id}/{p['post_id']})"


def votes_label(n):
    return f"{n} vote{'' if n == 1 else 's'}"


def fit(lines):
    """Join lines, cutting off with "...and N more" before the embed limit."""
    shown, size = [], 0
    for line in lines:
        if size + len(line) > DESCRIPTION_LIMIT:
            shown.append(f'...and {len(lines) - len(shown)} more')
            break
        shown.append(line)
        size += len(line) + 1
    return '\n'.join(shown)


def top_embed():
    """The best-voted suggestions nobody has claimed yet, as a card: (view, files)."""
    ps, cs = posts(), claims()
    taken = {c['post_id'] for c in cs if c['post_id']}
    ranked = sorted((p for p in ps if p['post_id'] not in taken and not p['excluded']), key=lambda p: (-p['votes'], p['title'].lower()))
    lines = []
    for n, p in enumerate(ranked[:TOP_LIMIT], 1):
        title = cut(p['title'], 38).replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
        lines.append(f"**{n}**{EN}[{title}](https://discord.com/channels/{ctx.guild.id}/{p['post_id']}){SEP}🔥 {p['votes']}")
    title = f"🏆 Top suggestions · {E['open']} {len(ranked)} open" if ranked else '🏆 Top suggestions'
    return card(title, [fit(lines) if lines else 'No open suggestions.'], FOOT_TOP.split(chr(10)))


async def build_embeds():
    """The three pinned messages as cards [(view, files)]: top suggestions, the games being worked on, and the released games."""
    from bot.features.games.games import game_embeds
    released, unreleased = await game_embeds()
    return [top_embed(), unreleased, released]


def set_completed(name, done):
    """Releasing a game completes its claim; moving it back reopens the claim. Matches on the game's name."""
    want = re.sub(r'[^a-z0-9]', '', name.lower())
    by_id = {p['post_id']: p for p in posts()}
    for c in claims():
        t = claim_title(c, by_id)
        if t and re.sub(r'[^a-z0-9]', '', t.lower()) == want and bool(c['completed_at']) != done:
            run('UPDATE board_claims SET completed_at=' + ('CURRENT_TIMESTAMP' if done else 'NULL') + ' WHERE id=?', c['id'])
            return True
    return False


def released_from_claims():
    """Completed claims (taken over from an older board) show as released games, unless the game is already listed."""
    from bot.features.games.games import key
    by_id = {p['post_id']: p for p in posts()}
    for c in claims():
        t = claim_title(c, by_id) if c['completed_at'] else None
        if t and not one('SELECT 1 FROM game_status WHERE key=?', key(t)):
            stamp = int(__import__('datetime').datetime.fromisoformat(c['completed_at']).replace(
                tzinfo=__import__('datetime').timezone.utc).timestamp() * 1000)
            run("INSERT INTO game_status(key,name,owners,since,status,released_at,released_by) VALUES(?,?,?,?,'released',?,?)",
                key(t), t, c['user_id'], (c['created_at'] or '')[:10] or None, stamp, c['user_id'])


# ---- the forum: posts, votes and tags ----
def forum_channel():
    c = board_cfg()
    ch = ctx.client.get_channel(int(c['forum_id'])) if c else None
    return ch if isinstance(ch, discord.ForumChannel) else None


def vote_count(reactions, emoji):
    """The count of the vote emoji among a message's reactions: matched by id for a custom emoji, else by character."""
    eid = emoji.id if emoji else None
    name = emoji.name if emoji else DEFAULT_VOTE_EMOJI
    for r in reactions:
        rid = getattr(r.emoji, 'id', None)
        if (rid == eid) if eid else (rid is None and str(r.emoji) == name):
            return r.count
    return 0


async def post_votes(forum, post_id):
    try:
        msg = await ctx.client.get_partial_messageable(int(post_id)).fetch_message(int(post_id))
    except discord.NotFound:  # the starter message was deleted
        return 0
    return vote_count(msg.reactions, forum.default_reaction_emoji)


def find_tag(tags, name):
    return next((t for t in tags if t.name.casefold() == name.casefold()), None)


async def set_post_tag(post_id, name, on):
    """Add or remove one of the forum's tags on a post. False if it couldn't: no such tag, 5 tags already, or an API error."""
    forum = forum_channel()
    tag = forum and find_tag(forum.available_tags, name)
    if tag is None:
        return False
    try:
        thread = ctx.client.get_channel(int(post_id)) or await ctx.client.fetch_channel(int(post_id))
        tags = [t for t in thread.applied_tags if t.id != tag.id] + ([tag] if on else [])
        if {t.id for t in tags} == {t.id for t in thread.applied_tags}:
            return True
        if len(tags) > 5:  # Discord's limit per post
            return False
        # An archived post can only be edited while unarchiving it in the same request.
        await thread.edit(applied_tags=tags, **({'archived': False} if thread.archived else {}))
    except discord.HTTPException as e:
        print('board tag', post_id, name, e)
        return False
    return True


async def tag_if_highly_requested(post_id, before, votes):
    """Tag a post when it reaches the threshold. Only on crossing it, so a mod can take the tag off again."""
    if votes >= HIGHLY_REQUESTED_VOTES and (before is None or before < HIGHLY_REQUESTED_VOTES):
        await set_post_tag(post_id, HIGHLY_REQUESTED_TAG, True)


def forget_posts(ids):
    """Delete posts and their claims. A completed claim is kept as a completed custom game under the post's title."""
    for pid in ids:
        row = one('SELECT p.title, c.user_id, c.created_at, c.completed_at FROM board_claims c JOIN board_posts p ON p.post_id=c.post_id'
                  ' WHERE c.post_id=? AND c.completed_at IS NOT NULL', pid)
        if row:
            taken = one('SELECT 1 FROM board_claims WHERE post_id IS NULL AND game=? COLLATE NOCASE', row['title'])
            run('INSERT INTO board_claims(game,user_id,created_at,completed_at) VALUES(?,?,?,?)',
                f"{row['title']} (post {pid})" if taken else row['title'], row['user_id'], row['created_at'], row['completed_at'])
        run('DELETE FROM board_claims WHERE post_id=?', pid)
        run('DELETE FROM board_posts WHERE post_id=?', pid)


async def sync_forum():
    """Read every post (active and archived) and its votes, then refresh the board. Returns the number of posts."""
    forum = forum_channel()
    if forum is None:
        print('Bounty board forum is gone')
        return 0
    threads = {t.id: t for t in await ctx.guild.active_threads() if t.parent_id == forum.id}
    async for t in forum.archived_threads(limit=None):
        threads[t.id] = t
    previous = {p['post_id']: p['votes'] for p in posts()}
    keep = set()
    for t in threads.values():
        if t.flags.pinned:  # rules and guides, not suggestions
            continue
        votes = await post_votes(forum, t.id)
        pid = str(t.id)
        keep.add(pid)
        run('INSERT INTO board_posts(post_id,title,votes) VALUES(?,?,?) ON CONFLICT(post_id) DO UPDATE SET title=excluded.title, votes=excluded.votes',
            pid, t.name, votes)
        await tag_if_highly_requested(pid, previous.get(pid), votes)
    if keep:  # an empty read is more likely a failure than a forum with no posts: never delete claims over it
        forget_posts([pid for pid in previous if pid not in keep])
    await refresh_board()
    await reload_claims()
    return len(keep)


# ---- the three pinned messages ----
async def refresh_board():
    """Bring the pinned messages up to date, posting any that was deleted or never posted. Logs failures rather than raising."""
    async with _lock:
        c = board_cfg()
        ch = c and await fetch_channel(c['channel_id'])
        if ch is None:
            return
        from bot.features.games import bounty
        if bounty.set_claims(live_claims()):  # the embeds read the claims; a change must reach the dev boards too
            from bot.features.bugs.devboard import schedule_boards
            schedule_boards()
        old = [c.get('top'), c.get('claims'), c.get('completed')]
        ids = []
        for n, (mid, built) in enumerate(zip(old, await build_embeds())):
            view, files = built
            try:
                if mid:
                    try:
                        await ch.get_partial_message(int(mid)).edit(content=None, embeds=[], view=view, attachments=files,
                                                                     allowed_mentions=discord.AllowedMentions.none())
                    except discord.NotFound:
                        mid = None
                        view, files = (await build_embeds())[n]  # the files can be sent once
                if not mid:
                    msg = await ch.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
                    mid = str(msg.id)
                    await msg.pin()
            except discord.HTTPException as e:
                print('Couldn\'t update the bounty board', e)
            ids.append(str(mid) if mid else None)
        if ids != old:
            save_cfg({**c, 'top': ids[0], 'claims': ids[1], 'completed': ids[2]})


def schedule_refresh():
    """Refresh the board in a few seconds, once for a whole burst of changes."""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        return

    async def go():
        global _refresh_task
        await asyncio.sleep(BOARD_REFRESH_DELAY)
        _refresh_task = None  # before rendering, so a change from here on schedules another refresh
        await refresh_board()
        await reload_claims()

    _refresh_task = asyncio.ensure_future(go())


async def reload_claims():
    """Hand the open claims to the part of the bot that routes bugs and builds the games board."""
    from bot.features.games import bounty
    from bot.features.bugs.devboard import schedule_boards
    if bounty.set_claims(live_claims()):
        schedule_boards()


async def sync_loop():
    """Re-read the forum hourly, to catch anything missed while the bot was offline. Runs for the bot's lifetime."""
    while True:
        await asyncio.sleep(FORUM_SYNC_SECONDS)
        if not is_live():
            continue
        try:
            await sync_forum()
        except Exception as e:
            print('bounty board sync failed', repr(e))


# ---- events ----
async def on_vote_change(channel_id, message_id):
    """A reaction changed. If it's on a board post's starter message, recount that post's votes."""
    if not is_live() or str(message_id) != str(channel_id):  # a forum post's starter message shares the thread's id
        return
    post = post_by_id(channel_id)
    forum = forum_channel()
    if post is None or forum is None:
        return
    votes = await post_votes(forum, post['post_id'])
    run('UPDATE board_posts SET votes=? WHERE post_id=?', votes, post['post_id'])
    await tag_if_highly_requested(post['post_id'], post['votes'], votes)
    schedule_refresh()


def on_thread_create(thread):
    c = board_cfg()
    if c and str(thread.parent_id) == str(c['forum_id']) and not thread.flags.pinned:
        run('INSERT OR IGNORE INTO board_posts(post_id,title,votes) VALUES(?,?,0)', str(thread.id), thread.name)
        schedule_refresh()
        return True
    return False


def on_thread_delete(thread_id):
    if is_live() and post_by_id(thread_id):
        forget_posts([str(thread_id)])
        schedule_refresh()


# ---- choosing a game ----
def is_dev(member):
    c = board_cfg()
    return level(member) == 'admin' or any(str(r.id) == str(c['role_id']) for r in member.roles)


def is_admin(member):
    return level(member) == 'admin'


def post_choices(ps, current):
    """Up to 25 posts whose title contains `current`, most votes first."""
    cur = current.casefold()
    found = sorted((p for p in ps if cur in p['title'].casefold()), key=lambda p: -p['votes'])
    return [app_commands.Choice(name=f"{p['title'][:85]} ({votes_label(p['votes'])})", value=p['post_id']) for p in found[:25]]


def game_choices(current, open_claims):
    """Unclaimed posts (and, for /assign, openly claimed ones) matching what's typed, plus a "Custom game" option."""
    taken = {c['post_id'] for c in claims() if c['post_id'] and (c['completed_at'] or not open_claims)}
    out = post_choices([p for p in posts() if p['post_id'] not in taken and not p['excluded']], current)[:24]
    name = custom_name(current)
    if name and not any(c.name.casefold().startswith(name.casefold() + ' (') for c in out):
        out.append(app_commands.Choice(name=f'Custom game: {name}'[:100], value=(CUSTOM + name)[:100]))
    return out[:25]


def claim_choices(user, current, completed):
    """Open (or completed) claims matching what's typed: the user's own, or everyone's for admins."""
    by_id = {p['post_id']: p for p in posts()}
    cur = current.casefold()
    out = []
    for c in claims():
        if bool(c['completed_at']) != completed or not (is_admin(user) or c['user_id'] == str(user.id)):
            continue
        t = claim_title(c, by_id)
        if t and cur in t.casefold():
            out.append(app_commands.Choice(name=t[:100], value=f"{CLAIM}{c['id']}"))
    return out[:25]


def chosen_game(value):
    """(post or None, custom name or None). A custom name that matches a post's title means the post."""
    custom = value.startswith(CUSTOM) and custom_name(value[len(CUSTOM):])
    text = custom or value
    if str(text).isdigit():
        p = post_by_id(text)
    else:
        m = [p for p in posts() if p['title'].casefold() == str(text).strip().casefold()]
        p = m[0] if len(m) == 1 else None
    return p, (None if p else (custom or None))


def chosen_claim(value):
    """The claim picked from autocomplete (or typed out by its game's name), with its post for a forum claim."""
    if value.startswith(CLAIM) and value[len(CLAIM):].isdigit():
        c = claim_by_id(int(value[len(CLAIM):]))
    else:
        p, name = chosen_game(value)
        c = claim_for_post(p['post_id']) if p else (claim_for_game(custom_name(value)) if value else None)
    return (post_by_id(c['post_id']) if c and c['post_id'] else None), c


def game_name(p, c):
    return post_link(p) if p else f"**{escape_markdown(c['game'])}** (custom game)"


# ---- the commands ----
async def _say(i, text, **kw):
    await i.response.send_message(text, **kw)


async def ensure_board(i):
    if not is_live():
        await _say(i, "There's no bounty board here yet. An admin can set one up with `/bounty-board`.", ephemeral=True)
        return False
    return True


async def ensure_admin(i):
    if not is_admin(i.user):
        await _say(i, 'Only admins can use this.', ephemeral=True)
        return False
    return True


async def unavailable(i, post, custom, claim):
    """Tells the user, and returns True, when a game can't be claimed or assigned: not picked, excluded, or completed."""
    if post is None and custom is None:
        msg = 'Pick a post from the list as you type, or the "Custom game" option for a game with no post.'
    elif post is not None and post['excluded']:
        msg = 'That game was removed from the board with `/exclude`.'
    elif claim and claim['completed_at']:
        msg = f"<@{claim['user_id']}> already completed that game. Use `/release undo` to reopen it."
    else:
        return False
    await _say(i, msg, ephemeral=True)
    return True


def current_claim(post, custom):
    return claim_for_post(post['post_id']) if post else claim_for_game(custom)


def add_claim(post, custom, user_id):
    try:
        if post:
            run('INSERT INTO board_claims(post_id,user_id) VALUES(?,?)', post['post_id'], str(user_id))
        else:
            run('INSERT INTO board_claims(game,user_id) VALUES(?,?)', custom, str(user_id))
    except Exception:
        return False
    return True


async def command_claim(i, opts):
    """/claim new post [link]: link is the page of the original game (Steam etc.), shown on the games board."""
    from bot.features.games.games import http, set_source_link
    if not await ensure_board(i):
        return
    if not is_dev(i.user):
        return await _say(i, f"Only <@&{board_cfg()['role_id']}> can claim games.", ephemeral=True, allowed_mentions=NO_MENTIONS)
    link = (opts.get('link') or '').strip()
    if link and not http(link):
        return await _say(i, 'The link must start with http:// or https://', ephemeral=True)
    post, custom = chosen_game(opts.get('post') or '')
    holder = current_claim(post, custom) if (post or custom) else None
    if await unavailable(i, post, custom, holder):
        return
    if holder:
        return await _say(i, f"That's already claimed by <@{holder['user_id']}>.", ephemeral=True, allowed_mentions=NO_MENTIONS)
    if not add_claim(post, custom, i.user.id):
        return await _say(i, 'Someone claimed that game just now.', ephemeral=True)
    c = current_claim(post, custom)
    await _say(i, f'{i.user.mention} claimed {game_name(post, c)}.', allowed_mentions=NO_MENTIONS)
    if post and not await set_post_tag(post['post_id'], IN_DEVELOPMENT_TAG, True):
        await i.followup.send(f'⚠️ Couldn\'t add the **{IN_DEVELOPMENT_TAG}** tag to the post.', ephemeral=True)
    if link:
        title = claim_title(c)
        set_source_link(title, [str(i.user.id)], (c['created_at'] or '')[:10], link)
    await refresh_board()
    await reload_claims()


async def held_claim(i, post, completed):
    """The open (or completed) claim picked, if the user holds it or is an admin; otherwise tells them why not."""
    p, c = chosen_claim(post or '')
    if c is None or bool(c['completed_at']) != completed:
        if completed:
            msg = "That game isn't completed."
        elif c is None:
            msg = "That game isn't claimed. Pick one from the list as you type."
        else:
            msg = 'That game is completed. Use `/release undo` to reopen it.'
        await _say(i, msg, ephemeral=True)
        return None
    if c['user_id'] != str(i.user.id) and not is_admin(i.user):
        await _say(i, f"Only <@{c['user_id']}> or an admin can do that.", ephemeral=True, allowed_mentions=NO_MENTIONS)
        return None
    return p, c


async def release(i, p, c, verb):
    """Drop a claim, putting the game back on Top suggestions and taking In Development off its post."""
    run('DELETE FROM board_claims WHERE id=?', c['id'])
    if hide_reports(claim_title(c), 'bug'):  # an unclaimed game keeps no bugs
        from bot.features.bugs.devboard import schedule_boards
        schedule_boards()
    await _say(i, f'{verb} {game_name(p, c)}.', allowed_mentions=NO_MENTIONS)
    if p and not await set_post_tag(p['post_id'], IN_DEVELOPMENT_TAG, False):
        await i.followup.send(f'⚠️ Couldn\'t remove the **{IN_DEVELOPMENT_TAG}** tag from the post.', ephemeral=True)
    await refresh_board()
    await reload_claims()


async def command_claim_edit(i, opts):
    """/claim edit post link: change the link to the original game (Steam page etc.) of a game you claimed."""
    from bot.features.games.games import http, refresh_game_board, set_source_link
    if not await ensure_board(i):
        return
    link = (opts.get('link') or '').strip()
    if not http(link):
        return await _say(i, 'The link must start with http:// or https://', ephemeral=True)
    held = await held_claim(i, opts.get('post'), False)
    if not held:
        return
    p, c = held
    set_source_link(claim_title(c), [c['user_id']], (c['created_at'] or '')[:10], link)
    await _say(i, f'{game_name(p, c)} now links to {link}', ephemeral=True)
    await refresh_game_board()


async def command_unclaim(i, opts):
    if await ensure_board(i):
        held = await held_claim(i, opts.get('post'), False)
        if held:
            await release(i, *held, verb='Dropped')


async def command_assign(i, opts):
    """Give a game to a dev, taking it from whoever holds it (admins only)."""
    if not await ensure_admin(i) or not await ensure_board(i):
        return
    dev_id = str(opts.get('dev'))
    post, custom = chosen_game(opts.get('post') or '')
    holder = current_claim(post, custom) if (post or custom) else None
    if await unavailable(i, post, custom, holder):
        return
    if holder and holder['user_id'] == dev_id:
        return await _say(i, f'<@{dev_id}> already holds that game.', ephemeral=True, allowed_mentions=NO_MENTIONS)
    if holder:
        run('UPDATE board_claims SET user_id=?, created_at=CURRENT_TIMESTAMP WHERE id=? AND completed_at IS NULL', dev_id, holder['id'])
    elif not add_claim(post, custom, dev_id):
        return await _say(i, "That game's claim changed just now. Try again.", ephemeral=True)
    c = current_claim(post, custom)
    taken = f", taking it from <@{holder['user_id']}>" if holder else ''
    await _say(i, f'{i.user.mention} assigned {game_name(post, c)} to <@{dev_id}>{taken}.',
               allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=int(dev_id))], everyone=False, roles=False))  # the dev should hear about it
    member = ctx.guild.get_member(int(dev_id))
    if member and not is_dev(member):
        await i.followup.send(f"⚠️ <@{dev_id}> doesn't have <@&{board_cfg()['role_id']}>.", ephemeral=True, allowed_mentions=NO_MENTIONS)
    if post and not await set_post_tag(post['post_id'], IN_DEVELOPMENT_TAG, True):
        await i.followup.send(f'⚠️ Couldn\'t add the **{IN_DEVELOPMENT_TAG}** tag to the post.', ephemeral=True)
    await refresh_board()
    await reload_claims()


async def _set_excluded(i, opts, excluded):
    if not await ensure_admin(i) or not await ensure_board(i):
        return
    p, _ = chosen_game(opts.get('post') or '')
    if p is None or bool(p['excluded']) == excluded:
        return await _say(i, 'Pick a post from the list as you type.' if p is None else
                          f"That post is already {'removed from' if excluded else 'on'} the board.", ephemeral=True)
    run('UPDATE board_posts SET excluded=? WHERE post_id=?', 1 if excluded else 0, p['post_id'])
    await _say(i, f"{'Removed from the bounty board' if excluded else 'Back on the bounty board'}: {post_link(p)}.", ephemeral=True)
    await refresh_board()


async def command_exclude(i, opts):
    await _set_excluded(i, opts, True)


async def command_include(i, opts):
    await _set_excluded(i, opts, False)


async def autocomplete(i, name, current):
    """Answers the autocomplete of a board command."""
    if name == 'claim':
        out = game_choices(current, False)
    elif name == 'assign':
        out = game_choices(current, True)
    elif name == 'unclaim':
        out = claim_choices(i.user, current, False)
    elif name == 'exclude':
        out = post_choices([p for p in posts() if not p['excluded']], current)
    else:  # include
        out = post_choices([p for p in posts() if p['excluded']], current)
    await i.response.autocomplete(out)


# ---- setting it up ----
def import_old_board(messages):
    """First setup only: take over the claims another bot's board lists (Claimed and Completed embeds), with their dates."""
    n = 0
    for m in messages:
        for e in m.embeds:
            title = (e.title or '').lower()
            done = 'complet' in title
            if not done and 'claimed' not in title:
                continue
            for line in (e.description or '').split('\n'):
                user = re.search(r'<@!?(\d+)>', line)
                date = re.search(r'(?:since|on) (\d{4}-\d{2}-\d{2})', line)
                if not user or not date:
                    continue
                stamp = f'{date.group(1)} 00:00:00'
                link = re.match(r'^\[.+?\]\(https://discord\.com/channels/\d+/(\d+)\)', line)
                named = re.match(r'^\*\*(.+?)\*\*', line)
                try:
                    if link:
                        run('INSERT OR IGNORE INTO board_claims(post_id,user_id,created_at,completed_at) VALUES(?,?,?,?)',
                            link.group(1), user.group(1), stamp, stamp if done else None)
                    elif named:
                        name = custom_name(re.sub(r'\\(.)', r'\1', named.group(1)))
                        run('INSERT OR IGNORE INTO board_claims(game,user_id,created_at,completed_at) VALUES(?,?,?,?)',
                            name, user.group(1), stamp, stamp if done else None)
                    else:
                        continue
                    n += 1
                except Exception as e2:
                    print('import', e2)
    return n


async def command_setup(i, opts):
    """/bounty-board channel forum role (admins only): posts and pins the three messages and takes over the claims."""
    if not await ensure_admin(i):
        return
    channel = await fetch_channel(opts.get('channel'))
    forum = await fetch_channel(opts.get('forum'))
    role = opts.get('role')
    if not isinstance(forum, discord.ForumChannel) or channel is None:
        return await _say(i, 'Pick a text channel and a forum channel.', ephemeral=True)
    me = ctx.guild.me
    problems = []
    p = channel.permissions_for(me)
    if not (p.view_channel and p.send_messages and p.embed_links and p.manage_messages):
        problems.append(f'In {channel.mention} I need Send Messages, Embed Links and Manage Messages (to pin).')
    p = forum.permissions_for(me)
    if not (p.view_channel and p.read_message_history and p.manage_threads):
        problems.append(f'In {forum.mention} I need Read Message History and Manage Threads (to set tags).')
    if problems:
        return await _say(i, '⚠️ ' + '\n'.join(problems), ephemeral=True)
    await i.response.defer(ephemeral=True, thinking=True)  # reading every post takes a while
    old = board_cfg()
    imported = 0
    if old is None:  # the first time: keep what the previous board says
        try:
            msgs = [m async for m in channel.history(limit=50) if m.author.bot and m.author.id != ctx.client.user.id]
        except Exception:
            msgs = []
        imported = import_old_board(msgs)
    new = {'forum_id': str(forum.id), 'channel_id': str(channel.id), 'role_id': str(role), 'top': None, 'claims': None, 'completed': None}
    save_cfg(new)
    if old:  # retire the previous board's messages
        for mid in (old.get('top'), old.get('claims'), old.get('completed')):
            if mid:
                try:
                    och = await fetch_channel(old['channel_id'])
                    await och.get_partial_message(int(mid)).delete()
                except Exception:
                    pass
    lines = [f'Bounty board posted and pinned in {channel.mention}, ranking {forum.mention}. <@&{role}> can claim games.']
    released_from_claims()
    if imported:
        lines.append(f'Took over {imported} claim(s) from the old board.')
    try:
        lines.append(f'Synced {await sync_forum()} posts.')
    except Exception as e:
        print('first board sync', repr(e))
        lines.append("⚠️ Reading the forum failed; I'll retry within the hour.")
    missing = [n for n in (IN_DEVELOPMENT_TAG, HIGHLY_REQUESTED_TAG) if find_tag(forum.available_tags, n) is None]
    if missing:
        lines.append(f"⚠️ {forum.mention} has no {' or '.join(f'**{n}**' for n in missing)} tag, so I won't set it.")
    from bot.discord_ui.commands_sync import register_commands
    await register_commands()
    await i.edit_original_response(content='\n'.join(lines), allowed_mentions=NO_MENTIONS)
