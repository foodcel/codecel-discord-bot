import { cfg } from './env.js';
import { ctx } from './ctx.js';

const IMG = /^image\/(png|jpe?g|gif|webp)/;
const VIDEO_LINK = /https?:\/\/(?:www\.)?(?:youtube\.com|youtu\.be|streamable\.com|medal\.tv|clips\.twitch\.tv|twitch\.tv|vimeo\.com|tiktok\.com|gyazo\.com|imgur\.com)\/\S+/gi;
const MAX_IMG_BYTES = 8 * 1024 * 1024;
const jump = (threadId, msgId) => `https://discord.com/channels/${cfg.guildId}/${threadId}/${msgId}`;

// For the bug view: fresh attachment URLs straight from the live thread (no downloads). Cached for a minute.
const liveCache = new Map();
export async function liveMedia(thread, bug) {
  const hit = liveCache.get(bug.id);
  if (hit && Date.now() - hit.t < 60000) return hit.v;
  const msgs = await thread.messages.fetch({ limit: 50 }).catch(() => null);
  const mine = [...(msgs?.values() ?? [])].filter((m) => m.author.id === bug.reporter_id || (bug.source === 'tester' && m.author.id === ctx.client.user.id))
    .sort((a, b) => a.createdTimestamp - b.createdTimestamp);
  const images = [];
  const videos = [];
  for (const m of mine) {
    for (const a of m.attachments.values()) {
      const type = a.contentType || '';
      if (IMG.test(type) && images.length < 4) images.push(a.url);
      else if (type.startsWith('video/') || IMG.test(type)) videos.push({ label: `${type.startsWith('video/') ? '🎥' : '🖼️'} ${a.name}`, url: jump(thread.id, m.id) });
    }
    for (const link of m.content.match(VIDEO_LINK) ?? []) videos.push({ label: `🎥 ${link.slice(0, 60)}`, url: link });
  }
  const v = { text: bug.source === 'tester' ? (bug.body || '') : (mine[0]?.content ?? ''), images, videos };
  liveCache.set(bug.id, { t: Date.now(), v });
  return v;
}

// Everything the reporter posted in their thread: text, screenshots (downloaded so they never expire), videos (links).
export async function collectMedia(thread, bug) {
  const msgs = await thread.messages.fetch({ limit: 50 }).catch(() => null);
  const mine = [...(msgs?.values() ?? [])].filter((m) => m.author.id === bug.reporter_id)
    .sort((a, b) => a.createdTimestamp - b.createdTimestamp);
  const files = [];
  const videos = [];
  let used = 0;
  for (const m of mine) {
    for (const a of m.attachments.values()) {
      const type = a.contentType || '';
      if (IMG.test(type)) {
        if (files.length >= 4 || a.size > MAX_IMG_BYTES || used + a.size > 20 * 1024 * 1024) {
          videos.push({ label: `🖼️ ${a.name}`, url: jump(thread.id, m.id) });
          continue;
        }
        try {
          const r = await fetch(a.url);
          const buffer = Buffer.from(await r.arrayBuffer());
          const ext = (a.name.match(/\.(\w{2,4})$/) || [, 'png'])[1];
          files.push({ name: `bug${bug.id}-${files.length + 1}.${ext}`, buffer });
          used += buffer.length;
        } catch { videos.push({ label: `🖼️ ${a.name}`, url: jump(thread.id, m.id) }); }
      } else if (type.startsWith('video/')) {
        videos.push({ label: `🎥 ${a.name}`, url: jump(thread.id, m.id) });
      }
    }
    for (const link of m.content.match(VIDEO_LINK) ?? []) videos.push({ label: `🎥 ${link.slice(0, 60)}`, url: link });
  }
  return { text: mine[0]?.content ?? '', files, videos };
}
