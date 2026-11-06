"""/mcp setup and /mcp revoke: a dev connects an AI agent (Claude Code, Codex, Pi...) to their games' reports."""
import os
import re
from pathlib import Path

from bot.discord_ui.card import card, notice
from bot.mcp import tokens

LOG = os.environ.get('MCP_TUNNEL_LOG') or str(Path.home() / 'cloudflared.log')
URL = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com')


def public_url():
    """The address devs use: MCP_URL when set, else the newest quick-tunnel address in the tunnel's log, else None."""
    if os.environ.get('MCP_URL'):
        return os.environ['MCP_URL'].rstrip('/')
    try:
        found = URL.findall(Path(LOG).read_text(errors='ignore'))
    except OSError:
        return None
    return found[-1] if found else None


async def command_mcp(i, sub):
    if sub == 'revoke':
        done = tokens.revoke(i.user.id)
        return await i.response.send_message(view=notice('✅ **Revoked**  ·  your token no longer works.' if done else 'You have no active token.')[0], ephemeral=True)
    base = public_url()
    if not base:
        return await i.response.send_message(view=notice('⚠️ **Not reachable yet**  ·  the tunnel is not running, so an agent outside the server cannot connect. Ask Mathys.')[0], ephemeral=True)
    token = tokens.issue(i.user.id)
    url = f'{base}/mcp'
    blocks = [f'**Address**\n`{url}`', f'**Your token** (shown once, a new `/mcp setup` replaces it)\n||`{token}`||',
              f'**Claude Code**\n```\nclaude mcp add --transport http codecel {url} --header "Authorization: Bearer {token}"\n```',
              '**Other agents**: add a remote MCP server with that address and the header `Authorization: Bearer <token>`.',
              '**It can**: list your games, list bugs and suggestions, read one in full. It cannot change anything yet.']
    view, files = card('🔌 Connect your AI agent', blocks, ['/mcp revoke · stop the token'], right=None)
    await i.response.send_message(view=view, files=files, ephemeral=True)
