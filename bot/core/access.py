"""Who may use which slash command: ONE table. The bot checks it before any command runs (and before an autocomplete list is shown),
scripts/lock_commands.py builds Discord's per-role rules from it, and tests/ check that /help agrees with it.
A command that is not listed is open to everyone (the command may still check more itself, like /tester's admin sub-commands)."""
from bot.core.perms import level

ADMIN, DEV, GIVEAWAY, EVERYONE = 'admin', 'dev', 'giveaway', 'everyone'

COMMANDS = {
    # admins only
    'mog': ADMIN, 'Mog': ADMIN, 'preview': ADMIN, 'botrules': ADMIN, 'games': ADMIN, 'bounty-board': ADMIN,
    'assign': ADMIN, 'exclude': ADMIN, 'include': ADMIN, 'strikes': ADMIN, 'pardon': ADMIN,
    # developers (and admins)
    'config': DEV, 'update': DEV, 'pings': DEV, 'release': DEV, 'progress': DEV, 'claim': DEV,
    # admins and the Giveaway Manager role
    'giveaway': GIVEAWAY,
}


def who(name):
    return COMMANDS.get(name, EVERYONE)


def allowed(member, name):
    need = who(name)
    if need == EVERYONE:
        return True
    lv = level(member)
    if need == ADMIN:
        return lv == 'admin'
    if need == DEV:
        return lv in ('admin', 'dev')
    from bot.features.giveaways.giveaway import can_run
    return can_run(member)


def names(need):
    return tuple(n for n, w in COMMANDS.items() if w == need)
