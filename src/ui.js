import { EmbedBuilder } from 'discord.js';

// One look for every embed the bot makes:
//  - flat: the embed color matches Discord's dark embed background, so there is no colored stripe
//  - heading: one emoji + bold UPPERCASE text, with a rule line under it
//  - at most 3 columns across, one value per cell
//  - every embed ends its description with an invisible line so they all stretch to the same width
//  - one emoji per meaning (E below), the same words for the same event
export const FLAT = 0x2b2d31;
// Sets the width of every embed. 17 + 17 filler characters plus two thin spaces reach the widest an embed can get (about 487px of text).
// If a blank line appears under a summary line the embed is too wide for that window: lower the 17s. Too narrow: raise them.
export const FILLER = 'ㅤ'.repeat(17) + '  ' + 'ㅤ'.repeat(17);
export const FILLER_SHORT = 'ㅤ'.repeat(26); // embeds that carry a big image are narrower, so a shorter width line
export const RULE = '─'.repeat(13);        // under a column heading
export const WIDE_RULE = '─'.repeat(34);   // under a full-width heading
export const GAP = '; ';           // divider inside the summary line
export const SEP = ' · ';

export const E = {
  fixed: '✅', open: '🐛', new: '🆕', investigating: '🔎', fixing: '🛠️', update: '📣',
  duplicate: '🔁', notbug: 'ℹ️', warn: '⚠️', game: '🎮', user: '👤', date: '📅', log: '📜',
  lock: '🔒', video: '🎥', status: '📌', severity: '⚡', device: '🎮', fix: '🔧', note: '📝',
};

export const STATUS = {
  new: `${E.new} New`, needs_info: '❓ Needs info', investigating: `${E.investigating} Investigating`,
  fixing: `${E.fixing} Fixing`, fixed: `${E.fixed} Fixed`, duplicate: `${E.duplicate} Duplicate`,
  not_a_bug: `${E.notbug} Not a bug`,
};
export const SEVERITY = { low: '🟢 Low', medium: '🟡 Medium', high: '🔴 High', critical: '⛔ Critical' };

export const cut = (x, n) => { x = String(x ?? ''); return x.length > n ? x.slice(0, n - 1) + '…' : x; };

// "🎮 GAME": the heading used for columns and fields
export const head = (emoji, text) => `${emoji} ${String(text).toUpperCase()}`;

export const flat = () => new EmbedBuilder().setColor(FLAT);

// Description = summary line + the invisible width line.
export const describe = (e, line, filler = FILLER) => e.setDescription(`${line}\n${filler}`);

// One inline field per column: heading, a rule (pass '' for none), then one line per row.
export const columns = (e, cols, rule = RULE) => e.addFields(cols.map((c) => ({
  name: c.name,
  value: `${rule ? `${rule}\n` : ''}${c.lines.join('\n') || '—'}`.slice(0, 1024),
  inline: true,
})));

// An empty line of space between two parts of an embed.
export const spacer = (e) => e.addFields({ name: '​', value: '​' });

// A full-width field with no rule line.
export const plain = (e, name, text) => e.addFields({ name, value: String(text).slice(0, 1024) });

// A full-width field: heading, a wide rule, then text.
export const section = (e, name, text) => e.addFields({ name, value: `${WIDE_RULE}\n${text}`.slice(0, 1024) });

// Mod cards: no rule, heading ends with a colon, text ends with a period.
export const sentence = (s) => { s = String(s ?? '').trim(); return /[.!?]$/.test(s) ? s : `${s}.`; };
export const labeled = (e, name, text) => e.addFields({ name: `${name}:`, value: String(text).slice(0, 1024) });

// A full-width field with no rule and one blank line of space after it (used to separate sections).
export const spaced = (e, name, text) => e.addFields({ name, value: `${String(text).slice(0, 1000)}\n​` });
