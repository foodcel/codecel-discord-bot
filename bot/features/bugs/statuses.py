"""Every status a bug or suggestion can have, in one place. Code may only use these words (tests/ check it).
A report goes new -> (needs_info) -> investigating / fixing -> fixed, or ends as duplicate, not_a_bug, declined, closed or removed.
Exploits have their own track (exploit, exploit_investigating, exploit_fixed, exploit_closed) and never show in public."""
NEW, NEEDS_INFO, INVESTIGATING, FIXING, FIXED = 'new', 'needs_info', 'investigating', 'fixing', 'fixed'
DUPLICATE, NOT_A_BUG, DECLINED, CLOSED, REMOVED = 'duplicate', 'not_a_bug', 'declined', 'closed', 'removed'
EXPLOIT, EXPLOIT_INVESTIGATING, EXPLOIT_FIXED, EXPLOIT_CLOSED = 'exploit', 'exploit_investigating', 'exploit_fixed', 'exploit_closed'

OPEN = (NEW, NEEDS_INFO, INVESTIGATING, FIXING)
DONE = (FIXED, DUPLICATE, NOT_A_BUG, DECLINED, CLOSED, REMOVED)
EXPLOITS = (EXPLOIT, EXPLOIT_INVESTIGATING, EXPLOIT_FIXED, EXPLOIT_CLOSED)
ALL = OPEN + DONE + EXPLOITS
