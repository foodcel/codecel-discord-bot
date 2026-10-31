// "1 fixed", "bug 3 fixed", "1-5 bugs fixed", "7 not a bug", "fixed 3", "1, 3 and 5 investigating"
const KEYS = [
  [/\bnot\s+a\s+bug\b|\bintended\b/, 'not_a_bug'],
  [/\bin\s+progress\b|\bfixing\b|\bwip\b/, 'fixing'],
  [/\binvestigating\b|\blooking\b/, 'investigating'],
  [/\bduplicate\b|\bdupe\b/, 'duplicate'],
  [/\breopen(?:ed)?\b/, 'new'],
  [/\bfixed\b|\bresolved\b|\bdone\b/, 'fixed'],
];

export function parseCommand(text) {
  let t = (text || '').toLowerCase().trim();
  if (!t || t.length > 80) return null;
  let status = null;
  for (const [re, s] of KEYS) {
    if (re.test(t)) { status = s; t = t.replace(re, ' '); break; }
  }
  if (!status) return null;
  t = t.replace(/\bbugs?\b|#|[.!:]/g, ' ')
    .replace(/\s*(?:-|–|—|\bto\b|\bthrough\b)\s*/g, '-')
    .replace(/\band\b|&|,/g, ' ');
  const ids = [];
  for (const p of t.trim().split(/\s+/).filter(Boolean)) {
    let m;
    if (/^\d+$/.test(p)) ids.push(+p);
    else if ((m = p.match(/^(\d+)-(\d+)$/))) {
      let a = +m[1], b = +m[2];
      if (b < a) [a, b] = [b, a];
      if (b - a > 100) return null;
      for (let i = a; i <= b; i++) ids.push(i);
    } else return null;
  }
  return { status, ids: [...new Set(ids)] };
}
