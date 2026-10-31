// Posts the bug bot launch announcement.
// Usage: node scripts/post-announcement.mjs --channel=<id> [--kind=bot|testers] [--ping | --role=<roleId>] --yes
// --kind=testers posts the /bug announcement for testers. --role pings only that role.
// ONLY run this after the user approved the text AND the channel. It refuses to run without --yes and --channel.
// --ping adds an @everyone ping (only members who can see that channel are notified).
import { Client, GatewayIntentBits as I } from 'discord.js';
import { cfg } from '../src/env.js';
import { botNewsEmbeds, testerNewsEmbeds } from '../src/botnews.js';

const arg = (name) => process.argv.find((a) => a.startsWith(`--${name}=`))?.split('=')[1];
const channelId = arg('channel');
if (!process.argv.includes('--yes') || !channelId) {
  console.log('Not posting. Pass --channel=<id> and --yes after the user approved the announcement and the channel.');
  process.exit(0);
}

const client = new Client({ intents: [I.Guilds] });
await client.login(cfg.token);
await new Promise((r) => (client.isReady() ? r() : client.once('clientReady', r)));
const ch = await client.channels.fetch(channelId);
const ping = process.argv.includes('--ping');
const role = arg('role');
const embeds = arg('kind') === 'testers' ? testerNewsEmbeds() : botNewsEmbeds();
const msg = await ch.send({
  content: role ? `<@&${role}>` : ping ? '@everyone' : undefined,
  embeds,
  allowedMentions: { parse: [], roles: role ? [role] : [], ...(ping ? { parse: ['everyone'] } : {}) },
});
console.log('posted', msg.url);
await client.destroy();
process.exit(0);
