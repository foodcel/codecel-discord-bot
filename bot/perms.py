"""Who may do what. Checked on the server for every click and command."""
from .env import cfg


def _has_role(m, role_id):
    return any(str(r.id) == str(role_id) for r in m.roles)


def level(m):
    """'admin' | 'jr' | 'dev' | 'none'. Jr wins over dev when someone has both roles."""
    if not m:
        return 'none'
    if m.guild_permissions.administrator:
        return 'admin'
    if cfg.jr_role and _has_role(m, cfg.jr_role):
        return 'jr'
    if _has_role(m, cfg.dev_role):
        return 'dev'
    return 'none'


def is_staff(m):
    """Staff are never struck by the troll ladder."""
    if not m:
        return False
    p = m.guild_permissions
    return bool(m.bot or level(m) != 'none' or m.id == m.guild.owner_id
                or p.moderate_members or p.kick_members or p.ban_members or p.manage_messages)


def can_manage(m, owners):
    """Status commands, /update, /config for a game: admin, or a dev who owns it. Unclaimed = any dev."""
    lv = level(m)
    if lv == 'admin':
        return True
    if lv != 'dev':
        return False
    return len(owners) == 0 or str(m.id) in [str(o) for o in owners]


def can_confirm(m):
    return level(m) in ('admin', 'dev')
