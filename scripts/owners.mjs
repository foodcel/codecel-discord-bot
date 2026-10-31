// Prints which dev owns each #bugs game tag, using the live bounty-board.
import { Client, GatewayIntentBits as I } from 'discord.js';
import { cfg } from '../src/env.js';
import { ctx } from '../src/ctx.js';
import { loadTags, gameTags } from '../src/tags.js';
import { refreshClaims, getClaims, ownersFor, boardNameFor } from '../src/bounty.js';

const client = new Client({ intents: [I.Guilds] });
ctx.client = client;
await client.login(cfg.token);
await new Promise((r) => (client.isReady() ? r() : client.once('clientReady', r)));
ctx.guild = await client.guilds.fetch(cfg.guildId);
await loadTags();
await refreshClaims();
console.log(`claims read: ${getClaims().length}`);
for (const t of gameTags()) {
  const o = ownersFor(t.id, t.name);
  const names = [];
  for (const id of o) names.push((await ctx.guild.members.fetch(id).catch(() => null))?.displayName ?? id);
  console.log(`${t.name.padEnd(20)} -> ${names.join(', ') || 'UNCLAIMED'}   (board: ${boardNameFor(t.id, t.name) || '-'})`);
}
await client.destroy();
process.exit(0);
