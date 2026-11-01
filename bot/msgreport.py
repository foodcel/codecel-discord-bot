"""Reply to a message with `!bug` or `!improve` (optionally followed by the game) to report that message.
Devs get a post in the bugs forum (or the improvements forum); testers get a thread in the testing channel.
The bot answers under the message and removes the `!bug` reply."""
import re

import discord

from .ai import interpret_note
from .env import cfg
from .components import NO_MENTIONS
from .ctx import fetch_channel
from .perms import level
from .tags import find_game_tag, game_tags
from .ui import E, EM

COMMAND = re.compile(r'^!(bug|improve|improvement)\b\s*(.*)$', re.I | re.S)


def wants(m):
    return bool(m.reference) and bool(COMMAND.match((m.content or '').strip()))


async def _say(m, text, keep=False):
    sent = await m.channel.send(text, reference=m.reference if keep else None, allowed_mentions=NO_MENTIONS, delete_after=None if keep else 15,
                                mention_author=False)
    return sent


async def _remove(m):
    try:
        await m.delete()
    except Exception:
        pass


async def guess_game(text, typed):
    """The game tag: what was typed after the command, else a guess from the message text."""
    if typed:
        return find_game_tag(typed)
    try:
        a = await interpret_note(text, text.splitlines()[0][:100] if text else '', '', [t['name'] for t in game_tags()])
        return find_game_tag(a.get('game'))
    except Exception as e:
        print('guess game', repr(e))
        return None


async def handle(m):
    """True when the message was a report command (handled, or refused with a reason)."""
    if not wants(m) or m.author.bot or not m.guild:
        return False
    word, typed = COMMAND.match(m.content.strip()).groups()
    kind = 'bug' if word.lower() == 'bug' else 'suggestion'
    from .tester import is_tester
    member = m.author
    lv = level(member)
    if not is_tester(member):
        return False  # players use /bug and /improvement
    try:
        src = m.reference.resolved if isinstance(m.reference.resolved, discord.Message) else await m.channel.fetch_message(m.reference.message_id)
    except Exception:
        await _say(m, f"{E['warn']} I could not read the message you replied to.")
        return True
    from .forms import message_text
    text = message_text(src)
    if not text and not src.attachments:
        await _say(m, f"{E['warn']} That message has no text or files to report.")
        return True
    game = await guess_game(text, typed.strip())
    dev = lv in ('admin', 'dev')
    to_thread = kind == 'bug' and not dev
    if str(m.channel.id) == str(cfg.test_id):  # a dry run in the test channel: draw the card, save and post nothing
        from .forms import card_from_message
        where = 'a thread in the testing channel' if to_thread else ('the bugs forum' if kind == 'bug' else 'the improvements forum')
        await m.channel.send(f"🧪 **TEST**{EM}·{EM}this would go to {where} (game: {game['name'] if game else 'not found'}). Nothing was saved or posted.", embeds=[card_from_message(src, member, kind, game['id'] if game else None)], allowed_mentions=NO_MENTIONS)
        await _remove(m)
        return True
    # the original text is copied into a forum everyone can read: never from a private channel (a tester thread is private too)
    if not to_thread and not src.channel.permissions_for(m.guild.default_role).view_channel:
        await _say(m, f"{E['warn']} That channel is private, so I will not copy it into a public forum. Use `/bug` and write it yourself.")
        return True
    if to_thread:  # a tester: a thread in the testing channel, which needs the game
        if not game:
            await _say(m, f"{E['warn']} Which game is it? Reply again with `!bug <game>`.")
            return True
        from .tester import thread_from_message
        id_, thread = await thread_from_message(src, member, game['id'])
        where = 'the testing channel'
    else:
        from .forms import post_from_message
        done = await post_from_message(src, member, kind, game['id'] if game else None)
        if not done:
            await _say(m, f"{E['warn']} I could not find the forum. Ask a developer.")
            return True
        id_, thread = done
        where = 'the forum'
    noun = 'bug' if kind == 'bug' else 'improvement'
    await _say(m, f"{E['fixed']} **SAVED**{EM}·{EM}{noun} #{id_} is in {where}: {thread.jump_url}", keep=True)
    await _remove(m)
    return True
