// End-to-end check of /bug against the real server using a fake interaction. Uses an unclaimed game (no dev is pinged)
// and the bot itself as the "tester", then removes everything it created.
import { Client, GatewayIntentBits as I } from 'discord.js';
import { cfg } from '../src/env.js';
import { ctx, fetchChannel, removeThreadNotice } from '../src/ctx.js';
import { db, bugById, cancelTimers } from '../src/db.js';
import { loadTags, gameTags } from '../src/tags.js';
import { refreshClaims, ownersFor } from '../src/bounty.js';
import { modalBug } from '../src/tester.js';
import { bugEmbeds } from '../src/bugview.js';
import { singleTranscript } from '../src/transcript.js';
import { markFixed } from '../src/fixes.js';
import { refreshAllBoards, openBugsFor } from '../src/devboard.js';
import { unlink } from 'node:fs/promises';

const client = new Client({ intents: [I.Guilds, I.GuildMembers] });
ctx.client = client;
await client.login(cfg.token);
await new Promise((r) => (client.isReady() ? r() : client.once('clientReady', r)));
ctx.guild = await client.guilds.fetch(cfg.guildId);
await loadTags(); await refreshClaims();
const tag = gameTags().find((t) => ownersFor(t.id, t.name).length === 0);
console.log('unclaimed game used:', tag.name);
const form = { title: '[BOT TEST] Car falls through the map', what: 'After checkpoint 2 the car drops through the road', steps: '1. Start race\n2. Pass checkpoint 2', expected: 'Car stays on the road', device: 'PS5' };
const fake = {
  user: { id: client.user.id, tag: 'bot-test' }, deferReply: async () => {},
  fields: { getTextInputValue: (k) => form[k] ?? '' },
  editReply: async (x) => { console.log('REPLY TO TESTER:', x); },
};
await modalBug(fake, tag.id, 'none');
const bug = db.prepare("SELECT * FROM bugs WHERE source='tester' ORDER BY id DESC LIMIT 1").get();
console.log('bug row:', { id: bug.id, game: bug.game_name, title: bug.title, severity: bug.severity, device: bug.device, status: bug.status, routed: bug.routed });
const thread = await fetchChannel(bug.thread_id);
console.log('thread in #testing:', thread?.name, '| parent ok:', thread?.parentId === cfg.testingId);
const emb = (await bugEmbeds(bug))[0];
console.log('bug page device field:', emb.data.fields.find((f) => /DEVICE/.test(f.name))?.value.trim(), '| quote shown:', emb.data.description.includes('What happened'));
console.log('on unclaimed board:', openBugsFor('unclaimed').some((b) => b.id === bug.id));
const t = await singleTranscript(bug.id);
console.log('transcript has tester body:', t.files[0].attachment.toString().includes('Report as written by the tester'));
await markFixed(bug, client.user.id);
await new Promise((r) => setTimeout(r, 4000));
console.log('after fix, status:', bugById(bug.id).status, '| thread archived:', (await fetchChannel(bug.thread_id))?.archived);
// clean up
const th = await fetchChannel(bug.thread_id);
if (th) await removeThreadNotice(th);
await th?.delete('e2e test cleanup').catch(() => {});
cancelTimers('delete_thread', bug.thread_id);
db.prepare('DELETE FROM bugs WHERE id=?').run(bug.id);
for (const ext of ['zip', 'md']) await unlink(new URL(`../data/archive/bug-${bug.id}.${ext}`, import.meta.url)).catch(() => {});
await refreshAllBoards();
console.log('cleaned up. bug row left:', !!bugById(bug.id));
await client.destroy(); process.exit(0);
