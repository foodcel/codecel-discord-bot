"""Three looks for the dev announcement, shown in the test channel (no pings). Clears the channel first.   python scripts/mockup_news.py --yes"""
import asyncio
import sys

import discord
from discord import ui

from _boot import boot, finish

from bot.cards import BLUE
from bot.ctx import fetch_channel
from bot.env import cfg
from bot.ui import flat

DEV_ROLE = 1562719404473458778
NONE = discord.AllowedMentions.none()


def url(channel_id):
    return f'https://discord.com/channels/{cfg.guild_id}/{channel_id}'


def items():
    """(emoji, title, text, link or None)"""
    return [
        ('🧪', 'Testing', '`/progress testing:on` shows 🧪 on the board and lists your game in the testing board. Released games too.', url(cfg.future_games_id)),
        ('🏷️', 'Testers forum', 'Testers report there. The game gets its tag when testing starts.', url(cfg.tester_forum_id)),
        ('👀', 'Previews', '`/release new`, `quiet` and `edit` show a preview first. Post, edit or cancel.', None),
        ('💬', 'Description', '`description:` adds a line under your game, like "Multiplayer + VC".', None),
        ('📚', 'Library', 'A new game is a card for 3 days, then joins the library.', url(1562940878685872149)),
        ('🔴', 'Offline', 'Taken-down games are marked offline for you, and you get pinged.', url(1565918318664093766)),
        ('🧾', 'Updates', '`/update` drafts look exactly like the posted card.', None),
    ]


def mock_a():
    """A · Grid: an embed with the features as small tiles, three to a row."""
    e = flat()
    e.title = '🆕  What\'s new'
    e.description = 'Testing, previews and a few smaller things.\n​'
    for emoji, title, text, _ in items():
        e.add_field(name=f'{emoji}  {title}', value=text, inline=True)
    e.set_footer(text='Type /help to see every command you can use.')
    return {'content': f'<@&{DEV_ROLE}>', 'embeds': [e]}


def mock_b():
    """B · Release notes: one card like the update cards. Big title, features as short headed blocks, buttons to the places."""
    c = [ui.TextDisplay(f'<@&{DEV_ROLE}>'),
         ui.TextDisplay('-# 🆕 WHAT\'S NEW\n# Testing and previews\n-# Nov 2, 2026'),
         ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large)]
    for n, (emoji, title, text, _) in enumerate(items()):
        c.append(ui.TextDisplay(f'### {emoji} {title}\n{text}'))
    c += [ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large),
          ui.TextDisplay('-# Type /help to see every command you can use.'),
          ui.ActionRow(ui.Button(style=discord.ButtonStyle.link, label='Testing board', url=url(cfg.future_games_id), emoji='🧪'),
                       ui.Button(style=discord.ButtonStyle.link, label='Testers forum', url=url(cfg.tester_forum_id), emoji='🏷️'),
                       ui.Button(style=discord.ButtonStyle.link, label='Games', url=url(1562940878685872149), emoji='🎮'))]
    view = ui.LayoutView()
    view.add_item(ui.Container(*c, accent_colour=BLUE))
    return {'view': view}


def mock_c():
    """C · Rows: every feature is a row with its own Open button on the right, so it is clear what to read and where to press."""
    c = [ui.TextDisplay(f'<@&{DEV_ROLE}>'),
         ui.TextDisplay('# 🆕 What\'s new\n-# Testing, previews and a few smaller things'),
         ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)]
    for emoji, title, text, link in items():
        body = f'**{emoji} {title}**\n{text}'
        if link:
            c.append(ui.Section(body, accessory=ui.Button(style=discord.ButtonStyle.link, label='Open', url=link)))
        else:
            c.append(ui.TextDisplay(body))
    c += [ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
          ui.TextDisplay('-# Type /help to see every command you can use.')]
    view = ui.LayoutView()
    view.add_item(ui.Container(*c))
    return {'view': view}


async def main():
    client = await boot()
    if '--yes' not in sys.argv:
        print('Not posting. Pass --yes.')
        return await finish(client)
    ch = await fetch_channel(cfg.test_id)
    await ch.purge(limit=None, bulk=True, reason='Mockups')
    for label, make in (('**A · Tiles**', mock_a), ('**B · Release notes**', mock_b), ('**C · Rows with buttons**', mock_c)):
        await ch.send(label, allowed_mentions=NONE)
        await ch.send(allowed_mentions=NONE, **make())
    print('done')
    await finish(client)


asyncio.run(main())
