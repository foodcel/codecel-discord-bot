// Checks /release and /unrelease against the live bounty-board with a fake admin, then puts everything back.
import { Client, GatewayIntentBits as I } from 'discord.js';
import { cfg } from '../src/env.js';
import { ctx } from '../src/ctx.js';
import { db } from '../src/db.js';
import { loadTags } from '../src/tags.js';
import { refreshClaims, getClaims } from '../src/bounty.js';
import { commandRelease, gameLists } from '../src/games.js';

const client = new Client({ intents: [I.Guilds] });
ctx.client = client;
await client.login(cfg.token);
await new Promise((r) => (client.isReady() ? r() : client.once('clientReady', r)));
ctx.guild = await client.guilds.fetch(cfg.guildId);
await loadTags(); await refreshClaims();
const admin = { id: 'x', permissions: { has: () => true }, roles: { cache: { has: () => false } } };
const call = async (undo, game, link) => {
  let out;
  await commandRelease({ options: { getString: (n) => (n === 'game' ? game : link ?? null) }, member: admin, user: { id: 'x' }, reply: async (r) => { out = r.content; } }, undo);
  return out;
};
const before = gameLists();
console.log('claims read:', getClaims().length, '| unreleased:', before.unreleased.length, '| released:', before.released.length);
const name = getClaims()[0].name;
console.log('release   ->', await call(false, name, 'https://example.com/play'));
let l = gameLists();
console.log('  now unreleased', l.unreleased.length, '| released', l.released.length, '| released row:', l.released.map((r) => `${r.name} ${r.link}`).join(','));
console.log('unrelease ->', await call(true, name));
l = gameLists();
console.log('  now unreleased', l.unreleased.length, '| released', l.released.length);
db.prepare('DELETE FROM game_status').run();
console.log('cleaned up');
await client.destroy(); process.exit(0);
