import { Client, Events, GatewayIntentBits as I, Partials } from 'discord.js';
import { cfg } from './env.js';
import { ctx, sleep } from './ctx.js';
import { db, kvGet, kvSet } from './db.js';
import { loadTags } from './tags.js';
import { refreshClaims } from './bounty.js';
import { clearBugMessages, refreshAllBoards, scheduleBoards } from './devboard.js';
import { backfillSnapshots } from './fixlog.js';
import { intakeThread } from './intake.js';
import { handleMessage } from './router.js';
import { runTimers } from './timers.js';
import { catchup } from './catchup.js';
import { commandDefs, handleInteraction } from './interactions.js';

const client = new Client({
  intents: [I.Guilds, I.GuildMessages, I.MessageContent, I.GuildMembers, I.GuildMessageReactions],
  partials: [Partials.Channel, Partials.Message, Partials.Reaction],
});
ctx.client = client;

process.on('unhandledRejection', (e) => console.error('unhandledRejection', e));

let claimTimer = null;
const scheduleClaims = () => {
  clearTimeout(claimTimer);
  claimTimer = setTimeout(async () => {
    if (await refreshClaims().catch(() => false)) scheduleBoards();
  }, 3000);
};

client.once(Events.ClientReady, async (c) => {
  ctx.guild = await c.guilds.fetch(cfg.guildId);
  console.log(`Logged in as ${c.user.tag}`);
  await loadTags();
  await ctx.guild.commands.set(commandDefs.map((d) => d.toJSON()));
  await refreshClaims();
  await catchup().catch((e) => console.error('catchup failed', e));
  if (!kvGet('board_v3')) { // one-time: remove the per-bug messages the old layout posted
    await clearBugMessages().catch((e) => console.error('clear failed', e));
    kvSet('board_v3', '1');
  }
  if (!kvGet('threshold_3')) { // announcement offers now start at 3 fixes
    db.prepare('UPDATE games SET threshold=3 WHERE threshold=5').run();
    kvSet('threshold_3', '1');
  }
  await backfillSnapshots().catch(console.error); // transcripts for bugs fixed before the log existed
  await refreshAllBoards().catch(console.error); // claims may have changed while offline (also creates/refreshes the fix log post)
  setInterval(() => runTimers().catch(console.error), 60000);
  console.log('Ready. Catch-up finished.');
});

client.on(Events.ThreadCreate, async (thread, newlyCreated) => {
  if (thread.parentId !== cfg.bugsId || !newlyCreated || !ctx.guild) return;
  await sleep(1500);
  intakeThread(thread).catch(console.error);
});

client.on(Events.MessageCreate, (m) => {
  if (m.channelId === cfg.bountyId) return scheduleClaims();
  handleMessage(m).catch(console.error);
});
client.on(Events.MessageUpdate, (_o, m) => { if (m.channelId === cfg.bountyId) scheduleClaims(); });
client.on(Events.ChannelUpdate, (_o, ch) => { if (ch.id === cfg.bugsId) loadTags().catch(console.error); });

client.on(Events.InteractionCreate, (i) =>
  handleInteraction(i).catch((e) => {
    console.error('interaction', e);
    if (i.isRepliable() && !i.replied && !i.deferred) i.reply({ content: 'Something went wrong.', flags: 64 }).catch(() => {});
  }));

client.login(cfg.token);
