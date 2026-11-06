"""What an agent may CHANGE: report statuses (two calls: preview, then confirm) and updates (post, edit). Everything goes through the same code as the
buttons and commands, so the dev log, the reporters' notices and the boards behave the same. Only the dev's own games; limits keep a looping agent calm."""
import secrets
import time
from collections import defaultdict, deque

from bot.core.db import create_pending, get_game, one, upsert_game
from bot.features.bugs import statuses as st
from bot.features.updates import announce, edit
from bot.mcp import reports

MODES = ('manual', 'every', 'critical', 'count')
SET_STATUS = (st.NEW, st.INVESTIGATING, st.FIXING, st.FIXED, st.NOT_A_BUG, st.DUPLICATE, st.DECLINED)
BIG = ('high', 'critical')  # only a fix of this severity may ping
STATUS_PER_HOUR, POSTS_GAP_MIN = 40, 20
_confirms = {}  # user id -> {'code', 'ids', 'status', 'until'}
_changes = defaultdict(deque)


def _too_many(uid):
    q, t = _changes[str(uid)], time.monotonic()
    while q and t - q[0] > 3600:
        q.popleft()
    if len(q) >= STATUS_PER_HOUR:
        return True
    q.append(t)
    return False


def _fix_list(x):
    return [str(line).strip()[:200] for line in (x or []) if str(line).strip()][:40]


async def set_status(member, allowed, ids, status, confirm=''):
    """First call (no confirm): shows what would change and gives a one-time code. Second call with the code: does it."""
    status = (status or '').strip().lower().replace(' ', '_')
    if status not in SET_STATUS:
        return f"Status must be one of: {', '.join(SET_STATUS)}."
    ids = sorted({int(i) for i in ids})[:30]
    if not ids:
        return 'Give at least one report id.'
    rows = []
    for i in ids:
        b, why = reports.owned(allowed, i)
        if not b:
            return f'id {i}: {why}'
        rows.append(b)
    uid = str(member.id)
    pend = _confirms.get(uid)
    if not confirm:
        code = secrets.token_hex(3)
        _confirms[uid] = {'code': code, 'ids': ids, 'status': status, 'until': time.time() + 600}
        lines = [f"- id {b['id']} ({b['game_name']}) {b['status']} -> {status}: {b['title'] or '(no title)'}" for b in rows]
        return 'Nothing changed yet. This would change:\n' + '\n'.join(lines) + f'\nTo do it, call set_status again with the same ids and status and confirm="{code}" (valid 10 minutes).'
    if not pend or pend['code'] != confirm or pend['ids'] != ids or pend['status'] != status or pend['until'] < time.time():
        return 'That confirm code does not match. Call set_status without confirm first.'
    if _too_many(uid):
        return f'Limit reached: at most {STATUS_PER_HOUR} status changes an hour. Wait a bit.'
    del _confirms[uid]
    from bot.features.bugs.fixes import apply_status
    done, skipped = await apply_status(ids, status, member, via='MCP')
    return ('Changed: ' + ', '.join(done) if done else 'Nothing changed.') + (('\nSkipped: ' + ', '.join(skipped)) if skipped else '')


def policy(tag_id):
    g = get_game(tag_id) or {}
    return (g.get('mcp_mode') if g.get('mcp_mode') in MODES else 'manual'), int(g.get('mcp_count') or 5)


def set_policy(allowed, game, mode, count=None):
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    mode = (mode or '').lower()
    if mode not in MODES:
        return (f"Mode must be one of: {', '.join(MODES)}. manual = only post when your dev tells you; every = after each fixed report; "
                'critical = when a high or critical fix is waiting; count = after `count` fixes.')
    patch = {'mcp_mode': mode}
    if count:
        patch['mcp_count'] = max(1, min(int(count), 50))
    upsert_game(hit[0], hit[1], patch)
    m, n = policy(hit[0])
    return f'{hit[1]}: update policy is now {m}' + (f' ({n} fixes)' if m == 'count' else '') + '.'


def due_text(allowed, game):
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    tag_id, name = hit
    mode, n = policy(tag_id)
    w = announce.unannounced(tag_id)
    big = [b for b in w if b['kind'] == 'bug' and b.get('severity') in BIG]
    due = bool(w) and (mode == 'every' or (mode == 'critical' and big) or (mode == 'count' and len(w) >= n))
    last = one('SELECT * FROM announcements WHERE tag_id=? ORDER BY id DESC LIMIT 1', str(tag_id))
    out = [f"{name}: policy {mode}" + (f' ({n} fixes)' if mode == 'count' else '') + f", {len(w)} fix(es) waiting, update due: {'YES' if due else 'no'}."]
    if mode == 'manual':
        out.append('Policy is manual: do not post unless your dev told you to.')
    for b in w:
        out.append(f"- id {b['id']} [{b['kind']}, severity {b.get('severity') or '?'}] {b['title'] or '(no title)'}")
    if last:
        out.append(f"Last update: id {last['id']}, {announce._ago(last['posted_at'])}." + (' It can still be merged into (under 12 hours old).' if announce.recent_announcement(str(tag_id)) else ''))
    return '\n'.join(out)


async def post_update(member, allowed, game, fixes=None, changes=None, whats_new=None, bug_ids=None, version='', ping='none', merge=True):
    """Posts an update through the normal pipeline. bug_ids are the fixed reports it announces (their reporters are told, as always)."""
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    tag_id, name = hit
    fixes, changes, new = _fix_list(fixes), _fix_list(changes), _fix_list(whats_new)
    bugs, sugs = [], []
    for i in bug_ids or []:
        b, why = reports.owned(allowed, i)
        if not b or str(b['game_tag_id']) != str(tag_id):
            return f'id {i}: {why or "that report is not in this game"}'
        if b['status'] != st.FIXED or b['announced']:
            return f"id {i} is not a fixed report that is still waiting for an update (status {b['status']}, announced {bool(b['announced'])})."
        (bugs if b['kind'] == 'bug' else sugs).append(b)
    if bugs and not fixes:
        fixes = [b['title'] or 'A bug fix' for b in bugs]
    if sugs and not new:
        new = [b['title'] or 'A new feature' for b in sugs]
    if not (fixes or changes or new):
        return 'Nothing to post: give fixes, changes or whats_new.'
    ping = (ping or 'none').lower()
    if ping not in ('none', 'role'):
        return 'ping must be none or role.'
    if ping == 'role' and not any(b.get('severity') in BIG for b in bugs):
        return 'Pings are only for big fixes: include at least one high or critical report in bug_ids, or use ping="none".'
    recent = announce.recent_announcement(str(tag_id))
    last = one('SELECT posted_at FROM announcements WHERE tag_id=? ORDER BY id DESC LIMIT 1', str(tag_id))
    use_merge = bool(merge and recent and ping == 'none')
    if not use_merge and last and time.time() * 1000 - last['posted_at'] < POSTS_GAP_MIN * 60000:
        return f'The last update of {name} was under {POSTS_GAP_MIN} minutes ago. Wait, or merge into it (merge=true, ping="none").'
    pid = create_pending({'tagId': str(tag_id), 'bugIds': [b['id'] for b in bugs], 'bugfixes': fixes, 'newIds': [b['id'] for b in sugs],
                          'newLines': new, 'updates': changes, 'version': (version or '').strip(), 'owners': [str(member.id)], 'off': []})
    res = await (announce.merge_announcement(pid) if use_merge else announce.post_announcement(pid, ping=(ping == 'role')))
    from bot.discord_ui import devlog
    await devlog.update_step(pid, member, name, 'Posted from the MCP.' if res.get('ok') else f"MCP post refused: {res.get('msg')}",
                             final=(('Added to the earlier update' if use_merge else 'Posted') + ' (via MCP)') if res.get('ok') else 'Not posted')
    if not res.get('ok'):
        return res.get('msg') or 'Could not post.'
    return ('Added to the earlier update: ' if use_merge else 'Posted: ') + res['url']


def updates_text(allowed, game):
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    rows = edit.recent([hit[0]], 6)
    if not rows:
        return f'{hit[1]}: no updates posted yet.'
    out = [f'{hit[1]}: latest updates, newest first (use the id with edit_update).']
    for r in rows:
        f, c, n, v = edit.lines(r)
        body = ' | '.join([*(f'fix: {x}' for x in f), *(f'change: {x}' for x in c), *(f'new: {x}' for x in n)])[:900]
        out.append(f"- update id {r['id']} ({announce._ago(r['posted_at'])}{', ' + v if v else ''}): {body}")
    return '\n'.join(out)


async def edit_update(member, allowed, update_id, fixes=None, changes=None, whats_new=None, version=None):
    row = edit.by_id(update_id)
    if not row or str(row['tag_id']) not in {str(t) for t, _ in allowed}:
        return 'No update with that id among your games.'
    ok, msg = await edit.edit_posted(row, None if fixes is None else _fix_list(fixes), None if changes is None else _fix_list(changes),
                                     None if whats_new is None else _fix_list(whats_new), None if version is None else str(version).strip())
    if ok:
        from bot.discord_ui import devlog
        await devlog.update_step(int(row['id']) + 1000000, member, row['game_name'], 'Edited a posted update from the MCP.', final='Posted (edited via MCP)')
    return ('Edited: ' + msg) if ok else msg
