"""Settings from .env (same keys as the JavaScript version)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]  # bot/core/env.py -> the repo
load_dotenv(ROOT / '.env')

_need = ['DISCORD_TOKEN', 'APPLICATION_ID', 'ANTHROPIC_API_KEY', 'GUILD_ID', 'BUGS_CHANNEL_ID',
         'DEV_BUGS_FORUM_ID', 'MODLOG_CHANNEL_ID', 'DEV_ROLE_ID']
for _k in _need:
    if not os.environ.get(_k):
        raise RuntimeError(f'Missing {_k} in .env')

_e = os.environ


class Cfg:
    token = _e['DISCORD_TOKEN']
    app_id = _e['APPLICATION_ID']
    anthropic_key = _e['ANTHROPIC_API_KEY']
    guild_id = _e['GUILD_ID']
    bugs_id = _e['BUGS_CHANNEL_ID']
    dev_forum_id = _e['DEV_BUGS_FORUM_ID']
    modlog_id = _e['MODLOG_CHANNEL_ID']
    dev_role = _e['DEV_ROLE_ID']
    jr_role = _e.get('JR_DEV_ROLE_ID') or None            # optional
    bounty_id = _e.get('BOUNTY_BOARD_CHANNEL_ID') or None  # optional: a channel whose embed lists who owns which game
    test_id = _e.get('TEST_CHANNEL_ID') or None
    updates_id = _e.get('UPDATES_CHANNEL_ID') or None
    testing_id = _e.get('TESTING_CHANNEL_ID') or None
    verified_role = _e.get('VERIFIED_ROLE_ID') or '1562762634565124186'  # the role people get when they verify: an invite only counts for the inviter once the invited person has it
    owner_id = _e.get('OWNER_ID') or None  # pinged when bug hunting is switched off for someone
    helpers_role = _e.get('HELPERS_ROLE_ID') or '1565120384519381052'  # helpers can volunteer as testers too
    tester_ping_role = _e.get('TESTER_PING_ROLE_ID') or '1562726451797565521'  # the Tester role: pinged when a game goes into testing
    future_games_id = _e.get('FUTURE_GAMES_CHANNEL_ID') or '1562728247131635742'  # private channel where the board of games in testing lives
    tester_forum_id = _e.get('TESTER_FORUM_ID') or '1566668851083612330'  # the forum in the Testers category where every tester report becomes a post
    tester_info_id = _e.get('TESTER_INFO_CHANNEL_ID') or None          # optional: the channel whose roster message the tester list is taken from
    releases_role = _e.get('RELEASES_ROLE_ID') or None                 # optional: a role a new-game card can ping (/release new ping:)
    updates_role = _e.get('UPDATES_PING_ROLE_ID') or None              # optional: the role an update announcement can ping
    devlog_id = _e.get('DEV_LOG_CHANNEL_ID') or None                   # optional: every dev action is logged here
    suggestions_id = _e.get('SUGGESTIONS_CHANNEL_ID') or None          # optional: forum where players suggest improvements
    dev_suggestions_id = _e.get('DEV_SUGGESTIONS_FORUM_ID') or None    # optional: dev-only forum, a board post per dev
    dev_chat_id = _e.get('DEV_CHAT_CHANNEL_ID') or '1565918318664093766'          # #developer-chat: game-down alerts, testing notes
    games_channel_id = _e.get('GAMES_CHANNEL_ID') or '1562940878685872149'         # #games: the game library
    commands_channel_id = _e.get('COMMANDS_CHANNEL_ID') or '1563090099774816286'   # where players can use commands
    game_ideas_id = _e.get('GAME_IDEAS_CHANNEL_ID') or '1562961976387174452'       # whole new game ideas
    mog_ping = [u for u in (_e.get('MOG_PING_USER_IDS') or '941724517481463888,1565900080894967809').split(',') if u]  # /mog pings these (Robin, Redwing Helper)
    tester_roles = [r for r in (_e.get('TESTER_ROLE_IDS') or '').split(',') if r]
    model = _e.get('MODEL') or 'claude-haiku-4-5-20251001'
    ai_daily_cap = int(_e.get('AI_DAILY_CAP') or 500)


cfg = Cfg()
