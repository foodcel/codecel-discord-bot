"""/bug and /improvement for everyone: a short form that makes the post in the right forum for the player. From then on the bot treats it
exactly like a post written by hand: it checks it, tags it, asks for what is missing and sends it to the dev who owns the game.
(Testers using /bug in the testing channel keep their own flow, see tester.py.)"""
import asyncio
import io
import re
import time

import discord

from bot.discord_ui.components import NO_MENTIONS, FormModal
from bot.core.ctx import fetch_channel
from bot.core.db import bug_by_id, now, run, update_bug
from bot.core.env import cfg
from bot.features.bugs.tags import find_device_tag, tag_name, to_suggest_tag_id
from bot.features.bugs.tester import _keep, _pending, quote, safe
from bot.features.bugs.transcript import download, upload_limit
from bot.discord_ui.ui import E, EM, columns, cut, describe, flat, head, labeled, sentence

# /improvement takes up to 5 screenshots and 2 videos (/bug takes 10 and 5, see tester.ATTACH)
IMPROVE_ATTACH = {
    'screenshots': [f'screenshot_{k + 1}' if k else 'screenshot' for k in range(5)],
    'videos': [f'video_{k + 1}' if k else 'video' for k in range(2)],
}
COOLDOWN = 45  # seconds between two forms of the same player
_last = {}

KINDS = {
    'bug': {'noun': 'bug report', 'command': '/bug', 'icon': '🐛'},
    'suggestion': {'noun': 'improvement', 'command': '/improvement', 'icon': '💡'},
}


def _attach_names(kind):
    from bot.features.bugs.tester import ATTACH
    a = ATTACH if kind == 'bug' else IMPROVE_ATTACH
    return [*a['screenshots'], *a['videos']]


def _device_tag(text):
    """Mobile / Computer / Controller from what the player wrote."""
    t = (text or '').lower()
    for word, tag in (('controller', 'Controller'), ('playstation', 'Controller'), ('ps4', 'Controller'), ('ps5', 'Controller'),
                      ('xbox', 'Controller'), ('console', 'Controller'), ('gamepad', 'Controller'),
                      ('phone', 'Mobile'), ('mobile', 'Mobile'), ('ios', 'Mobile'), ('iphone', 'Mobile'), ('ipad', 'Mobile'),
                      ('android', 'Mobile'), ('tablet', 'Mobile'),
                      ('pc', 'Computer'), ('computer', 'Computer'), ('laptop', 'Computer'), ('mac', 'Computer'), ('keyboard', 'Computer')):
        if re.search(rf'\b{word}\b', t):
            return find_device_tag(tag)
    return None


async def command_form(i, opts, kind):
    reply = i.response.send_message
    meta = KINDS[kind]
    forum_id = cfg.bugs_id if kind == 'bug' else cfg.suggestions_id
    if not forum_id:
        return await reply(f"{meta['command']} is not set up here.", ephemeral=True)
    wait = COOLDOWN - (time.time() - _last.get((i.user.id, kind), 0))
    if wait > 0:
        return await reply(f"Please wait {int(wait) + 1} seconds before sending another {meta['noun']}.", ephemeral=True)
    tag_id = opts.get('game')
    if not tag_name(tag_id):
        return await reply('Pick a game from the list.', ephemeral=True)
    if kind == 'suggestion' and not to_suggest_tag_id(tag_id):
        return await reply('That game has no tag in the improvement forum yet. Ask a developer.', ephemeral=True)
    files = []
    for n in _attach_names(kind):
        a = opts.get(n)
        if a:
            files.append({'url': a['url'], 'name': a['filename'], 'size': a['size'], 'type': a.get('content_type') or ''})
    token = _keep(files)
    if kind == 'bug':
        inputs = [
            {'id': 'title', 'label': 'Short title', 'style': 'short', 'required': True, 'max': 80, 'placeholder': 'e.g. Notes stop responding after restarting a song'},
            {'id': 'what', 'label': 'What happened', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': 'Describe the bug'},
            {'id': 'steps', 'label': 'How can we make it happen again?', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': '1. ... 2. ... 3. ...'},
            {'id': 'expected', 'label': 'What should happen (optional)', 'style': 'paragraph', 'required': False, 'max': 500, 'placeholder': ''},
            {'id': 'device', 'label': 'Device / platform (optional)', 'style': 'short', 'required': False, 'max': 60, 'placeholder': 'e.g. PC, PS5, iPhone 14'},
        ]
    else:
        inputs = [
            {'id': 'title', 'label': 'Short title', 'style': 'short', 'required': True, 'max': 80, 'placeholder': 'e.g. Improve the timing accuracy'},
            {'id': 'what', 'label': 'What should be added or changed?', 'style': 'paragraph', 'required': True, 'max': 1000, 'placeholder': 'Describe your idea'},
            {'id': 'why', 'label': 'Why, and any extra details (optional)', 'style': 'paragraph', 'required': False, 'max': 800, 'placeholder': ''},
        ]
    return await i.response.send_modal(FormModal(f'fm:{kind}:{tag_id}:{token}', f"{meta['noun'].capitalize()} · {tag_name(tag_id)}"[:45], inputs))


def _card(kind, user_id, game, form, too_big=None, image=None):
    e = flat()
    meta = KINDS[kind]
    e.title = head(meta['icon'], f'{game}')
    describe(e, f"### {form['title']}")
    if kind == 'bug':
        columns(e, [
            {'name': head(E['user'], 'Reporter'), 'lines': [f'<@{user_id}>']},
            {'name': head(E['device'], 'Device'), 'lines': [f"`{form['device']}`" if form['device'] else 'Not given']},
        ])
        labeled(e, head(E['note'], 'What happened'), quote(sentence(form['what'])))
        labeled(e, head('🔁', 'How to make it happen'), form['steps'])
        if form['expected']:
            labeled(e, head(E['fixed'], 'Should happen'), sentence(form['expected']))
    else:
        columns(e, [{'name': head(E['user'], 'Player'), 'lines': [f'<@{user_id}>']}])
        labeled(e, head('💡', 'The idea'), sentence(form['what']))
        if form['why']:
            labeled(e, head(E['note'], 'Why'), sentence(form['why']))
    if too_big:
        labeled(e, head(E['video'], 'Too big to attach'), '\n'.join(too_big) + '\nPost the file in this post.')
    if image:
        e.set_image(url=f'attachment://{image}')
    e.set_footer(text=f"Sent with {meta['command']} · replies go in this post")
    return e


async def _files(chosen):
    """Re-uploads the chosen files so they never expire: batches of 10 within the upload limit. Too big or failed ones become links."""
    limit = upload_limit()
    batches, too_big, placed, used = [[]], [], [], 0
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
    return batches, too_big, first_image['name'] if first_image else None


async def modal_form(i, kind, tag_id, token, fields, analyze=True):
    """The form was sent: make the post in the forum, save it, and let the bot check it like any other post."""
    await i.response.defer(ephemeral=True, thinking=True)
    meta = KINDS[kind]
    game = tag_name(tag_id)
    keys = ('title', 'what', 'steps', 'expected', 'device') if kind == 'bug' else ('title', 'what', 'why')
    form = {k: (fields.get(k) or '').strip() for k in ('title', 'what', 'steps', 'expected', 'device', 'why')}
    form = {k: (form[k] if k in keys else '') for k in form}
    chosen = (_pending.pop(token, None) or {}).get('files', [])
    _last[(i.user.id, kind)] = time.time()

    forum = await fetch_channel(cfg.bugs_id if kind == 'bug' else cfg.suggestions_id)
    if forum is None:
        return await i.edit_original_response(content='I could not find the forum. Ask a developer.')
    tags = []
    game_tag = forum.get_tag(int(tag_id if kind == 'bug' else to_suggest_tag_id(tag_id)))
    if game_tag:
        tags.append(game_tag)
    dev = _device_tag(form['device']) if kind == 'bug' else None
    if dev and forum.get_tag(int(dev['id'])):
        tags.append(forum.get_tag(int(dev['id'])))
    batches, too_big, image = await _files(chosen)
    created = await forum.create_thread(
        name=cut(form['title'], 100), embeds=[_card(kind, i.user.id, game, form, too_big, image)], files=batches[0],
        applied_tags=tags, allowed_mentions=NO_MENTIONS, reason=f"{meta['command']} by {i.user}")
    thread = created.thread
    for k, extra in enumerate(batches[1:]):
        if extra:
            await thread.send(content=f'📎 **MORE FILES**{EM}·{EM}{k + 2} of {len(batches)}', files=extra, allowed_mentions=NO_MENTIONS)
    body = (f"What happened: {form['what']}\nSteps: {form['steps']}" + (f"\nShould happen: {form['expected']}" if form['expected'] else '')
            if kind == 'bug' else f"{form['what']}" + (f"\nWhy: {form['why']}" if form['why'] else ''))
    id_ = run("""INSERT INTO bugs(thread_id,reporter_id,game_tag_id,game_name,title,status,created_at,last_msg_id,device,body,source,kind)
        VALUES(?,?,?,?,?,'new',?,?,?,?,'form',?)""",
              str(thread.id), str(i.user.id), tag_id, game, form['title'], now(), str(thread.last_message_id or thread.id),
              form['device'] or None, body, kind).lastrowid
    if analyze:
        asyncio.ensure_future(_analyze(id_, thread, kind))
    await i.edit_original_response(content=f"{E['fixed']} **POSTED**{EM}·{EM}Your {meta['noun']} is here: {thread.jump_url}\nThe bot is checking it now. If it needs anything it will ask you in the post.")
    return id_


async def _analyze(id_, thread, kind):
    try:
        bug = bug_by_id(id_)
        if kind == 'bug':
            from bot.features.bugs.intake import analyze_and_act
        else:
            from bot.features.bugs.suggest import analyze_and_act
        await analyze_and_act(bug, thread)
    except Exception as e:
        print('form analysis', repr(e))
        update_bug(id_, {'status': 'new'})  # the next start retries it (catch-up)


def message_text(src):
    """The words of a message: its text, or the text of an embed a bot made."""
    parts = [src.content or '']
    for e in src.embeds:
        parts += [e.title or '', e.description or ''] + [f'{f.name}: {f.value}' for f in e.fields]
    return NL_.join(p.strip() for p in parts if p and p.strip())


NL_ = chr(10)


def message_files(src):
    return [{'name': a.filename, 'url': a.url, 'size': a.size, 'type': a.content_type or ''} for a in src.attachments]


async def post_from_message(src, saver, kind, tag_id=None):
    """A dev replied `!bug` or `!improve` to a message: the forum post is made from it, then checked like any other post.
    The player who wrote the message is the reporter (they hear when it is fixed); the dev who saved it is named in the footer."""
    text = message_text(src)
    first = (text.splitlines()[0] if text else '').strip()
    form = {'title': cut(first, 70) or 'Report from a message', 'what': cut(text, 1500) or 'See the attached files.',
            'steps': '', 'expected': '', 'device': '', 'why': ''}
    forum = await fetch_channel(cfg.bugs_id if kind == 'bug' else cfg.suggestions_id)
    if forum is None:
        return None
    game = tag_name(tag_id) if tag_id else None
    tags = []
    if tag_id:
        tag = forum.get_tag(int(tag_id if kind == 'bug' else to_suggest_tag_id(tag_id) or 0))
        if tag:
            tags.append(tag)
    batches, too_big, image = await _files(message_files(src))
    reporter = saver.id if src.author.bot else src.author.id
    e = _card(kind, reporter, game or 'New report', form, too_big, image)
    labeled(e, head('🔗', 'Original message'), f'[Open it]({src.jump_url})')
    e.set_footer(text=f"Saved from a message by {saver.display_name} · replies go in this post")
    created = await forum.create_thread(name=cut(form['title'], 100), embeds=[e], files=batches[0], applied_tags=tags,
                                        allowed_mentions=NO_MENTIONS, reason=f"{KINDS[kind]['command']} reply by {saver}")
    thread = created.thread
    for k, extra in enumerate(batches[1:]):
        if extra:
            await thread.send(content=f'📎 **MORE FILES**{EM}·{EM}{k + 2} of {len(batches)}', files=extra, allowed_mentions=NO_MENTIONS)
    id_ = run("""INSERT INTO bugs(thread_id,reporter_id,game_tag_id,game_name,title,status,created_at,last_msg_id,body,source,kind,saved_by)
        VALUES(?,?,?,?,?,'new',?,?,?,'form',?,?)""",
              str(thread.id), str(reporter), tag_id, game, form['title'], now(), str(thread.last_message_id or thread.id), form['what'], kind, str(saver.id)).lastrowid
    asyncio.ensure_future(_analyze(id_, thread, kind))
    return id_, thread


def card_from_message(src, saver, kind, tag_id=None):
    """The card a `!bug` reply would post, for the test channel: nothing is saved."""
    text = message_text(src)
    first = (text.splitlines()[0] if text else '').strip()
    form = {'title': cut(first, 70) or 'Report from a message', 'what': cut(text, 1500) or 'See the attached files.',
            'steps': '', 'expected': '', 'device': '', 'why': ''}
    names = [a.filename for a in src.attachments]
    e = _card(kind, saver.id if src.author.bot else src.author.id, tag_name(tag_id) if tag_id else 'New report', form,
              [f'{n} (would be attached)' for n in names] or None)
    labeled(e, head('🔗', 'Original message'), f'[Open it]({src.jump_url})')
    e.set_footer(text=f'Saved from a message by {saver.display_name} · replies go in this post')
    return e

