import { cfg } from './env.js';
import { ctx } from './ctx.js';
import { getGame } from './db.js';

// Claims read from the pinned "Claimed games" embed on the bounty-board. Read only.
let claims = []; // { name, owners: [userId], since: 'YYYY-MM-DD', votes }
export const getClaims = () => claims;

export function parseClaims(embed) {
  const out = [];
  for (const line of (embed.description || '').split('\n')) {
    const owners = [...line.matchAll(/<@!?(\d+)>/g)].map((m) => m[1]);
    if (!owners.length) continue;
    const named = line.match(/^\[(.+?)\]\(/) || line.match(/^\*\*(.+?)\*\*/);
    if (!named) continue;
    out.push({
      name: named[1], owners: [...new Set(owners)],
      since: line.match(/since (\d{4}-\d{2}-\d{2})/)?.[1] ?? null,
      votes: Number(line.match(/(\d+) votes?/)?.[1] ?? 0),
    });
  }
  return out;
}

// Returns true when the claim list changed.
export async function refreshClaims() {
  if (!cfg.bountyId) return false; // optional feature, owners can also be set with /config
  const ch = await ctx.client.channels.fetch(cfg.bountyId).catch(() => null);
  if (!ch) return false;
  const msgs = await ch.messages.fetch({ limit: 50 }).catch(() => null);
  if (!msgs) return false;
  const found = [];
  for (const m of msgs.values()) {
    if (!m.author.bot) continue;
    for (const e of m.embeds) if (/claimed/i.test(e.title || '')) found.push(...parseClaims(e));
  }
  if (!found.length) return false;
  const changed = JSON.stringify(found) !== JSON.stringify(claims);
  claims = found;
  return changed;
}

const STOP = new Set(['all', 'the', 'a', 'an', 'of', 'game', 'games', 'please', 'make', 'you', 'should',
  'we', 'need', 'bro', 'i', 'want', 'to', 'and', 'for', 'custom', 'roblox']);
// "x_blocks" must match "X-Block 360": underscores/dashes are separators, plurals are stemmed.
const stem = (t) => (t.length > 3 && t.endsWith('s') ? t.slice(0, -1) : t);
const toks = (s) => s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter((t) => t && !STOP.has(t)).map(stem);
const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '');

export function matchClaims(gameName) {
  const g = toks(gameName || '');
  if (!g.length) return [];
  const gn = norm(gameName);
  let best = 0;
  let hits = [];
  for (const c of claims) {
    const ct = new Set(toks(c.name));
    const cn = norm(c.name);
    // Same letters with different spacing/plurals ("OneShot" / "One shot", "parappa" / "Parappa 2") count as a full match.
    const contained = gn.length >= 4 && cn.length >= 4 && (cn.includes(gn) || gn.includes(cn));
    const score = contained ? g.length + 1 : g.filter((t) => ct.has(t)).length;
    if (score / g.length < 0.5) continue;
    if (score > best) { best = score; hits = [c]; } else if (score === best && score > 0) hits.push(c);
  }
  return hits;
}

// Owner override (/config) > confirmed board name > auto match.
export function ownersFor(tagId, gameName) {
  const row = tagId ? getGame(tagId) : null;
  if (row?.owner_override) return row.owner_override.split(',').filter(Boolean);
  let hits = [];
  if (row?.board_name) hits = claims.filter((c) => norm(c.name) === norm(row.board_name));
  if (!hits.length) hits = matchClaims(gameName);
  return [...new Set(hits.flatMap((c) => c.owners))];
}

export function boardNameFor(tagId, gameName) {
  const row = tagId ? getGame(tagId) : null;
  if (row?.board_name) return row.board_name;
  return matchClaims(gameName).map((c) => c.name).join(', ') || null;
}
