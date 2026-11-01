"""One-off: registers the two restored new-game cards so the guard keeps them. Run on the VM."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.db import kv_set  # noqa: E402

DAY = 86400000
kv_set('library_cards', json.dumps([
    {'msg': '1566599642530189333', 'key': 'youshouldmakedeltarunepleas' if False else 'youshouldmakedeltaruneplease', 'leave_at': 1793511748084 + 3 * DAY},
    {'msg': '1566599643243220993', 'key': 'peggle', 'leave_at': 1793479248980 + 3 * DAY},
]))
print('cards registered')
