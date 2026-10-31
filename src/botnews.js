import { cfg } from './env.js';
import { E, columns, describe, flat, head, section } from './ui.js';

const BOT_HELPER_ID = process.env.BOT_HELPER_ID || ''; // optional: a bot this bot will move to (adds a PS line)
const OWNER_ID = process.env.OWNER_ID || '';             // optional: who devs report bot bugs to

// The launch announcement for the staff #announcements channel, as ONE embed. Channel names are real channel links.
// Built here so the preview and the real post are identical.
export function botNewsEmbeds() {
  const bugs = `<#${cfg.bugsId}>`;
  const board = `<#${cfg.devForumId}>`;
  const modlog = `<#${cfg.modlogId}>`;
  const e = flat().setTitle(head(E.update, 'New · the bug bot'))
    .setFooter({ text: 'Set your pings with /pings. Everything runs from your board.' });
  describe(e, `Reports in ${bugs} are now checked, tagged and sent to the dev who owns the game. Owners come from the bounty-board.`);
  section(e, head('😊', 'Your board'),
    `Every dev has a post in ${board} with their open bugs. Pick a game in the dropdown to scroll through its bugs one by one, with screenshots, videos and status buttons. A new bug gives you a quick ping.`);
  section(e, head(E.fixed, 'Fixing bugs'),
    'Press **Fixed**, or type `12 fixed` or `1-5 fixed`. The reporter and everyone who reacted 👀 are pinged, and the post is deleted after 24 hours. A reply of "still broken" reopens it. Also: investigating, fixing, not a bug, duplicate.');
  section(e, head(E.lock, 'Exploit reports'),
    `These are removed from ${bugs} at once and appear in your board as a **HIGH PRIORITY** card. The reporter gets a message that it was received, and another when you mark it fixed.`);
  section(e, head('📋', 'Transcripts'),
    'Per bug or per game: a zip with the conversation, screenshots, full videos and a few frames. Drop it into your AI agent.');
  section(e, head(E.log, 'Fix log'),
    `A pinned post in ${board} with fixed and open counts for every game, each fix, and its transcript.`);
  section(e, head(E.update, 'Updates'),
    'After 3 fixes the bot drafts an update with the bug fixes. Post, Edit or Later. `/update` adds your own lines, and the bot rewrites them into clean patch notes.');
  section(e, head(E.warn, 'Trolls'),
    `Warning, 1-day mute, kick, 7-day ban, permanent ban. Kicks and bans wait for a dev's Confirm in ${modlog}.`);
  columns(e, [
    { name: head('⌨️', 'Commands'), lines: [
      '`/pings` · choose your pings', '`/update` · post an update', '`/config set` · game link, icon, channel',
      '`/strikes` · a user\'s strikes', '`/pardon` · remove a strike'] },
    { name: head(E.user, 'Who can do what'), lines: [
      '**Devs** · act on their own games', '**Any dev** · unclaimed games', '**Jr devs** · read only', '**Admins** · everything'] },
  ], '─'.repeat(28));
  const ps = [BOT_HELPER_ID && `PS this bot will be moved to <@${BOT_HELPER_ID}>`, OWNER_ID && `Report any bugs to <@${OWNER_ID}>`].filter(Boolean);
  if (ps.length) e.addFields({ name: '​', value: ps.join('\n') });
  return [e];
}

// The announcement for the tester announcements channel: how to use /bug. One embed.
export function testerNewsEmbeds() {
  const testing = `<#${cfg.testingId}>`;
  const e = flat().setTitle(head(E.update, 'New · report bugs with /bug'))
    .setFooter({ text: 'Only testers can use /bug, and only in the testing channel.' });
  describe(e, `You can now send bugs straight to the developers from ${testing}. Your report goes to the dev who owns the game, with your screenshots and videos.`);
  section(e, head('🧪', 'How to report'),
    `1. Go to ${testing} and type \`/bug\`\n2. Pick the game\n3. Attach up to **10 screenshots** and **5 videos** if you have them\n4. Fill in the form and send it`);
  section(e, head(E.note, 'The form'),
    'A short title, what happened, the steps to reproduce, what should happen (optional) and your device or build (optional). The clearer the steps, the faster it gets fixed.');
  section(e, head('🧵', 'After you send it'),
    'The bot opens a thread in the testing channel, and the developer replies there. You get a ping in that thread when it is fixed. The thread is deleted 24 hours later. If it is still broken, reply in the thread and it reopens.');
  section(e, head(E.video, 'Big files'),
    'Files too big for Discord show up as download links on your report. Post them in your thread instead.');
  section(e, head(E.lock, 'Found an exploit?'),
    'If a bug lets players cheat or crash servers, do not post the details. Message a developer directly.');
  return [e];
}
