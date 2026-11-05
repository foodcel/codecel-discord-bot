"""Bug and suggestion numbers. Every game counts its own: Sonic Dimensions #3 and Peggle #3 are different reports. The database id stays the real key
(buttons, links, transcripts); the number is only what people read and type. A report gets its number the first time it is counted, and the number is
STORED (bugs.num, bugs.num_scope), so it never shifts: not when an older report changes game, not when a suggestion becomes a bug. Only the report that
moved gets a new number at the end of its new game. The first run stores the numbers people already see (same order, same values)."""
import re
import time

from bot.core.db import all_, one, run


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower())


_cache = (0.0, None)


def _table():
    """({id: (number, scope)}, {(scope, number): id}). A scope is (kind, game). Missing or moved numbers are given (and stored) here."""
    global _cache
    if _cache[1] is not None and time.time() - _cache[0] < 2:
        return _cache[1]
    rows = all_('SELECT id, kind, game_name, num, num_scope FROM bugs ORDER BY id')
    top = {}
    for r in rows:
        if r['num'] is not None and r['num_scope']:
            top[r['num_scope']] = max(top.get(r['num_scope'], 0), r['num'])
    by_id, by_num = {}, {}
    for r in rows:
        scope = (r['kind'] or 'bug', _norm(r['game_name']))
        key = f'{scope[0]}|{scope[1]}'
        if r['num'] is None or r['num_scope'] != key:  # new, or it moved to another game or kind: the next number there
            top[key] = top.get(key, 0) + 1
            r['num'], r['num_scope'] = top[key], key
            run('UPDATE bugs SET num=?, num_scope=? WHERE id=?', r['num'], key, r['id'])
        by_id[r['id']] = (r['num'], scope)
        by_num[(scope, r['num'])] = r['id']
    _cache = (time.time(), (by_id, by_num))
    return by_id, by_num


def forget():
    """A report was added or changed game: the next lookup reads the table again."""
    global _cache
    _cache = (0.0, None)


def _id(b):
    return b['id'] if isinstance(b, dict) else int(b)


def _entry(b):
    t = _table()[0]
    if _id(b) not in t:  # added a moment ago: read again
        forget()
        t = _table()[0]
    return t.get(_id(b), (_id(b), None))


def num(b):
    """The number of a report (a bug row or an id) within its game."""
    return _entry(b)[0]


def label(b):
    """#3"""
    return f'#{num(b)}'


def full(b):
    """Sonic Dimensions #3"""
    bug = b if isinstance(b, dict) else one('SELECT * FROM bugs WHERE id=?', int(b))
    return f"{(bug or {}).get('game_name') or 'Unknown game'} {label(b)}" if bug else f'#{b}'


def scope_of(b):
    return _entry(b)[1]


def game_scope(text, kind):
    """The scope of the game a dev typed ("sonic" for Sonic Dimensions), or None when no single game of that kind fits."""
    k = _norm(text)
    if not k:
        return None
    names = {_norm(r['game_name']): r['game_name'] for r in all_('SELECT DISTINCT game_name FROM bugs WHERE kind=?', kind) if r['game_name']}
    if k in names:
        return (kind, k)
    near = [n for n in names if len(k) >= 3 and (k in n or (len(n) >= 4 and n in k))]
    return (kind, near[0]) if len(near) == 1 else None


def resolve(cmd, kind, here=None, candidates=None):
    """Turns what a dev typed ({'ids': numbers, 'game': words or None}) into real ids.
    here: the report the dev typed under, whose game is the default. candidates: the reports the dev may mean when typing in a board with several games.
    Returns {'ids': [...], 'skipped': [texts], 'unknown_game': bool, 'ambiguous': [numbers]}."""
    out = {'ids': [], 'skipped': [], 'unknown_game': False, 'ambiguous': []}
    table_by_id, by_num = _table()
    scope = None
    if cmd.get('game'):
        scope = game_scope(cmd['game'], kind)
        if scope is None:
            out['unknown_game'] = True
            return out
    elif here:
        scope = scope_of(here)
    for n in cmd['ids']:
        if scope is not None:
            id_ = by_num.get((scope, n))
        else:  # a board with several games: the number must belong to one game among the open reports
            scopes = {table_by_id[b['id']][1] for b in (candidates or []) if table_by_id.get(b['id'], (0,))[0] == n}
            if len(scopes) > 1:
                out['ambiguous'].append(n)
                continue
            id_ = by_num.get((next(iter(scopes)), n)) if scopes else None
        if id_ is None:
            out['skipped'].append(f'#{n} not found')
        else:
            out['ids'].append(id_)
    return out
