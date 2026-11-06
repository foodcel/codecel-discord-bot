"""/bug for testers in the testing channel: a form, a thread in the tester channel, and the bug goes to the owning dev's board.
Everyone else uses the same command through forms.py."""
import random
import re
import string
import time
import uuid

from bot.discord_ui.card import notice, card, links_in, row
from bot.features.bugs.nums import label
from bot.core.ai import summarize_tester_report
from bot.discord_ui.components import NO_MENTIONS, FormModal
from bot.core.ctx import fetch_channel
from bot.core.db import bug_by_id, now, run, update_bug
from bot.features.bugs.devboard import route_bug
from bot.core.env import cfg
from bot.core.perms import level
from bot.features.bugs.tags import ensure_tester_tag, find_game_tag, game_tags, tag_name
from bot.discord_ui.ui import E, EM, SEVERITY, cut, sentence

def safe(n):
    return re.sub(r'[^\w.\-]+', '_', str(n), flags=re.ASCII)[:60]


# Attachments chosen on the slash command must survive until the form is submitted.
_pending = {}  # token -> {'files': [...], 't': ms}


def evidence(opts):
    """([files the player attached], the links box) from a /bug or /suggest command."""
    files = [{'url': a['url'], 'name': a['filename'], 'size': a['size'], 'type': a.get('content_type') or ''}
             for a in (opts.get(n) for n in ('file',) + tuple(f'file_{n}' for n in range(2, 11))) if a]
    return files, (opts.get('links') or '').strip()


def _keep(files, game=None, links=''):
    token = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    for k in [k for k, v in _pending.items() if time.time() * 1000 - v['t'] > 15 * 60000]:
        del _pending[k]
    _pending[token] = {'files': files, 't': time.time() * 1000, 'game': game, 'links': links}
    return token


def is_tester(m):
    """Testers, plus devs and admins. Only inside the tester channel."""
    if not m:
        return False
    return level(m) != 'none' or any(str(r.id) in cfg.tester_roles for r in m.roles)


def known_games():
    """Every game a tester can report: the games in the testing phase (released ones too), and the released ones that have a tag."""
    from bot.features.games.games import clean_name, game_lists
    lists = game_lists()
    names = [clean_name(g.get('title') or g['name']) for g in lists['unreleased'] + lists['released'] if g.get('testing_at')] + [t['name'] for t in game_tags()]  # the games in testing, and the released ones that have a tag
    return list(dict.fromkeys(n for n in names if n))


def resolve_game(value):
    """(game name, bugs-forum tag id or None) for what a tester picked or typed; (None, None) when no game fits."""
    from bot.features.games.games import key
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
        from bot.features.bugs.forms import command_form
        return await command_form(i, opts, 'bug')
    game, tag_id = resolve_game(opts.get('game'))
    if not game:
        return await reply('Pick a game from the list.', ephemeral=True)
    token = _keep(*evidence(opts), game=game)
    return await i.response.send_modal(FormModal(f'tb:{tag_id or 0}:{token}', f'Bug report · {game}'[:45], [
        {'id': 'title', 'label': 'Short title', 'style': 'short', 'required': True, 'max': 80, 'placeholder': 'e.g. Car falls through the map'},
        {'id': 'what', 'label': 'What happened', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': 'Describe the bug'},
        {'id': 'steps', 'label': 'Steps to reproduce', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': '1. ... 2. ... 3. ...'},
        {'id': 'expected', 'label': 'What should happen (optional)', 'style': 'paragraph', 'required': False, 'max': 500, 'placeholder': ''},
        {'id': 'device', 'label': 'Device / platform / build (optional)', 'style': 'short', 'required': False, 'max': 60, 'placeholder': 'e.g. PC, PS5, iPhone 14'},
    ]))


NL = chr(10)


def quote(text):
    """What the player wrote, with a quote bar."""
    return '\n'.join('> ' + line for line in str(text).split('\n'))


def tester_report_embed(bug, form, tester_id, too_big=None, media=None, origin=None):
    """The report posted inside the tester thread, as a card: (view, files)."""
    facts = NL.join([row('Game', bug['game_name']), row('Tester', f'<@{tester_id}>'), row('Severity', SEVERITY.get(bug['severity']) or '?'),
                     row('Device', f"`{form['device']}`" if form['device'] else 'Not given')])
    blocks = [bug['summary'] or '', facts, f"**{E['note']} What happened**{NL}{quote(sentence(form['what']))}"]
    if form['steps']:
        blocks.append(f"**🔁 Steps to reproduce**{NL}{form['steps']}")
    if form['expected']:
        blocks.append(f"**{E['fixed']} Should happen**{NL}{sentence(form['expected'])}")
    if origin:
        blocks.append(f"**🔗 Original message**{NL}[Open it]({origin})")
    typed = links_in(form.get('what'), form.get('steps'), form.get('expected'), form.get('links'))
    if typed:
        blocks.append(f"**🔗 Links**{NL}" + NL.join(typed))
    if too_big:
        blocks.append(f"**{E['video']} Too big to attach**{NL}" + NL.join(too_big) + f'{NL}Post the file in this thread.')
    from datetime import datetime, timezone
    return card(f"🧪 {label(bug)} · {bug['title']}", blocks, ['Tester report · reply here to add more files or links'], media=media,
                when=datetime.fromtimestamp(bug['created_at'] / 1000, timezone.utc))


async def create_report(reporter_id, game, tag_id, form, ai, batches, too_big, media, origin=None, saved_by=None):
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
              f'pending-{uuid.uuid4().hex}', str(reporter_id), tag_id, game, ai.get('title') or form['title'], ai['summary'], ai['severity'],
              'new', now(), form.get('device') or None, body, 'tester', str(saved_by) if saved_by else None).lastrowid
    bug = bug_by_id(id_)
    try:
        created = await forum.create_thread(
            name=cut(f"{label(bug)} {bug['title']}", 100), view=(made := tester_report_embed(bug, form, reporter_id, too_big, media, origin))[0], files=batches[0] + made[1],
            applied_tags=[tag] if tag else [], allowed_mentions=NO_MENTIONS, reason=f'Tester report for {game}')
    except Exception:
        run('DELETE FROM bugs WHERE id=?', id_)
        raise
    thread = created.thread
    update_bug(id_, {'thread_id': str(thread.id), 'last_msg_id': str(created.message.id)})
    for k, extra in enumerate(batches[1:]):
        if extra:
            await thread.send(content=f'📎 More files · {k + 2} of {len(batches)}', files=extra, allowed_mentions=NO_MENTIONS)
    await route_bug(bug_by_id(id_))  # ghost ping to the owner and the dev board
    from bot.features.testers.testers import schedule_refresh
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
    form['links'] = kept.get('links', '')
    ai = {'title': form['title'], 'summary': cut(form['what'], 200), 'severity': 'medium'}
    try:
        ai = await summarize_tester_report(game, form['title'], form['what'], form['steps'], form['expected'], form['device'])
    except Exception as e:
        print('summarizeTesterReport', e)
    from bot.features.bugs.forms import _files, with_clips
    chosen = await with_clips(chosen, form['what'], form['steps'], form['expected'], form.get('links'))  # clip links become real videos
    batches, too_big, media = await _files(chosen)  # re-uploaded so the files never expire
    done = await create_report(i.user.id, game, tag_id, form, ai, batches, too_big, media)
    if not done:
        return await i.edit_original_response(content='I could not find the testers forum. Ask a developer.')
    id_, thread = done
    return await i.edit_original_response(view=notice(f"{E['fixed']} **Sent**{EM}·{EM}to the {game} developer: {thread.jump_url}\nMore files or links? Reply in the post, as many as you like.")[0])


async def report_from_message(src, saver, game, tag_id):
    """A tester replied `!bug` to a message in the testing channel: the post is made from it. The player who wrote the message is the reporter."""
    from bot.features.bugs.forms import _files, message_files, message_text, with_clips
    text = message_text(src)
    first = (text.splitlines()[0] if text else '').strip()
    form = {'title': cut(first, 70) or 'Report from a message', 'what': cut(text, 1500) or 'See the attached files.', 'steps': '', 'expected': '', 'device': ''}
    ai = {'title': form['title'], 'summary': cut(form['what'], 200), 'severity': 'medium'}
    try:
        ai = await summarize_tester_report(game, form['title'], form['what'], '', '', '')
    except Exception as e:
        print('summarizeTesterReport', e)
    batches, too_big, media = await _files(await with_clips(message_files(src), text))
    reporter = saver.id if src.author.bot else src.author.id
    return await create_report(reporter, game, tag_id, form, ai, batches, too_big, media, origin=src.jump_url, saved_by=saver.id)
