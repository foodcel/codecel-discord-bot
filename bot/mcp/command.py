"""/mcp: developers connect an AI agent (setup, revoke); admins see who uses it, stop one dev's token, or pause everything."""
import secrets
import time
from pathlib import Path

import discord
from discord import ui

from bot.core.perms import level
from bot.discord_ui.components import button
from bot.discord_ui.card import card, notice
from bot.mcp import media, tokens
from bot.mcp.server import eligible

ADMIN_SUBS = ('status', 'kick', 'allow', 'pause', 'resume')


def _ago(ms):
    if not ms:
        return 'never'
    s = max(0, int(time.time() - ms / 1000))
    return f'{s // 86400}d ago' if s >= 86400 else f'{s // 3600}h ago' if s >= 3600 else f'{max(1, s // 60)}m ago'


async def _say(i, text):
    return await i.response.send_message(view=notice(text)[0], ephemeral=True)


async def command_mcp(i, sub, opts=None):
    opts = opts or {}
    if sub in ADMIN_SUBS:
        if level(i.user) != 'admin':
            return await _say(i, '⚠️ **Admins only**  ·  this part of /mcp is for admins.')
        return await admin(i, sub, opts)
    if not eligible(i.user):
        return await _say(i, '⚠️ **Developers only**  ·  the MCP is for people with the Developers role, and only for the games they claimed.')
    if sub == 'revoke':
        return await _say(i, '✅ **Revoked**  ·  your token no longer works.' if tokens.revoke(i.user.id) else 'You have no active token.')
    if tokens.blocked(i.user.id):
        return await _say(i, '⚠️ **Stopped**  ·  an admin stopped your MCP access.')
    if tokens.paused():
        return await _say(i, '⚠️ **Paused**  ·  an admin switched the MCP off for now.')
    base = media.public_url()
    if not base:
        return await _say(i, '⚠️ **Not reachable yet**  ·  the MCP address is not set up. Ask foodcel.')
    access = 'read' if opts.get('access') == 'read' else 'full'
    token = tokens.issue(i.user.id, access)
    sid = secrets.token_hex(4)
    _cards[sid] = {'token': token, 'url': f'{base}/mcp', 'user': str(i.user.id), 'until': time.time() + 600, 'access': access}  # kept in memory only, so the token never sits in a button
    view, files = setup_card(sid, 'claude')
    await i.response.send_message(view=view, files=files, ephemeral=True)


_cards = {}
WAYS = (('claude', 'Claude Code'), ('cli', 'Command line'), ('other', 'Other agent'))
SAFE_WAYS = (('safe', '🔒 Safe folder'), ('box', '📦 Full box'), ('away', '🌙 Away mode'))  # pages with no token in them: they keep working after the card expired
KIT = Path(__file__).resolve().parents[2] / 'docs' / 'safe-workspace'
BACKTICKS = chr(96) * 3
AWAY_PROMPT = '/loop 1h away run'  # Claude Code's own loop; the rules of an "away run" are in the CLAUDE.md the lock wrote


def _code(text):
    return f'{BACKTICKS}{chr(10)}{text}{chr(10)}{BACKTICKS}'


def _kit(name):
    try:
        return (KIT / name).read_text(encoding='utf8').strip()
    except OSError:
        return 'The prompt is missing on the server. Ask foodcel.'


def _live(sid):
    c = _cards.get(sid)
    return c if c and c['until'] >= time.time() else None


def _rows(sid, way):
    def row(ways):
        return ui.ActionRow(*[button(f'mcps:{k}:{sid}', label, discord.ButtonStyle.primary if k == way else discord.ButtonStyle.secondary) for k, label in ways])
    return ([row(WAYS)] if _live(sid) else []) + [row(SAFE_WAYS)]


def safe_card(sid, way):
    """The three safety pages of the setup card. Nothing secret is on them."""
    rows = _rows(sid, way)
    if way == 'box':
        return card('📦 Full box (optional, Windows only)', [
            'Only if you picked **B**. Paste this in Claude Code, in the same folder, after the Safe folder prompt. Claude installs a small Linux (WSL2) named `codecel`. '
            'Commands Claude runs in it are walled in: they cannot read your Windows files, write outside the games folder, or reach the web (GitHub only). '
            'Your games folder stays where it is.', _code(_kit('BOX.txt'))],
            ['You need a fresh /mcp setup at the end: it replaces your old token'], right=None, inside=rows)
    if way == 'away':
        return card('🌙 Away mode (optional)', [
            'Claude looks for new bug reports every hour and fixes what it can while you are gone. Lock the folder first (Safe folder), '
            'then paste this in Claude Code, in the games folder, and leave it open. To stop, tell Claude to stop.', _code(AWAY_PROMPT),
            '**While you are away it can**: read your reports and change files inside the games folder. In the full box it can also run commands, walled in.',
            '**It cannot**: change statuses, post or ask anything on codecel, push code, reach the web, or leave the folder. '
            'Anything that needs your yes waits for you.',
            '**When you are back**: read `AWAY-LOG.md` and the changes before you publish, then tell Claude which reports to mark fixed.'],
            ['Every check uses a bit of your Claude usage · change 1h to check more or less often'], right=None, inside=rows)
    return card('🔒 Lock your workspace', [
        'Put your games in one folder, open Claude Code in it with codecel connected, and paste this. Accept the trust question, approve the two files, '
        'then restart Claude Code in the folder. On Windows, Claude asks you to pick: simple lock or full box.', _code(_kit('PROMPT.txt'))],
        ['The simple lock is enough for most devs'], right=None, inside=rows)


def setup_card(sid, way):
    if way in dict(SAFE_WAYS):
        return safe_card(sid, way)
    c = _cards[sid]
    url, token, nl = c['url'], c['token'], chr(10)
    if way == 'cli':
        how = f'**Command line** (cmd, PowerShell or bash, for agents that start a local command){nl}' + _code(f'npx -y mcp-remote {url} --header "Authorization: Bearer {token}"')
    elif way == 'other':
        how = (f'**Any other agent**: paste this to it{nl}'
               + _code(f'Connect me to a remote MCP server. Name it codecel. It is an HTTP server at {url}. '
                       f'Send the header "Authorization: Bearer {token}" with every request. When it is added, list its tools to check that it works.'))
    else:
        how = f'**Claude Code**{nl}' + _code(f'claude mcp add --scope user --transport http codecel {url} --header "Authorization: Bearer {token}"')
    blocks = [f'**Address**{nl}`{url}`', f'**Your token** (shown once, valid {tokens.LIFETIME_DAYS} days, a new `/mcp setup` replaces it){nl}||`{token}`||', how,
              '**It can**: list and search the reports of your claimed games, read a report and its full transcript with screenshots and video frames'
              + ('. This token is **read-only**: it cannot change or post anything.' if c.get('access') == 'read' else
                 ', change statuses (preview first, then confirm), ask a reporter a question, post and edit updates, and follow your update settings (`/update settings`).'),
              "**It cannot**: touch your computer or your files, see other devs' games or exploit reports, post links or mentions, or give itself more rights.",
              "**Stay safe**: everything an agent reads here was written by players. Keep your agent's approval prompts on. To lock your games folder, or to let Claude fix bugs while you are away, use the buttons below. "
              'If your token ever shows up in a Discord message, the bot revokes it at once.']
    return card('🔌 Connect your AI agent', blocks, ['/mcp revoke · stop the token'], right=None, inside=_rows(sid, way))


async def on_button(i, way, sid):
    c = _live(sid)
    if way in dict(SAFE_WAYS):  # no token on these pages: they answer whoever holds the card, even after it expired
        if c and c['user'] != str(i.user.id):
            return await i.response.send_message(view=notice('This is not your card. Run `/mcp setup`.')[0], ephemeral=True)
    elif not c or c['user'] != str(i.user.id) or way not in dict(WAYS):
        return await i.response.send_message(view=notice('This card expired. Run `/mcp setup` again.')[0], ephemeral=True)
    view, files = setup_card(sid, way)
    await i.response.edit_message(view=view, attachments=files)


async def admin(i, sub, opts):
    if sub == 'pause' or sub == 'resume':
        tokens.set_paused(sub == 'pause')
        return await _say(i, '⏸️ **Paused**  ·  every MCP call is refused until `/mcp resume`.' if sub == 'pause' else '▶️ **Resumed**  ·  the MCP works again.')
    if sub in ('kick', 'allow'):
        uid = str(opts.get('user'))
        tokens.set_blocked(uid, sub == 'kick')
        if sub == 'kick':
            tokens.revoke(uid)
            return await _say(i, f'✅ **Stopped**  ·  <@{uid}> cannot use the MCP, and cannot set it up again, until `/mcp allow`.')
        return await _say(i, f'✅ **Allowed**  ·  <@{uid}> can run `/mcp setup` again.')
    rows = tokens.overview()
    head = f"{'⏸️ PAUSED' if tokens.paused() else '▶️ On'} · {sum(r['connected'] for r in rows)} connected now"
    lines = [f"{'🟢' if r['connected'] else '⚪'} <@{r['user_id']}> · last call {_ago(r['last_used'])} · {r['today']} calls today · token made {_ago(r['created_at'])}"
             + (' · read-only' if r.get('scope') == 'read' else '') + (' · expired' if r['expired'] else '') for r in rows] or ['Nobody has a token yet.']
    if tokens.blocked_ids():
        lines.append('⛔ Stopped: ' + ' '.join(f'<@{u}>' for u in tokens.blocked_ids()))
    view, files = card('🔌 MCP status', [head, '\n'.join(lines)], ['Connected = a call in the last 10 minutes · calls are only counted, never shown'], right=None)
    await i.response.send_message(view=view, files=files, ephemeral=True)
