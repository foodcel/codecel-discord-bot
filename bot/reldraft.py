"""The preview a dev sees after /release new, /release quiet or /release edit: the new-game card and the library entry exactly as they would
look, with buttons under them to post, edit or cancel. Nothing is posted or saved until Post (or Save) is pressed. The draft lives in the
database, so the buttons keep working after a restart."""
from pathlib import Path

import discord
from discord import ui

from .cards import BLUE, game_row, new_game_container, ping_target
from .components import NO_MENTIONS, FormModal
from .db import del_pending, get_pending, set_pending
from .games import clean_name
from .perms import level
from .release import ROBLOX_GAME, commit_edit, commit_release, roblox_info, summary

NL = chr(10)
PINGS = [('everyone', '@everyone', 'Everyone in the server'), ('updates', '@Updates', 'Only people who want updates'),
         ('releases', '@Releases', 'Only people who want new releases'), ('none', 'No ping', 'The card appears silently')]


def draft_row(d):
    """The game_status row a release draft would become."""
    info, art, mine = d['info'], d['art'], d.get('mine')
    return {'key': d['key'], 'name': d['name'], 'owners': d['owners'], 'link': d['link'], 'place_id': info.get('place_id'), 'roblox_name': info.get('name'),
            'creator': info.get('creator'), 'hero_url': mine or info.get('hero_url'), 'icon_url': info.get('icon_url'), 'hero_file': d.get('hero_file'),
            'studio': d['studio'], 'original_name': d['original'], 'notes': d.get('note'), 'title': d.get('title'),
            'art_url': None if mine else art['art_url'], 'art_hero_url': None if mine else art['art_hero_url']}


def _row(d):
    return draft_row(d) if d['kind'] == 'release' else {**d['rel'], **d['changes']}


def text_view(text):
    view = ui.LayoutView()
    view.add_item(ui.TextDisplay(text[:3900]))
    return view


def payload(pid):
    """The message a draft is shown as: {'view', 'attachments', 'allowed_mentions'}."""
    d = get_pending(pid)
    row = _row(d)
    release, quiet = d['kind'] == 'release', d.get('quiet')
    shown = row.get('title') or clean_name(row['name'])
    what = {'release': 'RELEASE', 'edit': 'CHANGES'}[d['kind']] if not quiet else 'QUIET RELEASE'
    head = f"### 🧪 PREVIEW · {what}{NL}-# Nothing is posted yet. Check it, change what you want, then press {'Post' if release else 'Save'}.{NL}{summary(row, shown)}"
    view, files = ui.LayoutView(), []
    view.add_item(ui.TextDisplay(head))
    if release and not quiet:
        label = {k: n for k, n, _ in PINGS}[d['ping']]
        text, role, _ = ping_target(d['ping'])
        view.add_item(ui.TextDisplay(f"-# 🎉 New-game card · pings **{label}**" + ('' if text or d['ping'] == 'none' else ' (not set up yet)')))
        if text:
            view.add_item(ui.TextDisplay(text))  # the ping sits above the card
        card, fs = new_game_container(row, None)
        view.add_item(card)
        files += fs
    view.add_item(ui.TextDisplay('-# 📚 In the library'))
    items, fs = game_row(row)
    view.add_item(ui.Container(*items, accent_colour=BLUE))
    files += fs
    view.add_item(ui.Separator())
    ok = {'release': ('Add quietly' if quiet else 'Post'), 'edit': 'Save'}[d['kind']]
    view.add_item(ui.ActionRow(
        ui.Button(custom_id=f'rel:post:{pid}', label=ok, style=discord.ButtonStyle.success, emoji='✅'),
        ui.Button(custom_id=f'rel:edit:{pid}', label='Edit details', style=discord.ButtonStyle.primary, emoji='✏️'),
        ui.Button(custom_id=f'rel:cancel:{pid}', label='Cancel', style=discord.ButtonStyle.danger)))
    if release and not quiet:
        view.add_item(ui.ActionRow(ui.Select(
            custom_id=f'rel:ping:{pid}', placeholder='Who gets pinged',
            options=[discord.SelectOption(label=n, value=k, description=desc, default=k == d['ping']) for k, n, desc in PINGS])))
    return {'view': view, 'attachments': files, 'allowed_mentions': NO_MENTIONS}


def _discard(d):
    """A cancelled draft: the picture saved for it goes too."""
    for path in (d.get('hero_file'), (d.get('changes') or {}).get('hero_file')):
        if path and '-draft' in str(path):
            Path(path).unlink(missing_ok=True)


async def _guard(i, pid):
    """The draft, or None after telling the person why not."""
    d = get_pending(pid)
    if not d:
        await i.response.edit_message(view=text_view('This draft is gone.'), attachments=[])
        return None
    if str(i.user.id) != d['user'] and level(i.user) != 'admin':
        await i.response.send_message('This draft belongs to someone else.', ephemeral=True)
        return None
    return d


async def on_button(i, action, pid):
    d = await _guard(i, pid)
    if not d:
        return
    if action == 'cancel':
        _discard(d)
        del_pending(pid)
        return await i.response.edit_message(view=text_view('🗑️ **CANCELLED**\nNothing was posted or saved.'), attachments=[])
    if action == 'edit':
        row = _row(d)
        spec = lambda id_, label, value, mx=100: {'id': id_, 'label': label, 'style': 'short', 'required': False, 'max': mx, 'value': (value or '')[:mx]}
        return await i.response.send_modal(FormModal(f'reled:{pid}', 'Edit details', [
            spec('title', 'Title shown (blank = the board name)', row.get('title')),
            spec('link', 'Roblox game link', row.get('link'), 300),
            spec('studio', 'Original studio', row.get('studio')),
            spec('original', 'Original game name', row.get('original_name')),
            spec('note', 'Description (multiplayer, bugs, one map...)', row.get('notes'), 140)]))
    if action == 'post':
        await i.response.defer()
        done, text = await (commit_release(i, d) if d['kind'] == 'release' else commit_edit(i, d))
        if not done:  # the draft stays: pick another ping, or wait
            return await i.followup.send(text, ephemeral=True)
        del_pending(pid)
        return await i.edit_original_response(view=text_view(text), attachments=[])


async def on_select(i, pid, value):
    d = await _guard(i, pid)
    if not d:
        return
    d['ping'] = value
    set_pending(pid, d)
    return await i.response.edit_message(**payload(pid))


async def on_modal(i, pid, fields):
    d = get_pending(pid)
    if not d:
        return await i.response.send_message('This draft is gone.', ephemeral=True)
    if str(i.user.id) != d['user'] and level(i.user) != 'admin':
        return await i.response.send_message('This draft belongs to someone else.', ephemeral=True)
    f = {k: (v or '').strip() for k, v in fields.items()}
    link = f.get('link', '')
    if link and not ROBLOX_GAME.search(link):
        return await i.response.send_message('Paste the Roblox game link: it looks like roblox.com/games/123456/Name', ephemeral=True)
    if link and link != _row(d).get('link'):  # a new link: the name, creator and picture come from it
        await i.response.defer()
        info = await roblox_info(link) or {}
        if d['kind'] == 'release':
            d['link'], d['info'] = link, info
        else:
            d['changes'].update({'link': link, 'place_id': info.get('place_id'), 'roblox_name': info.get('name'), 'creator': info.get('creator')})
            for k in ('hero_url', 'icon_url'):
                if info.get(k):
                    d['changes'][k] = info[k]
        answer = i.edit_original_response
    else:
        answer = None
    if d['kind'] == 'release':
        d.update({'title': f.get('title') or None, 'studio': f.get('studio') or None, 'original': f.get('original') or d['original'], 'note': f.get('note') or None})
    else:
        ch, rel = d['changes'], d['rel']
        for field, col in (('title', 'title'), ('studio', 'studio'), ('original', 'original_name'), ('note', 'notes')):
            v = f.get(field) or None
            if v != (rel.get(col) or None):
                ch[col] = v
            else:
                ch.pop(col, None)
    set_pending(pid, d)
    if answer:
        return await answer(**payload(pid))
    return await i.response.edit_message(**payload(pid))
