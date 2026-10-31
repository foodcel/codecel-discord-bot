"""Dev commands typed in chat: "1 fixed", "bug 3 fixed", "1-5 bugs fixed", "7 not a bug", "fixed 3", "1, 3 and 5 investigating"."""
import re

_KEYS = [
    (re.compile(r'\bdeclined?\b|\brejected\b|\bwont\s*add\b'), 'declined'),
    (re.compile(r'\bnot\s+a\s+bug\b|\bintended\b'), 'not_a_bug'),
    (re.compile(r'\bin\s+progress\b|\bfixing\b|\bwip\b'), 'fixing'),
    (re.compile(r'\binvestigating\b|\blooking\b'), 'investigating'),
    (re.compile(r'\bduplicate\b|\bdupe\b'), 'duplicate'),
    (re.compile(r'\breopen(?:ed)?\b'), 'new'),
    (re.compile(r'\bfixed\b|\bresolved\b|\bdone\b|\badded\b|\bimplemented\b'), 'fixed'),
]


def parse_command(text):
    """Returns {'status': ..., 'ids': [...]} or None when the text is not a command."""
    t = (text or '').lower().strip()
    if not t or len(t) > 80:
        return None
    status = None
    for rx, s in _KEYS:
        if rx.search(t):
            status = s
            t = rx.sub(' ', t, count=1)
            break
    if not status:
        return None
    t = re.sub(r'\bbugs?\b|\bsuggestions?\b|#|[.!:]', ' ', t)
    t = re.sub(r'\s*(?:-|–|—|\bto\b|\bthrough\b)\s*', '-', t)
    t = re.sub(r'\band\b|&|,', ' ', t)
    ids = []
    for p in [x for x in t.strip().split() if x]:
        if re.fullmatch(r'\d+', p):
            ids.append(int(p))
        else:
            m = re.fullmatch(r'(\d+)-(\d+)', p)
            if not m:
                return None
            a, b = int(m.group(1)), int(m.group(2))
            if b < a:
                a, b = b, a
            if b - a > 100:
                return None
            ids.extend(range(a, b + 1))
    return {'status': status, 'ids': list(dict.fromkeys(ids))}
