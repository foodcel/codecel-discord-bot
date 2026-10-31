import { cfg } from './env.js';

export const ctx = { client: null, guild: null };

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const fetchChannel = (id) => (id ? ctx.client.channels.fetch(id).catch(() => null) : Promise.resolve(null));
export const threadLink = (id) => `https://discord.com/channels/${cfg.guildId}/${id}`;

export async function modlog(payload) {
  const ch = await fetchChannel(cfg.modlogId);
  return ch?.send(payload).catch((e) => console.error('modlog send failed:', e.message));
}

export const dm = (userId, content) =>
  ctx.client.users.fetch(userId).then((u) => u.send(content)).then(() => true).catch(() => false);

export const getMember = (id) => ctx.guild.members.fetch(id).catch(() => null);
