import { ChannelType, MessageType } from 'discord.js';
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

// A thread started inside a text channel leaves a "<bot> started a thread: ..." line behind, even after the thread is
// deleted. Call this before deleting the thread so that line goes away with it. Forum posts have no such line.
export async function removeThreadNotice(thread) {
  const parent = thread.parent;
  if (!parent || parent.type === ChannelType.GuildForum) return;
  const near = await parent.messages.fetch({ around: thread.id, limit: 50 }).catch(() => null);
  const notice = near?.find((m) => m.type === MessageType.ThreadCreated && m.reference?.channelId === thread.id);
  await notice?.delete().catch(() => {});
}
