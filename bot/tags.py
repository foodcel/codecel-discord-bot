"""The forum tags of the bug channel and of the suggestions channel: game, device and status tags.
A game is known by its tag in the bug forum (its "canonical" tag). The suggestions forum has its own tags with slightly different
spellings, so they are matched by name."""
import difflib
import re

import discord

from .ctx import ctx
from .env import cfg

STATUS_TAG = {
    'needs_info': 'Needs Info', 'investigating': 'Investigating', 'fixing': 'Fix in Progress',
    'fixed': 'Fixed', 'duplicate': 'Duplicate', 'not_a_bug': 'Not a Bug',
}
SUGGEST_STATUS_TAG = {'needs_info': 'Needs Info', 'fixed': 'Added', 'declined': 'Declined', 'duplicate': 'Duplicate'}
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


async def ensure_suggest_tags():
    """Makes the status tags of the suggestions forum (Added, Declined, Duplicate, Needs Info) if they are missing."""
    if not cfg.suggestions_id:
        return
    forum = await ctx.client.fetch_channel(int(cfg.suggestions_id))
    have = {t.name.lower() for t in forum.available_tags}
    missing = [discord.ForumTag(name=n, moderated=True) for n in SUGGEST_STATUS_TAG.values() if n.lower() not in have]
    if missing:  # one edit with the whole list: creating them one by one overwrites each other
        try:
            await forum.edit(available_tags=[*forum.available_tags, *missing], reason='Status tags for suggestions')
        except Exception as e:
            print('create tags', e)
    await load_tags()


def _by_name(n, pool=None):
    n = str(n).lower()
    return next((t for t in (_tags if pool is None else pool) if t['name'].lower() == n), None)


def tag_name(id_):
    t = next((t for t in _tags + _stags if t['id'] == str(id_)), None)  # ids are unique across forums
    return t['name'] if t else None


def game_tags():
    return [t for t in _tags if not t['moderated'] and t['name'] not in DEVICES]


def device_tags():
    return [t for t in _tags if t['name'] in DEVICES]


def suggest_game_tags():
    return [t for t in _stags if not t['moderated'] and t['name'] not in SUGGEST_STATUS_TAG.values()]


def status_tag_ids():
    return [t['id'] for t in (_by_name(n) for n in STATUS_TAG.values()) if t]


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
    return near[0] if len(near) == 1 else None


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


def to_suggest_tag_id(game_tag_id):
    """The suggestions forum's tag for a game, given the bug forum's tag id."""
    name = tag_name(game_tag_id)
    for t in suggest_game_tags():
        c = canonical_game(t['name'])
        if c and c['name'] == name:
            return t['id']
    return None


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
    game/device: tag ids of the bug forum to make sure are on (translated for the suggestions forum).
    replace_game swaps out other game tags for `game`."""
    if not is_forum_post(thread):
        return  # tester threads live in a text channel and have no tags
    suggest = in_suggestions(thread)
    if not suggest and str(thread.parent_id) != str(cfg.bugs_id):
        return
    if suggest:
        game = to_suggest_tag_id(game) if game else None
        device = None
        status_map, pool, game_pool = SUGGEST_STATUS_TAG, _stags, suggest_game_tags()
        if kind != 'suggestion' or (status is not KEEP and status is not None and status not in SUGGEST_STATUS_TAG):
            status = KEEP  # a bug that was posted here, or a status this forum has no tag for
    else:
        status_map, pool, game_pool = STATUS_TAG, _tags, game_tags()
    current = applied_ids(thread)
    status_ids = {t['id'] for t in (_by_name(n, pool) for n in status_map.values()) if t}
    nxt = list(current) if status is KEEP else [i for i in current if i not in status_ids]
    if game and replace_game:
        games = {t['id'] for t in game_pool}
        nxt = [i for i in nxt if i not in games]
    if game and game not in nxt:
        nxt.append(game)
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
