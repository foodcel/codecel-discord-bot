# Code audit · 2026-11-05

## Status (2026-11-05 evening): done
- **Fixed:** all 8 critical items (C1–C8) and every high item.
- **Medium items fixed:** stored bug numbers, update-draft locks, the per-person AI limit, card limits, dev boards after claims, permission re-checks, admin-only strikes, the rival GIF cooldown, ffmpeg limits, loop blocking.
- **Clean-up done:** dead code and 53 scripts removed, ids moved to config, one access table (`bot/core/access.py`), one status list (`bot/features/bugs/statuses.py`).
- **Structure done:**
  - The folders `core/`, `discord_ui/` and `features/<area>/` now exist.
  - Routing uses one table per component type.
  - `giveaway.py` is split into six modules.
- **Guard rails added:** `tests/` (17 tests) plus pyflakes, both run by `deploy.sh`.

Left on purpose (risk to approved looks or flows, with no fix gained):
- **Native V2 card builders.** The boards, roster and help are still built as embeds and converted. They now stay within Discord's limits through `pngs.fit`.
- **One shared intake for bugs and suggestions.** The two keep their own wording, but they now have the same guards: dev reports, saved messages, exploit check, duplicate check.
- **One `ensure_message` helper.** The tester board's repost loop, the one real bug, is fixed.

The whole bot was read: 12,000 lines in `bot/` (52 modules) and 90 scripts in `scripts/` (4,300 lines). Nothing was changed by the audit.
The items marked **checked** were re-read in the code after the audit. The others were reported once, by reading the code.

## 1. What is wrong, most serious first

### Critical: fix first (things are already broken or can be abused)
| # | Where | What goes wrong |
|---|---|---|
| C1 | `giveaway.py:708` `FIELDS` | **checked.** `bypass_roles` and `per_boost` are missing from `FIELDS`, so a **new** giveaway silently drops "always allowed in" roles and "+N per boost". The live giveaway only works because those two settings were written into it by hand. |
| C2 | `timers.py:64` | **checked.** A timer row is deleted **before** it runs. If the job fails or the bot stops mid-run, the job is lost: a giveaway that never ends, a ban that is never lifted, a fixed post that is never deleted. |
| C3 | `__main__.py:66-120` | **checked.** `on_ready` runs about 12 steps with no protection, and the timer loop starts **last**. One failed step (a 429 while registering commands) means timers and the board sync never start. A reconnect does not retry. |
| C4 | `forms.py:227` + `intake.py:120` | **checked.** With `!bug` / `!suggest`, the reporter is the person who **wrote** the saved message. If the AI calls it a troll, that person gets a **strike**, and they never reported anything. |
| C5 | `cards.py:360`, `testerboard.py:133`, `cards.py:443`, `board.py:581` | **checked.** `AllowedMentions(roles=[...])` leaves `@everyone` and user pings on. A game named `@everyone`, or a line in an update or note, can ping the whole server. |
| C6 | `invites.py` | Invite credit can be inflated. In a burst of joins only the first is attributed, and the others become unchecked "earlier invites" for good. One person who leaves and rejoins through several links counts for every inviter. Self-invites count too. |
| C7 | `intake.py:79` | A public report that looks like a private **tester** report gets "DUPLICATE of #4 <private title>" with a link, which leaks unreleased-game details. |
| C8 | `suggest.py:76` | A suggestion that turns out to be an exploit is turned into a normal public bug. Exploit text is never hidden on that path. |

### High
- **Fixed bugs with no game tag** (`announce.py:26`): never in an update, so the reporter is never told and the thread is never closed.
- **A fixed bug moved back to investigating** (`fixes.py`): it stays in the draft and gets announced as fixed. Marking it fixed again later never re-announces it.
- **`tell_fixed`** sets "told" before it reaches the thread. One Discord hiccup and the reporter is never told. Nothing retries.
- **Tester reports** are saved with `thread_id='0'` before the thread exists (`tester.py:146`). A crash at the wrong moment blocks every later tester report.
- **Double clicks post twice:** update Post, giveaway Start (double @everyone) and release Post have no lock.
- **Giveaway `end()`** can run twice (timer plus `/giveaway end`), which gives two draws and two announcements. Entries are still accepted up to a minute after the end.
- **Giveaway Enter** first re-reads the whole boosters channel and can miss Discord's 3-second window. If that read fails, Enter breaks for everyone and the draw aborts.
- **Roblox link checks** are loose: `evil.com/?x=roblox.com/games/1` passes. A schemeless link breaks the whole library refresh.
- **The library guard** polls the channel **every second**, about 170,000 requests a day.
- **A handler that fails after `defer`** leaves the user on "thinking…" for 15 minutes, and the generic error is never sent.

### Medium (selection)
- **Bug numbers** (#7) are worked out on every call and **shift** when a bug changes game, so `7 fixed` can hit a different bug. Every board row rescans the whole table.
- **Update drafts:** no lock, so several drafts can appear for the same fixes. A hand-edited draft marks every id announced.
- **AI:** one daily cap for everyone. A spammer can use it up and stop triage for all. A failed AI call leaves a report stuck or closes it as "never answered".
- **Cards:** a long roster or games list passes Discord's 4,000-character or 40-part limit and silently stops updating. The tester board then reposts itself.
- **Dev boards** do not refresh after `/claim` or `/assign`.
- **Modal and button handlers:** `annedit`, `tr:`, `trg:`, `bd:`, `fl:` and others check permissions only by being in dev-only channels.
- **`/pardon` and `/strikes`** are open to every dev, but `/help` says admin.
- **The rival-bot GIF reply** has no cooldown, so it can loop.
- **Event loop blocking:** the image crop (`urlopen`), the banner drawing and the giveaway entry counts all run on the event loop, which freezes the bot.
- **ffmpeg** runs with no timeout. A full-board transcript loads every video into memory.

### Dead code (nothing uses it)
- **Whole module:** `layout_mobile.py`.
- **Single functions:**
  - `ui.spacer`, `look._plain`, `look._spaced`, `devlog.note`
  - `announce.all_updates`, `botnews.too_long`, `tags.status_tag_ids`
  - `games.with_gaps`, `games._valid_date`
  - `giveaway._count`, `giveaway._pool` (a wrapper), `button_bug` and the `bug:` route
  - `clear_bug_messages`, the `bug_msgs` table, `cfg.app_id`
- **Legacy bounty-board path** (`bounty.refresh_claims` non-live branch, `parse_claims`, `schedule_claims`, `cfg.bounty_id`).
- **One-time migrations still run on every start:** `board_v3`, `threshold_3`, `testers.import_old`.
- **The old embed builders** (`build_embeds`, `board_embed`, `release_news_*`) are only used by previews.
- **About 20 unused imports.**
- **`hunting.py`'s owner ping** never fires: `OWNER_ID` is in `.env` but never read.

### Scripts
Of the 90 scripts, **about 55 can be deleted**: old mockups (two are already broken), previews, one-time migrations and scripts now replaced by commands. **About 35 are worth keeping**: diagnostics, ops tools and end-to-end tests. The full list is in the appendix.

## 2. Why it got like this (structure)
1. **Permissions live in five places:** `DEV_ONLY`, the `jr/none` gate, inline `level()` checks, the `/help` pages and `lock_commands.py`. They already disagree. There are five meanings of "dev" (`perms.level`, `board.is_dev`, `testers.dev_members`, `can_volunteer`, `can_run`).
2. **`interactions.py` is the router and a feature module at once.** Long `if kind == ...` chains route interactions, and an unknown id gives "interaction failed".
3. **Two copies of the bug pipeline:** `intake.analyze_and_act` and `suggest.analyze_and_act` are the same five steps with different guards. This is why the dev-report rule exists in one and not the other.
4. **Cards are built as embeds, then converted** (`look.card_from_embed`), so nothing knows Discord's card limits. There are about 7 card builders, each with its own width hack.
5. **One message-refresh pattern copied three times** (board, roster, tester board), each failing differently.
6. **Config in three styles:** `cfg.*` with real ids hard-coded as defaults, JSON in `kv`, and ids written straight into modules (`boosts.CHANNEL`, `DEV_CHAT` twice, `guides.*`).
7. **Statuses are free strings** in about 10 modules (`new`, `needs_info`, `exploit_*`...) with no single list.
8. **No error boundaries:** steps either swallow errors (state drifts) or die halfway. State changes and Discord calls happen without a lock or a recovery pass.
9. **Cycles hidden by imports inside functions:** `games`↔`release`, `fixes`↔`announce`, `tester`↔`forms`, `reldraft`↔`cards`.
10. **`giveaway.py` (980 lines)** holds five modules: rules, card, draw, draft UI and stats.

## 3. The target layout
```
bot/
  core/        app.py (start-up, loops), config.py (every id, from .env + one table), db.py (+ migrations), errors.py, timers.py
  discord/     router.py (custom_id -> handler table), perms.py (ONE access table: command -> who), mentions.py (safe AllowedMentions),
               cards/ (V2 builders: dev look + community look, limits checked), messages.py (ensure_message: edit-or-send-once)
  features/
    bugs/      pipeline.py (one intake for bugs + suggestions + tester), statuses.py, numbers.py (stored, never shift), boards.py, fixlog.py, transcript.py
    updates/   drafts.py, announce.py, notify.py (tell reporters, with retry)
    games/     lists.py, release.py, library.py, watch.py, bounty.py
    testers/   roster.py, board.py
    giveaways/ rules.py, draw.py, card.py, draft.py, stats.py
    invites/   tracker.py, stats.py, boosts.py
    fun/       mog.py
  ai/          client.py (cap per user), prompts.py, schemas.py (validated results)
scripts/       ~35 kept tools, each with --dry-run by default
tests/         unit tests for the pure parts (prizes, numbers, entries, links, permissions)
```

## 4. The path, in order (each step ships on its own and keeps the bot running)
**Phase 1 · safety fixes (about a day, no restructuring)**
1. Fix C1 to C8.
2. Make every `AllowedMentions` explicit, through one helper.
3. Add locks: claim the draft or giveaway **before** sending, and set `status='ended'` before the first await.
4. Delete a timer only **after** it succeeds. Add a start-up sweep for overdue giveaways and unsent "fixed" notices.
5. Protect `on_ready` step by step, and start the loops first.
6. Use one Roblox link parser that returns a clean `https://www.roblox.com/games/<id>`.
7. Library guard: event-driven, plus the 90-second refresh, with no 1-second polling.
8. Defer before slow work everywhere. On error, `edit_original_response`.

**Phase 2 · clean-up (half a day)**
1. Delete the dead code and about 55 scripts (list below). Remove one-time migrations that already ran.
2. Move every hard-coded id into `config.py`. Read `OWNER_ID`.
3. Write one statuses list and one access table (command to role). `/help`, the router and `lock_commands.py` all read it.

**Phase 3 · structure (2–3 days, one feature folder at a time)**
1. `core/` and `discord/router.py`: a table of custom_id prefix to handler, with a reply for anything unknown.
2. Merge the two bug pipelines into one, with the guards in one place.
3. Store bug numbers when a bug is first routed (a migration fills in the current ones, so nothing visible changes).
4. Build cards directly as V2 components, with limit checks and paging. Drop `card_from_embed`.
5. Use one `ensure_message()` for the board, roster, tester board and library.
6. Split `giveaway.py` and `invites.py` into their folders. Fix invite attribution: the latest join only, no self-invites, and no "earlier invites" for unattributed joins.
7. Move heavy work off the event loop (image crop, banner cache, entry counts cached per redraw).

**Phase 4 · guard rails**
1. Add `tests/` for the pure logic (prizes, entries, numbers, links, permissions) and run them in `deploy.sh` before pushing.
2. Run `pyflakes` in `deploy.sh`, so unused code shows up.
3. Add a weekly log check for any handler error.

## Appendix · scripts triage
**Keep:**
- Setup: `_boot`, `lock_commands`, `command_locks`, `role_perms`.
- Diagnostics: `smoke_cards`, `inspect_board`, `inspect_channel`, `list_roles`, `list_news`, `roster_members`, `dump_embed`, `dump_board`, `owners`.
- Refresh: `watch_now`, `refresh_library`, `refresh_boards`, `refresh_everything`, `testing_board`.
- Posting and cleanup: `post_library`, `post_card`, `take_back`, `add_to_library`, `delete_msgs`, `wipe_test`, `dedupe_board`, `dedupe_library`, `repost_board`.
- Data fixes: `make_game_tags`, `set_bug_game`.
- Tests: `e2e_forms`, `e2e_release`, `e2e_suggestions`, `e2e_tester`, `check_tester_forum`, `test_board`, `preview_cards`.

**Delete:**
- Mockups: `mockup_*` (two are broken).
- Previews and demos: `show_all`, `show_missed`, `show_board_options`, `preview_widths`, `preview_roster_example`, `preview_testers`, `preview_guides`, `preview_news`, `preview_board`, `preview.py`, `demo_draft`, `demo_update`, `try_convert`, `purge_and_news`.
- One-time fixes and migrations: `convert_guides`, `swap_guides`, `move_guide`, `port_updates`, `trim_updates`, `merge_updates`, `edit_all_news`, `edit_announcement`, `post_announcement`, `post_release_news`, `post_logged`, `renumber`, `fix_titles`, `tag_emojis`, `reserve_bug_tags`.
- Old data restores and seeds: `restore_games`, `restore_cards`, `seed_cards`, `seed_credits`, `fix_card`, `go_live_library`, `take_over_games`, `save_banner`, `unpin_games`, `rebuild_update_cards`.
- Replaced by commands: `setup_board`, `post_testers`, `post_tester_guide`, `backfill_art`, `backfill_icons`.
- Tests of removed code: `audit_games`, `e2e_games`.
