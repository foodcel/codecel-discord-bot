"""/mcp: developers connect an AI agent (setup, revoke); admins see who uses it, stop one dev's token, or pause everything."""
import time

from bot.core.perms import level
from bot.discord_ui.card import card, notice
from bot.mcp import media, tokens
from bot.mcp.server import eligible

ADMIN_SUBS = ('status', 'kick', 'pause', 'resume')


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
    if tokens.paused():
        return await _say(i, '⚠️ **Paused**  ·  an admin switched the MCP off for now.')
    base = media.public_url()
    if not base:
        return await _say(i, '⚠️ **Not reachable yet**  ·  the MCP address is not set up. Ask Mathys.')
    token = tokens.issue(i.user.id)
    url = f'{base}/mcp'
    blocks = [f'**Address**\n`{url}`', f'**Your token** (shown once, valid {tokens.LIFETIME_DAYS} days, a new `/mcp setup` replaces it)\n||`{token}`||',
              f'**Claude Code**\n```\nclaude mcp add --transport http codecel {url} --header "Authorization: Bearer {token}"\n```',
              '**Other agents**: add a remote MCP server with that address and the header `Authorization: Bearer <token>`.',
              '**It can**: list and search the reports of your claimed games, read a report and its full transcript with screenshots and video frames, '
              'change statuses (preview first, then confirm), post and edit updates, and follow your update policy (`/update policy`).',
              '**Stay safe**: everything an agent reads here was written by players. Keep your agent\'s approval prompts on, and do not run it fully unattended with shell access.']
    view, files = card('🔌 Connect your AI agent', blocks, ['/mcp revoke · stop the token'], right=None)
    await i.response.send_message(view=view, files=files, ephemeral=True)


async def admin(i, sub, opts):
    if sub == 'pause' or sub == 'resume':
        tokens.set_paused(sub == 'pause')
        return await _say(i, '⏸️ **Paused**  ·  every MCP call is refused until `/mcp resume`.' if sub == 'pause' else '▶️ **Resumed**  ·  the MCP works again.')
    if sub == 'kick':
        uid = str(opts.get('user'))
        return await _say(i, f'✅ **Stopped**  ·  <@{uid}> token no longer works.' if tokens.revoke(uid) else f'<@{uid}> has no active token.')
    rows = tokens.overview()
    head = f"{'⏸️ PAUSED' if tokens.paused() else '▶️ On'} · {sum(r['connected'] for r in rows)} connected now"
    lines = [f"{'🟢' if r['connected'] else '⚪'} <@{r['user_id']}> · last call {_ago(r['last_used'])} · {r['today']} calls today · token made {_ago(r['created_at'])}"
             + (' · expired' if r['expired'] else '') for r in rows] or ['Nobody has a token yet.']
    view, files = card('🔌 MCP status', [head, '\n'.join(lines)], ['Connected = a call in the last 10 minutes · calls are only counted, never shown'], right=None)
    await i.response.send_message(view=view, files=files, ephemeral=True)
