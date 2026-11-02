"""Bug hunting: reply to a message with `!bug` or `!improve` (optionally followed by the game) to report that message.
Devs and testers alike get a post in the bugs forum (or the improvements forum) in the name of the player who wrote the message.
The bot answers under the message and removes the `!bug` reply. Five false posts (marked Not a bug or Declined) and the command is taken away (bot/hunting.py)."""
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
    in_testing = bool(cfg.testing_id) and str(m.channel.id) == str(cfg.testing_id)
    from .hunting import blocked
    if level(member) != 'admin' and blocked(member.id) and str(m.channel.id) != str(cfg.test_id):
        await _say(m, f"{E['warn']} Bug hunting is switched off for you for now. An admin will talk to you about it.")
        return True
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
    if str(m.channel.id) == str(cfg.test_id):  # a dry run in the test channel: draw the card, save and post nothing
        from .forms import card_from_message
        where = 'the bugs forum' if kind == 'bug' else 'the improvements forum'
        await m.channel.send(f"🧪 **TEST**{EM}·{EM}bug hunting would post this in {where} for <@{src.author.id}> (game: {game['name'] if game else 'not found'}). Nothing was saved or posted.",
                             embeds=[card_from_message(src, member, kind, game['id'] if game else None)], allowed_mentions=NO_MENTIONS)
        await _remove(m)
        return True
    if in_testing and kind == 'bug':  # the testing channel: the report goes to the testers' forum, tagged with the game (made when it is missing)
        from .tester import known_games, report_from_message, resolve_game
        name, tag_id = resolve_game(typed.strip())
        if not name and not typed.strip():
            try:
                a = await interpret_note(text, text.splitlines()[0][:100] if text else '', '', known_games())
                name, tag_id = resolve_game(a.get('game'))
            except Exception as e:
                print('guess game', repr(e))
        if not name:
            await _say(m, f"{E['warn']} Which game is it? Reply again with `!bug <game>`.")
            return True
        done = await report_from_message(src, member, name, tag_id)
        if not done:
            await _say(m, f"{E['warn']} I could not find the testers forum. Ask a developer.")
            return True
        id_, thread = done
        await _say(m, f"{E['fixed']} **SAVED**{EM}·{EM}bug #{id_} is in the testers forum: {thread.jump_url}", keep=True)
        await _remove(m)
        return True
    # the original text is copied into a forum everyone can read: never from a private channel (the testing channel is where testers work, so it is fine)
    private = not src.channel.permissions_for(m.guild.default_role).view_channel
    if private and str(getattr(src.channel, 'parent_id', None) or src.channel.id) != str(cfg.testing_id):
        await _say(m, f"{E['warn']} That channel is private, so I will not copy it into a public forum. Use `/bug` and write it yourself.")
        return True
    from .forms import post_from_message
    done = await post_from_message(src, member, kind, game['id'] if game else None)
    if not done:
        await _say(m, f"{E['warn']} I could not find the forum. Ask a developer.")
        return True
    id_, thread = done
    where = 'the bugs forum' if kind == 'bug' else 'the improvements forum'
    noun = 'bug' if kind == 'bug' else 'improvement'
    await _say(m, f"{E['fixed']} **SAVED**{EM}·{EM}{noun} #{id_} is in {where}: {thread.jump_url}", keep=True)
    await _remove(m)
    return True
