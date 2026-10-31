import { ctx } from './ctx.js';
import { cfg } from './env.js';

export const STATUS_TAG = {
  needs_info: 'Needs Info', investigating: 'Investigating', fixing: 'Fix in Progress',
  fixed: 'Fixed', duplicate: 'Duplicate', not_a_bug: 'Not a Bug',
};
const DEVICES = ['Mobile', 'Computer', 'Controller'];
let tags = [];

export async function loadTags() {
  const f = await ctx.client.channels.fetch(cfg.bugsId);
  tags = f.availableTags;
}

const byName = (n) => tags.find((t) => t.name.toLowerCase() === String(n).toLowerCase());
export const tagName = (id) => tags.find((t) => t.id === id)?.name;
export const gameTags = () => tags.filter((t) => !t.moderated && !DEVICES.includes(t.name));
export const deviceTags = () => tags.filter((t) => DEVICES.includes(t.name));
export const statusTagIds = () => Object.values(STATUS_TAG).map((n) => byName(n)?.id).filter(Boolean);
export const findGameTag = (name) => gameTags().find((t) => t.name.toLowerCase() === String(name || '').toLowerCase());
export const findDeviceTag = (name) => deviceTags().find((t) => t.name.toLowerCase() === String(name || '').toLowerCase());

export function threadGameTag(thread) {
  return gameTags().find((t) => thread.appliedTags.includes(t.id));
}

// status: a key of STATUS_TAG, or null to clear status tags. game/device: tag ids to ensure.
// status undefined = leave status tags alone. replaceGame = swap out other game tags for `game`.
export async function setTags(thread, { game, device, status, replaceGame = false }) {
  if (!thread.appliedTags) return; // tester threads live in a text channel and have no tags
  const ids = new Set(statusTagIds());
  let next = status === undefined ? [...thread.appliedTags] : thread.appliedTags.filter((id) => !ids.has(id));
  if (game && replaceGame) {
    const games = new Set(gameTags().map((t) => t.id));
    next = next.filter((id) => !games.has(id));
  }
  if (game && !next.includes(game)) next.push(game);
  if (device && !next.includes(device)) next.push(device);
  const st = status ? byName(STATUS_TAG[status])?.id : null;
  next = next.slice(0, st ? 4 : 5);
  if (st) next.push(st);
  if (JSON.stringify(next) === JSON.stringify(thread.appliedTags)) return;
  if (thread.archived) await thread.setArchived(false).catch(() => {});
  await thread.setAppliedTags(next).catch((e) => console.error('setAppliedTags', e.message));
}
