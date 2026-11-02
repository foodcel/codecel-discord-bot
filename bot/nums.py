"""Bug and suggestion numbers. Every game counts its own: Sonic Dimensions #3 and Peggle #3 are different reports. The database id stays the real key
(buttons, links, transcripts); the number is only what people read and type. It is the place of the report among those of the same game and kind,
oldest first, so it never changes and nothing has to be stored."""
import re

from .db import all_, one


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower())


def _table():
    """({id: (number, scope)}, {(scope, number): id}). A scope is (kind, game)."""
    by_id, by_num, count = {}, {}, {}
    for r in all_('SELECT id, kind, game_name FROM bugs ORDER BY id'):
        scope = (r['kind'] or 'bug', _norm(r['game_name']))
        count[scope] = count.get(scope, 0) + 1
        by_id[r['id']] = (count[scope], scope)
        by_num[(scope, count[scope])] = r['id']
    return by_id, by_num


def _id(b):
    return b['id'] if isinstance(b, dict) else int(b)


def num(b):
    """The number of a report (a bug row or an id) within its game."""
    return _table()[0].get(_id(b), (_id(b), None))[0]


def label(b):
    """#3"""
    return f'#{num(b)}'


def full(b):
    """Sonic Dimensions #3"""
    bug = b if isinstance(b, dict) else one('SELECT * FROM bugs WHERE id=?', int(b))
    return f"{(bug or {}).get('game_name') or 'Unknown game'} {label(b)}" if bug else f'#{b}'


def scope_of(b):
    return _table()[0].get(_id(b), (None, None))[1]


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
