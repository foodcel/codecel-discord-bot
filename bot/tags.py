"""The forum tags of the bug channel: game, device and status tags."""
import discord

from .ctx import ctx
from .env import cfg

STATUS_TAG = {
    'needs_info': 'Needs Info', 'investigating': 'Investigating', 'fixing': 'Fix in Progress',
    'fixed': 'Fixed', 'duplicate': 'Duplicate', 'not_a_bug': 'Not a Bug',
}
DEVICES = ['Mobile', 'Computer', 'Controller']
KEEP = object()  # status=KEEP means "leave the status tags alone", status=None means "clear them"

_tags = []  # [{'id': str, 'name': str, 'moderated': bool}]


async def load_tags():
    global _tags
    forum = await ctx.client.fetch_channel(int(cfg.bugs_id))
    _tags = [{'id': str(t.id), 'name': t.name, 'moderated': t.moderated} for t in forum.available_tags]


def _by_name(n):
    n = str(n).lower()
    return next((t for t in _tags if t['name'].lower() == n), None)


def tag_name(id_):
    t = next((t for t in _tags if t['id'] == str(id_)), None)
    return t['name'] if t else None


def game_tags():
    return [t for t in _tags if not t['moderated'] and t['name'] not in DEVICES]


def device_tags():
    return [t for t in _tags if t['name'] in DEVICES]


def status_tag_ids():
    return [t['id'] for t in (_by_name(n) for n in STATUS_TAG.values()) if t]


def find_game_tag(name):
    n = str(name or '').lower()
    return next((t for t in game_tags() if t['name'].lower() == n), None)


def find_device_tag(name):
    n = str(name or '').lower()
    return next((t for t in device_tags() if t['name'].lower() == n), None)


def applied_ids(thread):
    """Tag ids on a forum post. Threads in a normal text channel have none."""
    return [str(t.id) for t in thread.applied_tags]


def is_forum_post(thread):
    return thread.parent is not None and thread.parent.type in (discord.ChannelType.forum, discord.ChannelType.media)


def thread_game_tag(thread):
    ids = applied_ids(thread)
    return next((t for t in game_tags() if t['id'] in ids), None)


async def set_tags(thread, game=None, device=None, status=KEEP, replace_game=False):
    """status: a key of STATUS_TAG, None to clear the status tags, or KEEP. game/device: tag ids to make sure are on.
    replace_game swaps out other game tags for `game`."""
    if not is_forum_post(thread):
        return  # tester threads live in a text channel and have no tags
    current = applied_ids(thread)
    status_ids = set(status_tag_ids())
    nxt = list(current) if status is KEEP else [i for i in current if i not in status_ids]
    if game and replace_game:
        games = {t['id'] for t in game_tags()}
        nxt = [i for i in nxt if i not in games]
    if game and game not in nxt:
        nxt.append(game)
    if device and device not in nxt:
        nxt.append(device)
    st = None
    if status and status is not KEEP:
        t = _by_name(STATUS_TAG[status])
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
