"""/bug for testers in the testing channel: a form, a thread in the tester channel, and the bug goes to the owning dev's board.
Everyone else uses the same command through forms.py."""
import io
import random
import re
import string
import time

import discord

from .ai import summarize_tester_report
from .components import NO_MENTIONS, FormModal
from .ctx import fetch_channel
from .db import bug_by_id, now, run, update_bug
from .devboard import route_bug
from .env import cfg
from .perms import level
from .tags import ensure_tester_tag, find_game_tag, game_tags, tag_name
from .transcript import download, upload_limit
from .ui import E, EM, SEVERITY, columns, cut, describe, flat, head, labeled, sentence

# /bug takes up to 10 screenshots and 5 videos: screenshot, screenshot_2 ... screenshot_10, video, video_2 ... video_5
ATTACH = {
    'screenshots': [f'screenshot_{k + 1}' if k else 'screenshot' for k in range(10)],
    'videos': [f'video_{k + 1}' if k else 'video' for k in range(5)],
}


def safe(n):
    return re.sub(r'[^\w.\-]+', '_', str(n), flags=re.ASCII)[:60]


# Attachments chosen on the slash command must survive until the form is submitted.
_pending = {}  # token -> {'files': [...], 't': ms}


def _keep(files, game=None):
    token = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    for k in [k for k, v in _pending.items() if time.time() * 1000 - v['t'] > 15 * 60000]:
        del _pending[k]
    _pending[token] = {'files': files, 't': time.time() * 1000, 'game': game}
    return token


def is_tester(m):
    """Testers, plus devs and admins. Only inside the tester channel."""
    if not m:
        return False
    return level(m) != 'none' or any(str(r.id) in cfg.tester_roles for r in m.roles)


def known_games():
    """Every game a tester can report: the games in the testing phase, and the released ones that have a tag."""
    from .games import clean_name, game_lists
    lists = game_lists()
    names = [clean_name(g['name']) for g in lists['testing']] + [t['name'] for t in game_tags()]  # the games in testing, and the released ones that have a tag
    return list(dict.fromkeys(n for n in names if n))


def resolve_game(value):
    """(game name, bugs-forum tag id or None) for what a tester picked or typed; (None, None) when no game fits."""
    from .games import key
    if value and tag_name(value):
        return tag_name(value), str(value)
    k = key(value or '')
    if not k:
        return None, None
    names = known_games()
    name = next((n for n in names if key(n) == k), None)
    if not name:
        near = [n for n in names if len(k) >= 3 and (k in key(n) or (len(key(n)) >= 4 and key(n) in k))]
        name = near[0] if len(near) == 1 else None
    if not name:
        return None, None
    tag = find_game_tag(name)
    return name, (tag['id'] if tag else None)


async def command_bug(i, opts):
    """opts: the slash command's options (see interactions.get_options)."""
    reply = i.response.send_message
    if not (cfg.testing_id and str(i.channel_id) == cfg.testing_id and is_tester(i.user)):
        # everyone else (and testers outside the testing channel) send a normal report: it becomes a post in the bug forum
        from .forms import command_form
        return await command_form(i, opts, 'bug')
    game, tag_id = resolve_game(opts.get('game'))
    if not game:
        return await reply('Pick a game from the list.', ephemeral=True)
    files = []
    for n in [*ATTACH['screenshots'], *ATTACH['videos']]:
        a = opts.get(n)
        if a:
            files.append({'url': a['url'], 'name': a['filename'], 'size': a['size'], 'type': a.get('content_type') or ''})
    token = _keep(files, game)
    return await i.response.send_modal(FormModal(f'tb:{tag_id or 0}:{token}', f'Bug report · {game}'[:45], [
        {'id': 'title', 'label': 'Short title', 'style': 'short', 'required': True, 'max': 80, 'placeholder': 'e.g. Car falls through the map'},
        {'id': 'what', 'label': 'What happened', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': 'Describe the bug'},
        {'id': 'steps', 'label': 'Steps to reproduce', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': '1. ... 2. ... 3. ...'},
        {'id': 'expected', 'label': 'What should happen (optional)', 'style': 'paragraph', 'required': False, 'max': 500, 'placeholder': ''},
        {'id': 'device', 'label': 'Device / platform / build (optional)', 'style': 'short', 'required': False, 'max': 60, 'placeholder': 'e.g. PC, PS5, iPhone 14'},
    ]))


def tester_report_embed(bug, form, tester_id, too_big=None, image=None, origin=None):
    """The report card posted inside the tester thread."""
    e = flat()
    e.title = head('🧪', f"#{bug['id']} · {bug['game_name']}")
    describe(e, f"### {bug['title']}\n{bug['summary'] or ''}")
    columns(e, [
        {'name': head(E['user'], 'Tester'), 'lines': [f'<@{tester_id}>']},
        {'name': head(E['severity'], 'Severity'), 'lines': [SEVERITY.get(bug['severity']) or '?']},
        {'name': head(E['device'], 'Device'), 'lines': [form['device'] or 'Not given']},
    ])
    labeled(e, head(E['note'], 'What happened'), sentence(form['what']))
    if form['steps']:
        labeled(e, head('🔁', 'Steps to reproduce'), form['steps'])
    if origin:
        labeled(e, head('🔗', 'Original message'), f'[Open it]({origin})')
    if form['expected']:
        labeled(e, head(E['fixed'], 'Should happen'), sentence(form['expected']))
    if too_big:
        labeled(e, head(E['video'], 'Too big to attach'), '\n'.join(too_big) + '\nPost the file in this thread.')
    if image:
        e.set_image(url=f'attachment://{image}')
    e.set_footer(text='Tester report · devs reply in this post')
    from datetime import datetime, timezone
    e.timestamp = datetime.fromtimestamp(bug['created_at'] / 1000, timezone.utc)
    return e


async def create_report(reporter_id, game, tag_id, form, ai, batches, too_big, image, origin=None, saved_by=None):
    """The post in the testers' forum (tagged with the game), the bug saved, and the owner told. Returns (bug id, thread), or None without the forum."""
    forum = await fetch_channel(cfg.tester_forum_id)
    if forum is None:
        return None
    tag, problem = await ensure_tester_tag(game)
    if problem:
        print('tester tag', problem)
    body = f"What happened: {form['what']}" + (f"\nSteps: {form['steps']}" if form['steps'] else '') + (f"\nShould happen: {form['expected']}" if form['expected'] else '')
    id_ = run("""INSERT INTO bugs(thread_id,reporter_id,game_tag_id,game_name,title,summary,severity,status,created_at,
        device,body,source,saved_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              '0', str(reporter_id), tag_id, game, ai.get('title') or form['title'], ai['summary'], ai['severity'],
              'new', now(), form.get('device') or None, body, 'tester', str(saved_by) if saved_by else None).lastrowid
    bug = bug_by_id(id_)
    try:
        created = await forum.create_thread(
            name=cut(f"#{id_} {bug['title']}", 100), embeds=[tester_report_embed(bug, form, reporter_id, too_big, image, origin)], files=batches[0],
            applied_tags=[tag] if tag else [], allowed_mentions=NO_MENTIONS, reason=f'Tester report for {game}')
    except Exception:
        run('DELETE FROM bugs WHERE id=?', id_)
        raise
    thread = created.thread
    update_bug(id_, {'thread_id': str(thread.id), 'last_msg_id': str(created.message.id)})
    for k, extra in enumerate(batches[1:]):
        if extra:
            await thread.send(content=f'📎 **MORE FILES**{EM}·{EM}{k + 2} of {len(batches)}', files=extra, allowed_mentions=NO_MENTIONS)
    await route_bug(bug_by_id(id_))  # ghost ping to the owner and the dev board
    from .testers import schedule_refresh
    schedule_refresh()  # the roster shows how many reports each tester made
    return id_, thread


async def modal_bug(i, tag_id, token, fields):
    """Form submitted: make the post in the testers' forum, save the bug, send it to the dev board."""
    await i.response.defer(ephemeral=True, thinking=True)
    kept = _pending.pop(token, None) or {}
    game = kept.get('game') or tag_name(tag_id)
    if not game:
        return await i.edit_original_response(content='That form ran out of time. Use `/bug` again.')
    tag_id = None if str(tag_id) == '0' else tag_id
    form = {k: (fields.get(k) or '').strip() for k in ('title', 'what', 'steps', 'expected', 'device')}
    chosen = kept.get('files', [])
    ai = {'title': form['title'], 'summary': cut(form['what'], 200), 'severity': 'medium'}
    try:
        ai = await summarize_tester_report(game, form['title'], form['what'], form['steps'], form['expected'], form['device'])
    except Exception as e:
        print('summarizeTesterReport', e)
    from .forms import _files
    batches, too_big, image = await _files(chosen)  # re-uploaded so the files never expire
    done = await create_report(i.user.id, game, tag_id, form, ai, batches, too_big, image)
    if not done:
        return await i.edit_original_response(content='I could not find the testers forum. Ask a developer.')
    id_, thread = done
    return await i.edit_original_response(content=f"{E['fixed']} **SENT**{EM}·{EM}#{id_} went to the {game} developer. Follow it here: {thread.jump_url}")


async def report_from_message(src, saver, game, tag_id):
    """A tester replied `!bug` to a message in the testing channel: the post is made from it. The player who wrote the message is the reporter."""
    from .forms import _files, message_files, message_text
    text = message_text(src)
    first = (text.splitlines()[0] if text else '').strip()
    form = {'title': cut(first, 70) or 'Report from a message', 'what': cut(text, 1500) or 'See the attached files.', 'steps': '', 'expected': '', 'device': ''}
    ai = {'title': form['title'], 'summary': cut(form['what'], 200), 'severity': 'medium'}
    try:
        ai = await summarize_tester_report(game, form['title'], form['what'], '', '', '')
    except Exception as e:
        print('summarizeTesterReport', e)
    batches, too_big, image = await _files(message_files(src))
    reporter = saver.id if src.author.bot else src.author.id
    return await create_report(reporter, game, tag_id, form, ai, batches, too_big, image, origin=src.jump_url, saved_by=saver.id)
