"""The forum tags of the bug channel and of the suggestions channel: device and status tags (a fixed few).
Games are NOT tags any more (a forum holds 20 tags at most): a game is a row of the `games` table, or a released game of the library. Its id is
what the forum tag id used to be for the games that had a tag, and `g-<key>` for every other game. Posts carry the game in their title."""
import difflib
import re

import discord

from bot.core.ctx import ctx
from bot.core.db import all_, upsert_game
from bot.core.env import cfg

STATUS_TAG = {
    'needs_info': 'Needs Info', 'investigating': 'Investigating', 'fixing': 'Fix in Progress',
    'fixed': 'Fixed', 'duplicate': 'Duplicate', 'not_a_bug': 'Not a Bug',
}
SUGGEST_STATUS_TAG = {'fixed': 'Added', 'declined': 'Declined'}  # the suggestions forum keeps just these two
STATUS_EMOJI = {'Fixed': '✅', 'Added': '✅', 'Declined': '❌'}
OLD_SUGGEST_TAGS = {'needs info', 'duplicate'}  # taken out of the suggestions forum
DEVICES = ['Mobile', 'Computer', 'Controller']
KEEP = object()  # status=KEEP means "leave the status tags alone", status=None means "clear them"

_tags = []   # the bug forum: [{'id': str, 'name': str, 'moderated': bool}]
_stags = []  # the suggestions forum


def _read(forum):
    return [{'id': str(t.id), 'name': t.name, 'moderated': t.moderated} for t in forum.available_tags]


async def load_tags():
    global _tags, _stags
    _tags = _read(await ctx.client.fetch_channel(int(cfg.bugs_id)))
    if cfg.suggestions_id:
        _stags = _read(await ctx.client.fetch_channel(int(cfg.suggestions_id)))
    _remember_game_tags()


def _remember_game_tags():
    """The game tags the bug forum still has are saved as games, so deleting them from the forum later loses nothing."""
    for t in _tags:
        if t['moderated'] or t['name'] in DEVICES or t['name'].lower() in {n.lower() for n in STATUS_TAG.values()}:
            continue
        upsert_game(t['id'], t['name'], {'name': t['name']})


def _status_tag(name, emoji, id_=0):
    """A moderated tag with its emoji; with the id of an existing tag it replaces that tag in place (posts keep it)."""
    t = discord.ForumTag(name=name, emoji=discord.PartialEmoji(name=emoji), moderated=True)
    t.id = id_
    return t


def _has_emoji(tag, emoji):
    return bool(tag.emoji) and tag.emoji.name == emoji


async def ensure_suggest_tags():
    """The suggestions forum has two status tags: Added ✅ and Declined ❌. Needs Info and Duplicate are taken out; missing ones are made and get their emoji."""
    if not cfg.suggestions_id:
        return
    forum = await ctx.client.fetch_channel(int(cfg.suggestions_id))
    tags, changed = [], False
    for t in forum.available_tags:
        if t.name.lower() in OLD_SUGGEST_TAGS:
            changed = True
            continue
        want = STATUS_EMOJI.get(t.name) if t.name in SUGGEST_STATUS_TAG.values() else None
        if want and not _has_emoji(t, want):
            t = _status_tag(t.name, want, t.id)
            changed = True
        tags.append(t)
    have = {t.name for t in tags}
    for name in SUGGEST_STATUS_TAG.values():
        if name not in have:
            tags.append(_status_tag(name, STATUS_EMOJI[name]))
            changed = True
    if changed:  # one edit with the whole list: creating tags one by one overwrites each other
        try:
            await forum.edit(available_tags=tags, reason='Status tags for suggestions')
        except Exception as e:
            print('suggestion tags', repr(e))
    await load_tags()


async def ensure_open_posting():
    """Posts carry no game tag, so the forums must not require one (Discord refuses a post without a tag when it does)."""
    for fid in (cfg.bugs_id, cfg.suggestions_id):
        if not fid:
            continue
        try:
            forum = await ctx.client.fetch_channel(int(fid))
            if forum.flags.require_tag:
                await forum.edit(require_tag=False, reason='Games are in the post title, not tags')
        except Exception as e:
            print('require_tag', repr(e))


async def ensure_fixed_tag():
    """The bugs forum has one status tag: Fixed ✅. It is made when missing and gets its emoji."""
    forum = await ctx.client.fetch_channel(int(cfg.bugs_id))
    tags, changed, seen = [], False, False
    for t in forum.available_tags:
        if t.name.lower() == 'fixed':
            seen = True
            if not _has_emoji(t, '✅') or not t.moderated:
                t = _status_tag(t.name, '✅', t.id)
                changed = True
        tags.append(t)
    if not seen and len(tags) < 20:
        tags.append(_status_tag('Fixed', '✅'))
        changed = True
    if changed:
        try:
            await forum.edit(available_tags=tags, reason='Fixed tag')
        except Exception as e:
            print('fixed tag', repr(e))
    await load_tags()


def _has_game(name, names):
    """True when a game already stands for this name: the same name, or a longer or shorter form of it ("Peggle Deluxe" for "Peggle")."""
    k = _norm(name)
    for n in names:
        o = _norm(n)
        if o == k or (len(o) >= 4 and len(k) >= 4 and (k.startswith(o) or o.startswith(k))):
            return True
    return False


def _by_name(n, pool=None):
    n = str(n).lower()
    return next((t for t in (_tags if pool is None else pool) if t['name'].lower() == n), None)


def game_tags():
    """Every game a report can be about: [{'id', 'name'}]. The games that were tags (kept in the games table), then the released games of the library
    that none of them stands for (id `g-<key>`)."""
    from bot.features.games.games import clean_name
    out = [{'id': r['tag_id'], 'name': r['name'], 'moderated': False} for r in all_('SELECT tag_id, name FROM games') if r['name']]
    names = [t['name'] for t in out]
    for r in all_("SELECT key, name, title, roblox_name FROM game_status WHERE status='released'"):
        shown = clean_name(r['name'])
        if any(_has_game(a, names) for a in (shown, r['name'], r['title'], r['roblox_name']) if a):
            continue
        out.append({'id': 'g-' + r['key'], 'name': shown, 'moderated': False})
        names.append(shown)
    return sorted(out, key=lambda t: t['name'].lower())


def game_by_id(id_):
    return next((t for t in game_tags() if t['id'] == str(id_)), None) if id_ else None


def tag_name(id_):
    """A game's name, or the name of a status or device tag."""
    g = game_by_id(id_)
    if g:
        return g['name']
    t = next((t for t in _tags + _stags if t['id'] == str(id_)), None)  # ids are unique across forums
    return t['name'] if t else None


def device_tags():
    return [t for t in _tags if t['name'] in DEVICES]


def suggest_game_tags():
    """The game tags old suggestion posts still carry (new posts get none)."""
    return [t for t in _stags if not t['moderated'] and t['name'] not in SUGGEST_STATUS_TAG.values()]


def find_game_tag(name):
    """The game tag for a name: exact, then written a little differently, then a longer or shorter form of one tag
    ("Peggle Deluxe" for the tag "Peggle") as long as only one tag fits."""
    n = str(name or '').lower()
    tags = game_tags()
    hit = next((t for t in tags if t['name'].lower() == n), None)
    if hit:
        return hit
    k = _norm(name)
    if not k:
        return None
    hit = next((t for t in tags if _norm(t['name']) == k), None)
    if hit:
        return hit
    near = [t for t in tags if len(_norm(t['name'])) >= 4 and (k.startswith(_norm(t['name'])) or (len(k) >= 4 and _norm(t['name']).startswith(k)))]
    if len(near) == 1:
        return near[0]
    # the name the game has on Roblox ("Thunderball Deluxe") or the title a dev set, for a released game that has a tag
    from bot.core.db import all_
    hits = []
    for r in all_("SELECT name, roblox_name, title FROM game_status WHERE status='released'"):
        for alias in {_norm(r.get('roblox_name')), _norm(r.get('title'))} - {''}:
            if len(alias) >= 4 and (k.startswith(alias) or (len(k) >= 4 and alias.startswith(k))):
                hits.append(_norm(r['name']))
                break
    hits = set(hits)
    return next((t for t in tags if _norm(t['name']) in hits), None) if len(hits) == 1 else None


def find_device_tag(name):
    n = str(name or '').lower()
    return next((t for t in device_tags() if t['name'].lower() == n), None)


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower().replace('&', 'and'))


def canonical_game(name):
    """The bug forum's game tag for a name written a little differently ("Simpsons Hit and Run", "SUEPRHOT")."""
    n = _norm(name)
    if not n:
        return None
    pool = {_norm(t['name']): t for t in game_tags()}
    if n in pool:
        return pool[n]
    m = difflib.get_close_matches(n, list(pool), 1, 0.7)
    return pool[m[0]] if m else None


def applied_ids(thread):
    """Tag ids on a forum post. Threads in a normal text channel have none."""
    return [str(t.id) for t in thread.applied_tags]


def is_forum_post(thread):
    return thread.parent is not None and thread.parent.type in (discord.ChannelType.forum, discord.ChannelType.media)


def in_suggestions(thread):
    return bool(cfg.suggestions_id) and str(thread.parent_id) == str(cfg.suggestions_id)


def thread_game_tag(thread):
    """The game the poster picked, as the bug forum's tag."""
    ids = applied_ids(thread)
    if in_suggestions(thread):
        for t in suggest_game_tags():
            if t['id'] in ids:
                return canonical_game(t['name'])
        return None
    return next((t for t in game_tags() if t['id'] in ids), None)


async def set_tags(thread, game=None, device=None, status=KEEP, replace_game=False, kind='bug'):
    """status: a key of STATUS_TAG (SUGGEST_STATUS_TAG in the suggestions forum), None to clear the status tags, or KEEP.
    device: a tag id of the bug forum to make sure is on. game and replace_game are kept so callers read the same, but games are not tags any more:
    the game is in the post's title (see retitle)."""
    if not is_forum_post(thread):
        return  # tester threads live in a text channel and have no tags
    suggest = in_suggestions(thread)
    if not suggest and str(thread.parent_id) != str(cfg.bugs_id):
        return
    if suggest:
        device = None
        status_map, pool = SUGGEST_STATUS_TAG, _stags
        if kind != 'suggestion' or (status is not KEEP and status is not None and status not in SUGGEST_STATUS_TAG):
            status = KEEP  # a bug that was posted here, or a status this forum has no tag for
    else:
        status_map, pool = STATUS_TAG, _tags
    current = applied_ids(thread)
    status_ids = {t['id'] for t in (_by_name(n, pool) for n in status_map.values()) if t}
    nxt = list(current) if status is KEEP else [i for i in current if i not in status_ids]
    if device and device not in nxt:
        nxt.append(device)
    st = None
    if status and status is not KEEP:
        t = _by_name(status_map[status], pool)
        st = t['id'] if t else None
    nxt = nxt[:4 if st else 5]
    if st:
        nxt.append(st)
    if nxt == current:
        return
    if thread.archived:
        try:
            await thread.edit(archived=False)
        except Exception:
            pass
    try:
        forum = thread.parent
        await thread.edit(applied_tags=[forum.get_tag(int(i)) for i in nxt if forum.get_tag(int(i))])
    except Exception as e:
        print('setAppliedTags', e)


def titled(game, title):
    """The post title with the game in front: "Minecraft · Wither AI broken"."""
    title = str(title or '')
    return title if not game or title.lower().startswith(f'{game} · '.lower()) else f'{game} · {title}'


async def retitle(thread, old, new):
    """The report moved to another game: the game in the post's title follows ("#3 Peggle · title" becomes "#3 Minecraft · title")."""
    m = re.match(r'^(#\d+\s+)?(.*)$', thread.name, re.S)
    rest = m.group(2)
    if old and rest.lower().startswith(f'{old} · '.lower()):
        rest = rest[len(old) + 3:]
    name = ((m.group(1) or '') + titled(new, rest))[:100]
    if name != thread.name:
        try:
            await thread.edit(name=name)
        except Exception as e:
            print('retitle', repr(e))
