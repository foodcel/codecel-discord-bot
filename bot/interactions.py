"""Everything people click, select, type as a slash command or submit as a form. Answered in one place, by parsing the
custom_id, so buttons on old messages keep working after a restart."""
import discord
from discord import app_commands

from .ai import interpret_note
from .announce import (draft_payload, polish_dev_updates, polish_fixes, post_announcement, snooze, unannounced)
from . import board as bounty_board
from .bounty import board_name_for, get_claims, owners_for
from .bugview import handle_view, open_game
from . import commands as bounty_board_commands
from .components import NO_MENTIONS, FormModal, make_view, modal_fields, select
from .ctx import dm, fetch_channel
from .db import (bug_by_id, create_pending, get_game, get_pending, get_prefs, set_pending, set_prefs, update_bug, upsert_game)
from .devboard import board_components, exploit_buttons, exploit_status_line, open_bugs_for, route_bug, schedule_boards
from .env import cfg
from .fixes import apply_status
from .fixlog import log_page, open_log, send_fix_transcript
from .games import autocomplete_games, command_gamelink, command_progress, command_games, command_release
from .perms import can_confirm, can_manage, level
from .previews import post_previews
from .strikes import pardon, resolve_strike, rules_embed, strike_info
from .tags import find_device_tag, find_game_tag, game_tags, set_tags, tag_name
from .tester import command_bug, modal_bug
from .transcript import board_transcript, single_transcript
from .ui import E, EM, describe as describe_embed
import re


def http(u):
    return bool(re.match(r'^https?://', u or '', re.I))


# ---- reading what Discord sent ----
def get_options(i):
    """(subcommand or None, {option name: value}, (focused name, value) or None). Attachments come back as dicts."""
    opts = i.data.get('options') or []
    sub = None
    if opts and opts[0].get('type') == 1:
        sub = opts[0]['name']
        opts = opts[0].get('options') or []
    resolved = i.data.get('resolved') or {}
    out = {}
    focused = None
    for o in opts:
        v = o.get('value')
        if o.get('type') == 11:
            v = (resolved.get('attachments') or {}).get(str(v))
        out[o['name']] = v
        if o.get('focused'):
            focused = (o['name'], v)
    return sub, out, focused


async def deny(i, text='You do not have permission for that.'):
    return await i.response.send_message(text, ephemeral=True)


def owner_of(tag_id):
    return owners_for(tag_id, tag_name(tag_id) or '')


# ---- autocomplete ----
async def autocomplete(i):
    name = i.data['name']
    sub, _, focused = get_options(i)
    fname, fvalue = focused or ('', '')
    if name in bounty_board_commands.BOARD_NAMES:
        return await bounty_board.autocomplete(i, name, fvalue)
    if name in ('release', 'unrelease', 'games', 'gamelink', 'progress'):
        return await autocomplete_games(i, name, fvalue)
    q = str(fvalue).lower()
    if fname == 'board':
        lst = [{'name': c['name'][:100], 'value': c['name'][:100]} for c in get_claims()]
    else:
        only_mine = name == 'update' or (name == 'config' and sub == 'set')
        lst = [{'name': t['name'], 'value': t['id']} for t in game_tags() if not only_mine or can_manage(i.user, owner_of(t['id']))]
    await i.response.autocomplete([app_commands.Choice(name=c['name'], value=c['value']) for c in lst if q in c['name'].lower()][:25])


# ---- /config ----
def describe_game(g):
    owners = owners_for(g['tag_id'], g['name'])
    owners_txt = ' '.join(f'<@{o}>' for o in owners) if owners else 'nobody (unclaimed)'
    return '\n'.join([
        f"Owner: {owners_txt}{' (set by admin)' if g.get('owner_override') else ''} · board name: {board_name_for(g['tag_id'], g['name']) or 'no match'}",
        f"Link: {g.get('link') or '—'} · Icon: {'set' if g.get('icon_url') else 'auto/none'}",
        f"Channel: {f'<#{g['announce_channel_id']}>' if g.get('announce_channel_id') else '—'} · Ping: {f'<@&{g['ping_role_id']}>' if g.get('ping_role_id') else '—'}",
        f"Offer an announcement at **{g['threshold']}** fixes · ready now: **{len(unannounced(g['tag_id']))}**",
    ])


async def config_set(i, opts):
    tag_id = opts.get('game')
    name = tag_name(tag_id)
    if not name:
        return await deny(i, 'Unknown game.')
    if not can_manage(i.user, owner_of(tag_id)):
        return await deny(i, 'Only the dev who claimed this game (or an admin) can change it.')
    patch = {}
    link = opts.get('link')
    icon = opts.get('icon')
    if link:
        if not http(link):
            return await deny(i, 'The link must start with http:// or https://')
        patch['link'] = link
    if icon:
        if not http(icon):
            return await deny(i, 'The icon must be an image URL starting with http(s)://')
        patch['icon_url'] = icon
    if opts.get('channel'):
        patch['announce_channel_id'] = str(opts['channel'])
    if opts.get('role'):
        patch['ping_role_id'] = str(opts['role'])
    if opts.get('threshold'):
        patch['threshold'] = opts['threshold']
    owner = opts.get('owner')
    board = opts.get('board')
    if owner or board:
        if level(i.user) != 'admin':
            return await deny(i, 'Only admins can set the owner or board name.')
        if owner:
            patch['owner_override'] = str(owner)
        if board:
            patch['board_name'] = board
    if not patch:
        return await deny(i, 'Nothing to change. Pass at least one option.')
    g = upsert_game(tag_id, name, patch)
    if patch.get('owner_override') or patch.get('board_name'):
        schedule_boards()
    return await i.response.send_message(f"Saved **{g['name']}**.\n{describe_game(g)}", ephemeral=True)


async def config_show(i, opts):
    only = opts.get('game')
    tags = [t for t in game_tags() if not only or t['id'] == only]
    text = '\n\n'.join(f"**{t['name']}**\n{describe_game(upsert_game(t['id'], t['name']))}" for t in tags)
    return await i.response.send_message(text[:1990] or 'No games.', ephemeral=True, allowed_mentions=NO_MENTIONS)


# ---- /update and the announcement drafts ----
def form_input(id_, label, style, value='', required=False):
    mx = 3000 if style == 'paragraph' else 40
    return {'id': id_, 'label': label, 'style': style, 'required': required, 'max': mx, 'value': (value or '')[:mx]}


async def command_update(i, opts):
    tag_id = opts.get('game')
    if not tag_name(tag_id):
        return await deny(i, 'Unknown game.')
    if not can_manage(i.user, owner_of(tag_id)):
        return await deny(i, 'Only the dev who claimed this game (or an admin) can post updates.')
    return await i.response.send_modal(FormModal(f'upd:{tag_id}', f'Update: {tag_name(tag_id)}'[:45], [
        form_input('updates', 'Updates (one per line)', 'paragraph'),
        form_input('version', 'Version (optional)', 'short'),
    ]))


def lines_of(s):
    out = []
    for l in (s or '').split('\n'):
        l = re.sub(r'^[\s•*\-–]+', '', l).strip()
        if l:
            out.append(l)
    return out


async def modal_update(i, tag_id, fields):
    game = upsert_game(tag_id, tag_name(tag_id))
    await i.response.defer(thinking=True)
    fixes, fix_lines, sugs, sug_lines = await polish_fixes(tag_id, game)
    pid = create_pending({
        'tagId': tag_id, 'bugIds': [f['id'] for f in fixes], 'bugfixes': fix_lines,
        'newIds': [f['id'] for f in sugs], 'newLines': sug_lines,
        'updates': await polish_dev_updates(game['name'], lines_of(fields.get('updates'))),  # Claude rewrites what the dev typed
        'version': (fields.get('version') or '').strip(),
        'owners': owner_of(tag_id),
    })
    return await i.edit_original_response(**await draft_payload(pid))


async def button_ann(i, action, pid):
    p = get_pending(pid)
    if not p:
        return await i.response.edit_message(content='This draft is gone.', embeds=[], view=None)
    if not can_manage(i.user, owner_of(p['tagId'])):
        return await deny(i)
    if action == 'edit':
        return await i.response.send_modal(FormModal(f'annedit:{pid}', 'Edit announcement', [
            form_input('bugfixes', 'Bug fixes (one per line)', 'paragraph', '\n'.join(p['bugfixes'])),
            form_input('updates', 'Updates (one per line)', 'paragraph', '\n'.join(p['updates'] + p.get('newLines', []))),
            form_input('version', 'Version (optional)', 'short', p.get('version')),
        ]))
    if action == 'later':
        snooze(pid)
        return await i.response.edit_message(content=f"{E['update']} **LATER**{EM}·{EM}I will offer this again after 3 more fixes.", embeds=[], view=None)
    await i.response.defer()
    r = await post_announcement(pid)
    if not r['ok']:
        return await i.followup.send(r['msg'], ephemeral=True)
    return await i.message.edit(content=f"{E['fixed']} **POSTED**{EM}·{EM}{r['url']}", embeds=[], view=None)


async def modal_ann_edit(i, pid, fields):
    p = get_pending(pid)
    if not p:
        return await i.response.send_message('This draft is gone.', ephemeral=True)
    from_message = i.message is not None
    if from_message:
        await i.response.defer()
    else:
        await i.response.defer(thinking=True)
    # Only update lines the dev changed get rewritten again; untouched ones keep their wording.
    typed = lines_of(fields.get('updates'))
    before = p['updates'] + p.get('newLines', [])
    same = '\n'.join(typed) == '\n'.join(before)
    updates = p['updates'] if same else await polish_dev_updates(get_game(p['tagId'])['name'], typed)
    set_pending(pid, {**p, 'bugfixes': lines_of(fields.get('bugfixes')), 'updates': updates,
                      'newLines': p.get('newLines', []) if same else [],
                      'version': (fields.get('version') or '').strip()})
    payload = await draft_payload(pid)
    if from_message:
        return await i.message.edit(**payload)
    return await i.edit_original_response(**payload)


# ---- status buttons on old per-bug messages (kept so nothing breaks) ----
async def button_bug(i, id_, status):
    bug = bug_by_id(int(id_))
    if not bug:
        return await deny(i, 'That bug no longer exists.')
    await i.response.defer(ephemeral=True, thinking=True)
    done, skipped = await apply_status([bug['id']], status, i.user, via='button')
    return await i.edit_original_response(
        content=f"#{bug['id']} → {status.replace('_', ' ', 1)}" if done else f"Could not change #{bug['id']}: {skipped[0] if skipped else 'unknown'}")


# ---- a dev's note on a bug ----
async def modal_note(i, bug_id, fields):
    """Dev note on a bug: the bot works out the game (and device/severity), retags the post and moves the bug to the right board."""
    bug = bug_by_id(int(bug_id))
    if not bug:
        return await deny(i, 'That bug no longer exists.')
    if not can_manage(i.user, owners_for(bug['game_tag_id'], bug['game_name'])):
        return await deny(i)
    await i.response.defer(ephemeral=True, thinking=True)
    note = (fields.get('note') or '').strip()
    try:
        r = await interpret_note(note, bug['title'], bug['summary'] or '', [t['name'] for t in game_tags()])
    except Exception as e:
        print('interpretNote', e)
        return await i.edit_original_response(content='I could not read that note right now. Try again in a minute.')
    game_tag = find_game_tag(r.get('game'))
    patch = {'note': note}
    if game_tag:
        patch['game_tag_id'] = game_tag['id']
        patch['game_name'] = game_tag['name']
    if r.get('severity'):
        patch['severity'] = r['severity']
    update_bug(bug['id'], patch)
    thread = await fetch_channel(bug['thread_id'])
    if thread:
        dev_tag = find_device_tag(r.get('device'))
        await set_tags(thread, game=game_tag['id'] if game_tag else None, device=dev_tag['id'] if dev_tag else None, replace_game=True)
    if not game_tag:
        schedule_boards()
        return await i.edit_original_response(
            content=f"Saved your note on #{bug['id']}, but it does not say which game. Name the game directly, like \"Vyra Station\".")
    await route_bug(bug_by_id(bug['id']))
    owners = owners_for(game_tag['id'], game_tag['name'])
    text = (f"✅ #{bug['id']} is now **{game_tag['name']}**{f' · {r['device']}' if r.get('device') else ''}"
            f"{f' · {r['severity']}' if r.get('severity') else ''}. ")
    text += (f"Sent to {' '.join(f'<@{o}>' for o in owners)}." if owners else 'Nobody has claimed that game yet, so it stays in Unclaimed.')
    return await i.edit_original_response(content=text)


# ---- exploit cards ----
async def button_exploit(i, bug_id, action):
    """Status change on an exploit card. The reporter's post was deleted, so every change is also sent to them as a DM."""
    bug = bug_by_id(int(bug_id))
    if not bug:
        return await deny(i, 'That report no longer exists.')
    if not can_manage(i.user, owners_for(bug['game_tag_id'], bug['game_name'])):
        return await deny(i)
    await i.response.defer()
    nxt = {'investigating': 'exploit_investigating', 'fixed': 'exploit_fixed', 'closed': 'exploit_closed'}.get(action)
    if not nxt:
        return
    update_bug(bug['id'], {'status': nxt})
    text = {
        'investigating': f"{E['investigating']} **INVESTIGATING**\nA developer is looking at your report \"{bug['title']}\". I will message you when it is fixed.",
        'fixed': f"{E['fixed']} **FIXED**\nThe problem in your report \"{bug['title']}\" is fixed. Thank you for reporting it safely.",
        'closed': f"{E['notbug']} **CLOSED**\nWe looked at your report \"{bug['title']}\" and it is not an exploit we can act on. Thanks for telling us.",
    }[action]
    dm_ok = await dm(bug['reporter_id'], text)
    card = discord.Embed.from_dict(i.message.embeds[0].to_dict())
    describe_embed(card, exploit_status_line(nxt, False, dm_ok))
    return await i.edit_original_response(embeds=[card], view=exploit_buttons(bug['id'], nxt))


# ---- strikes ----
async def button_strike(i, action, log_id):
    if not can_confirm(i.user):
        return await deny(i, 'Only developers can confirm or dismiss this.')
    await i.response.defer()
    res = await resolve_strike(int(log_id), action == 'confirm', str(i.user.id))
    return await i.edit_original_response(content=f'{i.message.content}\n\n{res}', view=None, allowed_mentions=NO_MENTIONS)


# ---- transcripts ----
async def button_transcript(i, id_):
    """Sends the transcript as a .md file or a zip (attach or paste into an AI agent chat), plus a copyable block when short."""
    await i.response.defer(ephemeral=True, thinking=True)
    t = await single_transcript(int(id_))
    if not t:
        return await i.edit_original_response(content='That bug no longer exists.')
    how = 'Paste the text into your AI agent chat. For images and video frames, attach the files from the zip, or unzip it into your project and tell the agent to read the folder.'
    if t['inline']:
        content = f"```md\n{t['inline']}\n```"
    else:
        content = f"{t['note']}\n{how}" if t['note'] else 'Transcript attached. Paste it into your AI agent chat.'
    return await i.edit_original_response(content=content, attachments=t['files'])


async def button_transcript_all(i, key):
    """Step 1: pick a game (or all games) from the open bugs on this board."""
    bugs = open_bugs_for(key)
    if not bugs:
        return await i.response.send_message('No open bugs.', ephemeral=True)
    by = {}
    for b in bugs:
        k = b['game_tag_id'] or 'none'
        e = by.setdefault(k, {'name': b['game_name'] or 'Unknown game', 'n': 0})
        e['n'] += 1
    options = [{'label': f'All games ({len(bugs)})', 'value': 'all'}] + [
        {'label': f"{e['name']} ({e['n']})"[:100], 'value': k} for k, e in list(by.items())[:24]]
    return await i.response.send_message('Which game do you want the transcript for?',
                                         view=make_view([[select(f'trgame:{key}', 'Pick a game', options)]]), ephemeral=True)


async def game_transcript_reply(key, game):
    t = await board_transcript(key, game)
    if not t['count']:
        return {'content': 'No open bugs for that game.', 'attachments': []}
    content = (f"**{t['count']}** open bug(s){'' if game == 'all' else f' for **{t['name']}**'} in {len(t['files'])} zip file(s), "
               f"about {t['tokens']:,} tokens of text. Each bug has its own folder with `transcript.md`"
               f"{', screenshots and video frames' if t['hasMedia'] else ''}. Unzip it into your project and tell your agent to read the folder.")
    if t['cut']:
        content += f"\n⚠️ {t['cut']} more part(s) did not fit in one message. Use the per-bug buttons for those."
    return {'content': content, 'attachments': t['files']}


async def select_transcript(i, key):
    """Step 2: build it."""
    await i.response.edit_message(content='Building the transcript…', view=None)
    return await i.edit_original_response(**await game_transcript_reply(key, i.data['values'][0]))


async def button_game_transcript(i, key, game):
    """"Whole game" button inside the bug page."""
    await i.response.defer(ephemeral=True, thinking=True)
    return await i.edit_original_response(**await game_transcript_reply(key, game))


# ---- the entry point ----
async def handle_interaction(i):
    t = i.type
    if t == discord.InteractionType.autocomplete:
        return await autocomplete(i)
    if t == discord.InteractionType.application_command:
        return await handle_command(i)
    if t == discord.InteractionType.component:
        return await handle_component(i)
    if t == discord.InteractionType.modal_submit:
        return await handle_modal(i)


async def handle_command(i):
    name = i.data['name']
    sub, opts, _ = get_options(i)
    if name == 'bug':
        return await command_bug(i, opts)  # testers have no dev role, so it skips the dev-only gate below
    board_handlers = {'claim': bounty_board.command_claim, 'unclaim': bounty_board.command_unclaim,
                      'assign': bounty_board.command_assign, 'exclude': bounty_board.command_exclude,
                      'include': bounty_board.command_include, 'bounty-board': bounty_board.command_setup}
    if name in board_handlers:  # they check the board's own role, so they skip the dev-only gate below
        return await board_handlers[name](i, opts)
    if level(i.user) in ('jr', 'none'):
        return await deny(i)
    if name == 'config':
        return await (config_set(i, opts) if sub == 'set' else config_show(i, opts))
    if name == 'update':
        return await command_update(i, opts)
    if name == 'strikes':
        u = opts['user']
        info = strike_info(u)
        rows = '\n'.join(f"• <t:{l['at'] // 1000}:d> {l['step']} ({l['state']}): {l['reason']}" for l in info['log'])
        return await i.response.send_message(f"<@{u}> has **{info['count']}** strike(s).\n{rows}", ephemeral=True, allowed_mentions=NO_MENTIONS)
    if name == 'pardon':
        u = opts['user']
        c = await pardon(u)
        return await i.response.send_message(f'Removed one strike from <@{u}>. They now have {c}.', ephemeral=True, allowed_mentions=NO_MENTIONS)
    if name == 'pings':
        b = opts.get('bugs')
        x = opts.get('exploits')
        uid = str(i.user.id)
        prefs = set_prefs(uid, bugs=(b == 'on') if b else None, exploits=(x == 'on') if x else None) if (b or x) else get_prefs(uid)
        return await i.response.send_message(
            f"{E['status']} **YOUR PINGS**\n• New bugs on your games: **{'on' if prefs['bugs'] else 'off'}**\n"
            f"• Exploit reports: **{'on' if prefs['exploits'] else 'off'}**\nChange them with `/pings bugs:off exploits:on`.", ephemeral=True)
    if name == 'preview':
        if level(i.user) != 'admin':
            return await deny(i)
        await i.response.defer(ephemeral=True, thinking=True)
        n = await post_previews(opts.get('what') or 'all')
        return await i.edit_original_response(content=f'Posted {n} preview message(s) in <#{cfg.test_id}>.')
    if name == 'release':
        return await command_release(i, opts)
    if name == 'unrelease':
        return await command_release(i, opts, True)
    if name == 'progress':
        return await command_progress(i, opts)
    if name == 'gamelink':
        return await command_gamelink(i, opts)
    if name == 'games':
        return await command_games(i, sub, opts)
    if name == 'botrules':
        if level(i.user) != 'admin':
            return await deny(i)
        await i.channel.send(embeds=[rules_embed()])
        return await i.response.send_message('Posted.', ephemeral=True)


async def handle_component(i):
    cid = i.data['custom_id']
    parts = cid.split(':')
    kind = parts[0]
    a = parts[1] if len(parts) > 1 else None
    b = parts[2] if len(parts) > 2 else None
    ctype = i.data.get('component_type')
    if ctype == 2:  # button
        if kind == 'bug':
            return await button_bug(i, a, b)
        if kind == 'ann':
            return await button_ann(i, a, int(b))
        if kind == 'strike':
            return await button_strike(i, a, b)
        if kind == 'exp':
            return await button_exploit(i, a, b)  # status buttons on a high-priority exploit card
        if kind == 'v':
            return await handle_view(i)
        if kind == 'flp':
            return await log_page(i, a, b)
        if kind == 'trg':
            return await button_game_transcript(i, a, b)
        if kind == 'tr':
            return await button_transcript(i, a)
        if kind == 'trall':
            return await button_transcript_all(i, a)
    elif ctype == 3:  # dropdown
        value = (i.data.get('values') or [None])[0]
        if kind == 'trgame':
            return await select_transcript(i, a)
        if kind == 'bd':
            return await open_game(i, a, value)
        if kind == 'fl':
            return await open_log(i, value)
        if kind == 'flt':
            return await send_fix_transcript(i, value)
        if kind == 'trpick':
            await i.response.defer(ephemeral=True, thinking=True)
            try:
                await i.message.edit(view=board_components(a))  # resets the dropdown
            except Exception:
                pass
            return await i.edit_original_response(**await game_transcript_reply(a, value))


async def handle_modal(i):
    parts = i.data['custom_id'].split(':')
    kind = parts[0]
    a = parts[1] if len(parts) > 1 else None
    b = parts[2] if len(parts) > 2 else None
    fields = modal_fields(i)
    if kind == 'tb':
        return await modal_bug(i, a, b, fields)
    if kind == 'upd':
        return await modal_update(i, a, fields)
    if kind == 'note':
        return await modal_note(i, a, fields)
    if kind == 'annedit':
        return await modal_ann_edit(i, int(a), fields)
