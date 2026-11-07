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
BIG = ('high', 'critical')  # what the critical mode waits for
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


ASK_GAP_HOURS, ASKS_PER_HOUR = 6, 10
_asked = defaultdict(deque)


async def ask_reporter(member, allowed, bug_id, questions):
    """Posts a short question card in the report's thread, pinging only the reporter. The report stays with the dev; the answer lands in the transcript."""
    from bot.core.ctx import fetch_channel
    from bot.core.db import all_
    from bot.core.db import now as now_ms
    from bot.discord_ui.components import allowed as only
    from bot.features.bugs import replies
    b, why = reports.owned(allowed, bug_id)
    if not b:
        return why
    qs = [str(q).strip() for q in (questions or []) if str(q).strip()][:3]
    if not qs:
        return 'Give one to three short questions.'
    if b['status'] in st.DONE:
        return 'That report is closed. Ask in Discord if you really need to.'
    q, t = _asked[str(member.id)], time.monotonic()
    while q and t - q[0] > 3600:
        q.popleft()
    if len(q) >= ASKS_PER_HOUR:
        return f'Limit reached: at most {ASKS_PER_HOUR} questions an hour.'
    recent = all_('SELECT 1 FROM kv WHERE k=? AND CAST(v AS INTEGER) > ?', f"mcp_ask:{b['id']}", now_ms() - ASK_GAP_HOURS * 3600000)
    if recent:
        return f'This reporter was asked less than {ASK_GAP_HOURS} hours ago. Wait for the answer (read the transcript).'
    thread = await fetch_channel(b['thread_id'])
    if not thread:
        return 'The post is gone.'
    view, files = replies.dev_question(b['reporter_id'], qs)
    await thread.send(view=view, files=files, allowed_mentions=only(users=[b['reporter_id']]))
    from bot.core.db import kv_set
    kv_set(f"mcp_ask:{b['id']}", now_ms())
    q.append(t)
    return 'Asked. The reporter was pinged in the post. Read the transcript later to see the answer.'


async def set_progress(member, allowed, game, percent=-1, working=''):
    """How far the game is (0-100) and whether the dev is working on it: the same as /progress. The progress bar is on the bounty board."""
    from bot.features.games.games import apply_progress
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    w = None if working in ('', None) else str(working).lower() in ('yes', 'true', 'on', '1')
    ok, text = await apply_progress(member, hit[1], None if percent is None or int(percent) < 0 else int(percent), w, None, '', ping=False)
    return ('Saved: ' if ok else '') + text


async def set_testing(member, allowed, game, on=True, play_link='', note=''):
    """Puts the game into testing (or takes it out): the same as /progress testing. The tester card is posted without a ping."""
    from bot.features.games.games import apply_progress
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    ok, text = await apply_progress(member, hit[1], None, None, 'on' if on else 'off', play_link or '', ping=False, note=(note or None))
    return ('Saved: ' if ok else '') + text


async def edit_game(member, allowed, game, title='', online='', description=''):
    """Changes how a RELEASED game shows in the library: its title, whether it is online, and the short line under it (a single - removes the line)."""
    from bot.core.db import run
    from bot.core.perms import owns
    from bot.features.games.games import NONE, _find, clean_name, owner_ids, refresh_game_board
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    k, rel, _ = _find(hit[1])
    if not rel or hit[1] == NONE:
        return f'{hit[1]} is not released yet. Only released games can be edited here.'
    if not owns(member, owner_ids(rel)):
        return 'Only the dev who owns this game can change it.'
    changes = {}
    if (title or '').strip():
        changes['title'] = title.strip()[:100]
    if (online or '').strip().lower() in ('online', 'offline'):
        changes['online'] = 1 if online.strip().lower() == 'online' else 0
    if (description or '').strip():
        changes['notes'] = None if description.strip() == '-' else description.strip()[:140]
    if not changes:
        return 'Nothing to change: give a title, online (online or offline) or a description.'
    if 'online' in changes:
        from bot.features.games.watch import forget
        forget(k)  # by hand: the automatic watch starts from nothing for this game
    run(f"UPDATE game_status SET {','.join(c + '=?' for c in changes)} WHERE key=?", *changes.values(), k)
    await refresh_game_board()
    return f"Updated {clean_name(rel['name'])}: " + ', '.join(f"{c} {'removed' if v is None else v}" for c, v in changes.items()) + '.'


def testers_text(member, allowed, game):
    """Who volunteered to test the game, and which other testers are open to it, with their devices and free times."""
    from bot.core.ctx import ctx
    from bot.features.games.games import key as game_key
    from bot.features.testers import testers
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    roster = {r['user_id']: r for r in testers.everyone()}
    from bot.features.testers.testerboard import testers_of
    volunteers = testers_of(game_key(hit[1]))

    def line(uid):
        r = roster.get(uid) or {}
        m = ctx.guild.get_member(int(uid)) if ctx.guild else None
        return f"- {m.display_name if m else uid}: devices {r.get('devices') or '?'}; free {r.get('availability') or '?'}; best for {r.get('best_for') or '?'}"

    rest = [u for u, r in roster.items() if u not in volunteers and (r['status'] == 'active' or (r['status'] == 'private' and r['only_for'] in (str(member.id), testers.ANY_DEV)))]
    out = [f'{hit[1]}: {len(volunteers)} tester(s) volunteered' + (':' if volunteers else '.')] + [line(u) for u in volunteers]
    if rest:
        out += [f'Other testers open for testing ({len(rest)}):'] + [line(u) for u in rest[:15]]
    return reports.fence(reports.clean(chr(10).join(out)))


def add_note(allowed, bug_id, text):
    """Adds a line to the developer note of a report (it shows on the report for the dev)."""
    from bot.core.db import update_bug
    b, why = reports.owned(allowed, bug_id)
    if not b:
        return why
    text = ' '.join(str(text or '').split())[:300]
    if not text:
        return 'Give a note.'
    update_bug(b['id'], {'note': ((b.get('note') + chr(10)) if b.get('note') else '') + text})
    return 'Note added.'


def policy(tag_id):
    g = get_game(tag_id) or {}
    return (g.get('mcp_mode') if g.get('mcp_mode') in MODES else 'manual'), int(g.get('mcp_count') or 5)


def merge_hours(tag_id):
    return announce.merge_hours(tag_id)


def agent_may_ping(tag_id):
    return bool((get_game(tag_id) or {}).get('agent_ping'))


def settings_text(tag_id, name):
    mode, n = policy(tag_id)
    hours = merge_hours(tag_id)
    return (f"{name}: your agent posts {'only when you say so' if mode == 'manual' else 'after every fix' if mode == 'every' else 'when a high or critical fix is waiting' if mode == 'critical' else f'after {n} fixes'}"
            f" ({mode}). Merging: {f'updates within {hours} hours fold into one card' if hours else 'off, every update is a new card'}. "
            f"Pings: {'the agent may ping' if agent_may_ping(tag_id) else 'the agent may not ping'}.")


def set_settings(allowed, game, mode=None, count=None, merge=None, ping=None):
    """The update settings of a game. Anything left out stays as it is; with nothing given it only shows the current settings."""
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    if reports.untagged(hit[0]):
        return f'{hit[1]} is in development or testing: update settings start once the game is released.'
    patch = {}
    if mode:
        mode = mode.lower()
        if mode not in MODES:
            return (f"Mode must be one of: {', '.join(MODES)}. manual = only post when your dev tells you; every = after each fixed report; "
                    'critical = when a high or critical fix is waiting; count = after `count` fixes.')
        patch['mcp_mode'] = mode
    if count:
        patch['mcp_count'] = max(1, min(int(count), 50))
    if merge is not None and int(merge) >= 0:
        patch['merge_hours'] = min(int(merge), 72)
    if ping:
        if ping.lower() not in ('on', 'off'):
            return 'ping must be on or off.'
        patch['agent_ping'] = 1 if ping.lower() == 'on' else 0
    if patch:
        upsert_game(hit[0], hit[1], patch)
    return settings_text(hit[0], hit[1])


def due_text(allowed, game):
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    tag_id, name = hit
    if reports.untagged(tag_id):
        return f'{name} is in development or testing: it has no updates yet. Fix reports and set their status; updates start once the game is released.'
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
        out.append(f"Last update: id {last['id']}, {announce._ago(last['posted_at'])}." + (' It can still be merged into.' if announce.recent_announcement(str(tag_id)) else ''))
    return '\n'.join(out)


async def post_update(member, allowed, game, fixes=None, changes=None, whats_new=None, bug_ids=None, version='', ping='none', merge=True):
    """Posts an update through the normal pipeline. bug_ids are the fixed reports it announces (their reporters are told, as always)."""
    hit = reports.find_game(allowed, game)
    if not hit:
        return f'No game of yours matches "{game}".'
    tag_id, name = hit
    if reports.untagged(tag_id):
        return f'{name} is in development or testing: updates are for released games.'
    fixes, changes, new = _fix_list(fixes), _fix_list(changes), _fix_list(whats_new)
    bugs, sugs = [], []
    for i in bug_ids or []:
        b, why = reports.owned(allowed, i)
        if not b or reports.key_of(b) != str(tag_id):
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
    if ping == 'role' and not agent_may_ping(tag_id):
        return 'Your dev has not allowed pings for this game (update settings, ping on). Post without a ping, or ask them.'
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
    if reports.untagged(hit[0]):
        return f'{hit[1]}: no updates yet, it is in development or testing.'
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
