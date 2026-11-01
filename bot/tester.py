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
from .tags import tag_name
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


def _keep(files):
    token = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    for k in [k for k, v in _pending.items() if time.time() * 1000 - v['t'] > 15 * 60000]:
        del _pending[k]
    _pending[token] = {'files': files, 't': time.time() * 1000}
    return token


def is_tester(m):
    """Testers, plus devs and admins. Only inside the tester channel."""
    if not m:
        return False
    return level(m) != 'none' or any(str(r.id) in cfg.tester_roles for r in m.roles)


async def command_bug(i, opts):
    """opts: the slash command's options (see interactions.get_options)."""
    reply = i.response.send_message
    if not (cfg.testing_id and str(i.channel_id) == cfg.testing_id and is_tester(i.user)):
        # everyone else (and testers outside the testing channel) send a normal report: it becomes a post in the bug forum
        from .forms import command_form
        return await command_form(i, opts, 'bug')
    tag_id = opts.get('game')
    if not tag_name(tag_id):
        return await reply('Pick a game from the list.', ephemeral=True)
    files = []
    for n in [*ATTACH['screenshots'], *ATTACH['videos']]:
        a = opts.get(n)
        if a:
            files.append({'url': a['url'], 'name': a['filename'], 'size': a['size'], 'type': a.get('content_type') or ''})
    token = _keep(files)
    return await i.response.send_modal(FormModal(f'tb:{tag_id}:{token}', f'Bug report · {tag_name(tag_id)}'[:45], [
        {'id': 'title', 'label': 'Short title', 'style': 'short', 'required': True, 'max': 80, 'placeholder': 'e.g. Car falls through the map'},
        {'id': 'what', 'label': 'What happened', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': 'Describe the bug'},
        {'id': 'steps', 'label': 'Steps to reproduce', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': '1. ... 2. ... 3. ...'},
        {'id': 'expected', 'label': 'What should happen (optional)', 'style': 'paragraph', 'required': False, 'max': 500, 'placeholder': ''},
        {'id': 'device', 'label': 'Device / platform / build (optional)', 'style': 'short', 'required': False, 'max': 60, 'placeholder': 'e.g. PC, PS5, iPhone 14'},
    ]))


def tester_report_embed(bug, form, tester_id, too_big=None, image=None):
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
    labeled(e, head('🔁', 'Steps to reproduce'), form['steps'])
    if form['expected']:
        labeled(e, head(E['fixed'], 'Should happen'), sentence(form['expected']))
    if too_big:
        labeled(e, head(E['video'], 'Too big to attach'), '\n'.join(too_big) + '\nPost the file in this thread.')
    if image:
        e.set_image(url=f'attachment://{image}')
    e.set_footer(text='Tester report · devs reply in this thread')
    from datetime import datetime, timezone
    e.timestamp = datetime.fromtimestamp(bug['created_at'] / 1000, timezone.utc)
    return e


async def modal_bug(i, tag_id, token, fields):
    """Form submitted: make the thread, save the bug, send it to the dev board."""
    await i.response.defer(ephemeral=True, thinking=True)
    game = tag_name(tag_id)
    form = {k: (fields.get(k) or '').strip() for k in ('title', 'what', 'steps', 'expected', 'device')}
    chosen = (_pending.pop(token, None) or {}).get('files', [])

    ai = {'title': form['title'], 'summary': cut(form['what'], 200), 'severity': 'medium'}
    try:
        ai = await summarize_tester_report(game, form['title'], form['what'], form['steps'], form['expected'], form['device'])
    except Exception as e:
        print('summarizeTesterReport', e)

    # Re-upload the files into the thread so they never expire. Discord allows 10 files and one upload limit per message,
    # so they go out in batches. Files that are too big or fail become links on the card.
    limit = upload_limit()
    batches = [[]]
    too_big = []
    placed = []
    used = 0
    for n, f in enumerate(chosen):
        if f['size'] > limit:
            too_big.append(f"[{f['name']}]({f['url']})")
            continue
        cur = batches[-1]
        if len(cur) >= 10 or used + f['size'] > limit:
            cur = []
            batches.append(cur)
            used = 0
        try:
            name = f"{n + 1}-{safe(f['name'])}"
            cur.append(discord.File(io.BytesIO(await download(f['url'])), filename=name))
            placed.append({'f': f, 'name': name, 'first': len(batches) == 1})
            used += f['size']
        except Exception:
            too_big.append(f"[{f['name']}]({f['url']})")
    first_image = next((p for p in placed if p['first'] and re.match(r'^image/(png|jpe?g|gif|webp)', p['f']['type'])), None)

    testing = await fetch_channel(cfg.testing_id)
    thread = await testing.create_thread(
        name=cut(ai.get('title') or form['title'], 90), type=discord.ChannelType.public_thread,
        auto_archive_duration=10080, reason=f'Tester report by {i.user}')
    body = f"What happened: {form['what']}\nSteps: {form['steps']}" + (f"\nShould happen: {form['expected']}" if form['expected'] else '')
    id_ = run("""INSERT INTO bugs(thread_id,reporter_id,game_tag_id,game_name,title,summary,severity,status,created_at,
        device,body,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
              str(thread.id), str(i.user.id), tag_id, game, ai.get('title') or form['title'], ai['summary'], ai['severity'],
              'new', now(), form['device'] or None, body, 'tester').lastrowid
    bug = bug_by_id(id_)
    try:
        await thread.edit(name=cut(f"#{id_} {bug['title']}", 100))
    except Exception:
        pass
    sent = await thread.send(
        embeds=[tester_report_embed(bug, form, i.user.id, too_big, first_image['name'] if first_image else None)],
        files=batches[0], allowed_mentions=NO_MENTIONS)
    for k, extra in enumerate(batches[1:]):
        if extra:
            await thread.send(content=f'📎 **MORE FILES**{EM}·{EM}{k + 2} of {len(batches)}', files=extra, allowed_mentions=NO_MENTIONS)
    update_bug(id_, {'last_msg_id': str(sent.id)})
    await route_bug(bug_by_id(id_))  # ghost ping to the owner and the dev board
    from .testers import schedule_refresh
    schedule_refresh()  # the roster shows how many reports each tester made
    return await i.edit_original_response(content=f"{E['fixed']} **SENT**{EM}·{EM}#{id_} went to the {game} developer. Follow it here: {thread.jump_url}")


async def thread_from_message(src, saver, tag_id):
    """A tester replied `!bug` to a message: the same thread in the testing channel as /bug makes, filled from the message."""
    from .forms import _files, message_files, message_text
    game = tag_name(tag_id)
    text = message_text(src)
    first = (text.splitlines()[0] if text else '').strip()
    form = {'title': cut(first, 70) or 'Report from a message', 'what': cut(text, 1500) or 'See the attached files.', 'steps': '', 'expected': '', 'device': ''}
    ai = {'title': form['title'], 'summary': cut(form['what'], 200), 'severity': 'medium'}
    try:
        ai = await summarize_tester_report(game, form['title'], form['what'], '', '', '')
    except Exception as e:
        print('summarizeTesterReport', e)
    batches, too_big, image = await _files(message_files(src))
    testing = await fetch_channel(cfg.testing_id)
    thread = await testing.create_thread(name=cut(ai.get('title') or form['title'], 90), type=discord.ChannelType.public_thread,
                                         auto_archive_duration=10080, reason=f'Tester report by {saver}')
    reporter = saver.id if src.author.bot else src.author.id
    id_ = run("""INSERT INTO bugs(thread_id,reporter_id,game_tag_id,game_name,title,summary,severity,status,created_at,body,source)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              str(thread.id), str(reporter), tag_id, game, ai.get('title') or form['title'], ai['summary'], ai['severity'], 'new', now(),
              form['what'], 'tester').lastrowid
    bug = bug_by_id(id_)
    try:
        await thread.edit(name=cut(f"#{id_} {bug['title']}", 100))
    except Exception:
        pass
    e = tester_report_embed(bug, form, reporter, too_big, image)
    labeled(e, head('🔗', 'Original message'), f'[Open it]({src.jump_url})')
    sent = await thread.send(embeds=[e], files=batches[0], allowed_mentions=NO_MENTIONS)
    for k, extra in enumerate(batches[1:]):
        if extra:
            await thread.send(content=f'📎 **MORE FILES**{EM}·{EM}{k + 2} of {len(batches)}', files=extra, allowed_mentions=NO_MENTIONS)
    update_bug(id_, {'last_msg_id': str(sent.id)})
    await route_bug(bug_by_id(id_))
    from .testers import schedule_refresh
    schedule_refresh()
    return id_, thread

