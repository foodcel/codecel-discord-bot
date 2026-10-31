"""Settings from .env (same keys as the JavaScript version)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
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
    tester_info_id = _e.get('TESTER_INFO_CHANNEL_ID') or None          # optional: the channel whose roster message the tester list is taken from
    updates_role = _e.get('UPDATES_PING_ROLE_ID') or None              # optional: the role an update announcement can ping
    devlog_id = _e.get('DEV_LOG_CHANNEL_ID') or None                   # optional: every dev action is logged here
    suggestions_id = _e.get('SUGGESTIONS_CHANNEL_ID') or None          # optional: forum where players suggest improvements
    dev_suggestions_id = _e.get('DEV_SUGGESTIONS_FORUM_ID') or None    # optional: dev-only forum, a board post per dev
    tester_roles = [r for r in (_e.get('TESTER_ROLE_IDS') or '').split(',') if r]
    model = _e.get('MODEL') or 'claude-haiku-4-5-20251001'
    ai_daily_cap = int(_e.get('AI_DAILY_CAP') or 500)


cfg = Cfg()
