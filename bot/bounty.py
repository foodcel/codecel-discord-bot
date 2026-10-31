"""Who owns which game, read from the "Claimed games" embed on the bounty-board. Read only."""
import re

from .ctx import ctx
from .db import get_game
from .env import cfg

_claims = []  # [{'name', 'owners': [userId], 'since': 'YYYY-MM-DD' | None, 'votes': int}]


def get_claims():
    return _claims


def parse_claims(embed):
    out = []
    for line in (embed.description or '').split('\n'):
        owners = re.findall(r'<@!?(\d+)>', line)
        if not owners:
            continue
        named = re.match(r'^\[(.+?)\]\(', line) or re.match(r'^\*\*(.+?)\*\*', line)
        if not named:
            continue
        since = re.search(r'since (\d{4}-\d{2}-\d{2})', line)
        votes = re.search(r'(\d+) votes?', line)
        out.append({
            'name': named.group(1), 'owners': list(dict.fromkeys(owners)),
            'since': since.group(1) if since else None,
            'votes': int(votes.group(1)) if votes else 0,
        })
    return out


async def refresh_claims():
    """Returns True when the claim list changed."""
    global _claims
    if not cfg.bounty_id:
        return False  # optional feature, owners can also be set with /config
    try:
        ch = await ctx.client.fetch_channel(int(cfg.bounty_id))
    except Exception:
        return False
    found = []
    try:
        async for m in ch.history(limit=50):
            if not m.author.bot:
                continue
            for e in m.embeds:
                if re.search(r'claimed', e.title or '', re.I):
                    found.extend(parse_claims(e))
    except Exception:
        return False
    if not found:
        return False
    changed = found != _claims
    _claims = found
    return changed


_STOP = {'all', 'the', 'a', 'an', 'of', 'game', 'games', 'please', 'make', 'you', 'should',
         'we', 'need', 'bro', 'i', 'want', 'to', 'and', 'for', 'custom', 'roblox'}


def _stem(t):
    """"x_blocks" must match "X-Block 360": underscores/dashes are separators, plurals are stemmed."""
    return t[:-1] if len(t) > 3 and t.endswith('s') else t


def _toks(s):
    parts = re.split(r'\s+', re.sub(r'[^a-z0-9 ]', ' ', s.lower()))
    return [_stem(t) for t in parts if t and t not in _STOP]


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def match_claims(game_name):
    g = _toks(game_name or '')
    if not g:
        return []
    gn = _norm(game_name)
    best = 0
    hits = []
    for c in _claims:
        ct = set(_toks(c['name']))
        cn = _norm(c['name'])
        # Same letters with different spacing/plurals ("OneShot" / "One shot", "parappa" / "Parappa 2") count as a full match.
        contained = len(gn) >= 4 and len(cn) >= 4 and (gn in cn or cn in gn)
        score = len(g) + 1 if contained else len([t for t in g if t in ct])
        if score / len(g) < 0.5:
            continue
        if score > best:
            best = score
            hits = [c]
        elif score == best and score > 0:
            hits.append(c)
    return hits


def owners_for(tag_id, game_name):
    """Owner override (/config) > confirmed board name > auto match."""
    row = get_game(tag_id) if tag_id else None
    if row and row.get('owner_override'):
        return [o for o in row['owner_override'].split(',') if o]
    hits = []
    if row and row.get('board_name'):
        hits = [c for c in _claims if _norm(c['name']) == _norm(row['board_name'])]
    if not hits:
        hits = match_claims(game_name)
    return list(dict.fromkeys(o for c in hits for o in c['owners']))


def board_name_for(tag_id, game_name):
    row = get_game(tag_id) if tag_id else None
    if row and row.get('board_name'):
        return row['board_name']
    return ', '.join(c['name'] for c in match_claims(game_name)) or None
