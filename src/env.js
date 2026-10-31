import dotenv from 'dotenv';
import { fileURLToPath } from 'node:url';

dotenv.config({ path: fileURLToPath(new URL('../.env', import.meta.url)) });

const need = ['DISCORD_TOKEN', 'APPLICATION_ID', 'ANTHROPIC_API_KEY', 'GUILD_ID', 'BUGS_CHANNEL_ID',
  'DEV_BUGS_FORUM_ID', 'MODLOG_CHANNEL_ID', 'DEV_ROLE_ID'];
for (const k of need) if (!process.env[k]) throw new Error(`Missing ${k} in .env`);

const e = process.env;
export const cfg = {
  token: e.DISCORD_TOKEN,
  appId: e.APPLICATION_ID,
  anthropicKey: e.ANTHROPIC_API_KEY,
  guildId: e.GUILD_ID,
  bugsId: e.BUGS_CHANNEL_ID,
  devForumId: e.DEV_BUGS_FORUM_ID,
  modlogId: e.MODLOG_CHANNEL_ID,
  devRole: e.DEV_ROLE_ID,
  jrRole: e.JR_DEV_ROLE_ID || null,       // optional
  bountyId: e.BOUNTY_BOARD_CHANNEL_ID || null, // optional: a channel whose embed lists who owns which game
  testId: e.TEST_CHANNEL_ID || null,
  updatesId: e.UPDATES_CHANNEL_ID || null,
  testingId: e.TESTING_CHANNEL_ID || null,
  testerRoles: (e.TESTER_ROLE_IDS || '').split(',').filter(Boolean),
  model: e.MODEL || 'claude-haiku-4-5-20251001',
  aiDailyCap: Number(e.AI_DAILY_CAP || 500),
};
