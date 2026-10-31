import { PermissionFlagsBits as P } from 'discord.js';
import { cfg } from './env.js';

// 'admin' | 'jr' | 'dev' | 'none'. Jr wins over dev when someone has both roles.
export function level(m) {
  if (!m) return 'none';
  if (m.permissions.has(P.Administrator)) return 'admin';
  if (cfg.jrRole && m.roles.cache.has(cfg.jrRole)) return 'jr';
  if (m.roles.cache.has(cfg.devRole)) return 'dev';
  return 'none';
}

// Staff are never struck by the troll ladder.
export function isStaff(m) {
  return !!m && (m.user.bot || level(m) !== 'none' || m.id === m.guild.ownerId ||
    m.permissions.has(P.ModerateMembers) || m.permissions.has(P.KickMembers) ||
    m.permissions.has(P.BanMembers) || m.permissions.has(P.ManageMessages));
}

// Status commands, /update, /config for a game: admin, or a dev who owns it. Unclaimed = any dev.
export function canManage(m, owners) {
  const l = level(m);
  if (l === 'admin') return true;
  if (l !== 'dev') return false;
  return owners.length === 0 || owners.includes(m.id);
}

export const canConfirm = (m) => ['admin', 'dev'].includes(level(m));
