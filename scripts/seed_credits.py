"""One-off: gives the games released before /release new their original studio and proper titles (taken from the old #games library).
Only fills what is empty. Run on the VM (the real database lives there)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.db import all_, run  # noqa: E402
from bot.games import key  # noqa: E402

# key of the name on the board -> (title, studio)
DATA = {
    'peggle': ('Peggle Deluxe', 'PopCap Games'),
    'superhot': ('SUPERHOT', 'SUPERHOT Team'),
    'clustertruck': ('Clustertruck', 'Landfall Games'),
    'simpsonshitrun': ('The Simpsons: Hit & Run', 'Radical Entertainment · Vivendi Universal Games / Fox Interactive'),
    'oneshot': ('OneShot', 'Future Cat / Degica'),
    'gangbeasts': ('Gang Beasts', 'Boneloaf'),
    'youshouldmakedeltaruneplease': ('Deltarune', 'Toby Fox'),
}

for r in all_("SELECT * FROM game_status WHERE status='released'"):
    got = DATA.get(key(r['name']))
    if not got:
        print('skipped', r['name'])
        continue
    title, studio = got
    run('UPDATE game_status SET title=COALESCE(title, ?), studio=COALESCE(studio, ?) WHERE key=?', title, studio, r['key'])
    print('filled', r['name'], '->', title, '|', studio)
