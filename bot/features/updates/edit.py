"""Editing an update that was already posted: the same card, new lines. Used by /update edit and by the MCP."""
import json

from bot.core.ctx import fetch_channel
from bot.core.db import all_, get_game, one, run
from bot.discord_ui.components import NO_MENTIONS
from bot.features.games.cards import released_row_for, update_card
from bot.features.updates.announce import mark


def recent(tag_ids, limit=25):
    """The latest posted updates of these games, newest first."""
    ids = [str(t) for t in tag_ids]
    if not ids:
        return []
    return all_(f"SELECT * FROM announcements WHERE tag_id IN ({','.join('?' * len(ids))}) AND message_id IS NOT NULL AND payload IS NOT NULL ORDER BY id DESC LIMIT ?", *ids, limit)


def lines(row):
    """(bug fixes, changes, what's new, version) of a posted update."""
    old = json.loads(row['payload'])
    changes = old['changes'] if 'changes' in old else old.get('updates', [])
    return old.get('bugfixes', []), changes, old.get('new', []), old.get('version') or ''


async def edit_posted(row, fixes=None, changes=None, new=None, version=None):
    """Rewrites a posted update. None keeps a part as it is. Returns (ok, message or link). Never pings again."""
    old = json.loads(row['payload'])
    f0, c0, n0, v0 = lines(row)
    f, c, n = (f0 if fixes is None else fixes), (c0 if changes is None else changes), (n0 if new is None else new)
    v = v0 if version is None else version
    if not (f or c or n):
        return False, 'An update cannot be empty.'
    ch = await fetch_channel(row['channel_id'])
    try:
        msg = await ch.fetch_message(int(row['message_id'])) if ch else None
    except Exception:
        msg = None
    if not msg:
        return False, 'The posted message is gone, so it cannot be edited.'
    game = get_game(row['tag_id']) or {'name': row['game_name'], 'tag_id': row['tag_id']}
    fresh = old.get('fresh') or []
    view, files = update_card(game, released_row_for(game['name']), mark(f, fresh), mark(c, fresh), mark(n, fresh), v, f"<@&{old['ping_role']}>" if old.get('ping_role') else None, poster=old.get('poster'))
    await msg.edit(content=None, embeds=[], view=view, attachments=files, allowed_mentions=NO_MENTIONS)
    run('UPDATE announcements SET payload=? WHERE id=?', json.dumps({**old, 'bugfixes': f, 'changes': c, 'new': n, 'updates': c + n, 'version': v}), row['id'])
    return True, msg.jump_url


def by_id(id_):
    return one('SELECT * FROM announcements WHERE id=?', int(id_))
