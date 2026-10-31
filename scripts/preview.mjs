// Usage: node scripts/preview.mjs [all|bug|board|announcement|rules|messages|transcript]
// Logs in as the bot (a second session, safe while the bot runs) and posts previews to TEST_CHANNEL_ID.
import { Client, GatewayIntentBits as I } from 'discord.js';
import { cfg } from '../src/env.js';
import { ctx } from '../src/ctx.js';
import { loadTags } from '../src/tags.js';
import { refreshClaims } from '../src/bounty.js';
import { postPreviews } from '../src/previews.js';

const client = new Client({ intents: [I.Guilds] });
ctx.client = client;
await client.login(cfg.token);
await new Promise((r) => (client.isReady() ? r() : client.once('clientReady', r)));
ctx.guild = await client.guilds.fetch(cfg.guildId);
await loadTags();
await refreshClaims();
const n = await postPreviews(process.argv[2] || 'all');
console.log(`posted ${n} preview message(s)`);
await client.destroy();
process.exit(0);
