"""/mcp setup and /mcp revoke: a dev connects an AI agent (Claude Code, Codex, Pi...) to their games' reports."""
import os
import re
from pathlib import Path

from bot.discord_ui.card import card, notice
from bot.mcp import media, tokens
from bot.mcp.server import eligible

LOG = os.environ.get('MCP_TUNNEL_LOG') or str(Path.home() / 'cloudflared.log')
URL = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com')


async def command_mcp(i, sub):
    if not eligible(i.user):
        return await i.response.send_message(view=notice('⚠️ **Developers only**  ·  the MCP is for developers with the Developers role. Admins cannot connect it.')[0], ephemeral=True)
    if sub == 'revoke':
        done = tokens.revoke(i.user.id)
        return await i.response.send_message(view=notice('✅ **Revoked**  ·  your token no longer works.' if done else 'You have no active token.')[0], ephemeral=True)
    base = media.public_url()
    if not base:
        return await i.response.send_message(view=notice('⚠️ **Not reachable yet**  ·  the tunnel is not running, so an agent outside the server cannot connect. Ask foodcel.')[0], ephemeral=True)
    token = tokens.issue(i.user.id)
    url = f'{base}/mcp'
    blocks = [f'**Address**\n`{url}`', f'**Your token** (shown once, a new `/mcp setup` replaces it)\n||`{token}`||',
              f'**Claude Code**\n```\nclaude mcp add --transport http codecel {url} --header "Authorization: Bearer {token}"\n```',
              '**Other agents**: add a remote MCP server with that address and the header `Authorization: Bearer <token>`.',
              '**It can**: list your games, bugs and suggestions, search them, read a report and its full transcript with screenshots and video frames. It cannot change anything yet.']
    view, files = card('🔌 Connect your AI agent', blocks, ['/mcp revoke · stop the token'], right=None)
    await i.response.send_message(view=view, files=files, ephemeral=True)
