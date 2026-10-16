# IU Football Report ("Hoosiers 2026")

Indiana's current season against the earlier Cignetti-era seasons, lined up by game number (Game 1 vs Game 1, and so on), on four tabs.  The site title is `site_title` in `roster.json` ("Hoosiers {season}"), so it becomes "Hoosiers 2027" on its own when the 2027 QB is added.

- **QB:** the current starter against every earlier Cignetti-era starter (Hoover 2026 vs Mendoza 2025 and Rourke 2024), plus national leaderboards, the Heisman field, and BetMGM Heisman odds.
- **RB:** the current season's named running backs (Beebe and Richard in 2026) against each earlier season's top 2 RBs by rushing yards.  Rushing yards, rushing TD, yards per carry, yards per game, plus national top-5 boards with both current backs' ranks.
- **WR:** the current season's named receivers (Becker and Marsh in 2026) against each earlier season's top 2 WR/TE by receiving yards.  Receptions, receiving yards, receiving TD, yards per catch, yards per game, plus national top-5 boards.
- **Team:** Indiana's current season against its earlier Cignetti-era seasons and the current AP Top 5 (the poll's week and release date are shown).  Record, points scored and allowed, total, rushing and passing yards, turnover margin, third-down %.

Each compare chart (QB, RB, WR) can also draw gray national reference lines, from two collapsible sections under "IU players": **National Top 3** (the top three non-Indiana players at that position in the stat being viewed; the chips change with the stat and start off) and **Individual player** (search a pool of roughly the top 20 per tracked stat, then add or remove players as pills).  Every national line comes from that player's own cfbstats.com game log, linked from his leaderboard row, and is stored only if it matches his leaderboard line exactly.

Completed seasons also show full-season totals.  Colors: crimson for the current season (on RB/WR, the first named player solid and the second dashed), then blue, amber, teal and purple for earlier seasons, newest first (two players per season: solid then dashed).  AP Top 5 teams use dotted lines in teal, violet, green, slate and orchid by poll rank.

Live page: https://qb.daboodah.com/ (the old https://daboodah-oss.github.io/iu-qb-report/ address redirects here)

The page follows the OS light/dark setting automatically; the sun/moon button in the header overrides it and remembers the choice (localStorage `qb-theme`).

## Quarterbacks: roster.json

`roster.json` lists one starter per season (`key`, `name`, `short`, `season`, `espn_id`, optional `note`, and `final_totals` once a season is over).  The newest season is the current QB; every earlier season is a comparison QB.  Page headings, copy, charts, link-preview text, national ranks and the Heisman section all read from it, so nothing names a player in code.

To start a new season (for example 2027):
1. Add the new starter to `roster.json` and add `final_totals` (published passing yards, TD, INT) to the season that just ended.
2. Nothing else changes: `collect.py` takes the season from the roster.  The next full refresh tracks the new QB's games, and the previous current QB becomes a comparison QB automatically.
3. Optional: record the new QB's preseason Heisman line in `data/heisman.json` as `<key>_opening` (a hand-recorded odds snapshot, the one allowed hand edit).

A comparison QB whose game log is not stored yet is backfilled once, automatically, by the `backfill` step in `collect.py`: it reads ESPN's athlete game log for that season, checks every row against the NCAA passer-rating formula, joins it to that season's cfbstats schedule (ESPN's schedule fills any game cfbstats lacks), and stores it only if the season reconciles to `final_totals`.  It also stores that season's final opponent pass-defense ranks.  Until then the page shows the other QBs plus a Data note.  Chart colors: crimson for the current QB, then blue, amber, teal and purple for earlier starters, newest first.

## RB, WR and Team tabs: roster.json "tabs"

- `tabs.rb.current` / `tabs.wr.current` name the current season's players by season, for example `"2026": ["Lee Beebe Jr.", "Turbo Richard"]` (first = solid line, second = dashed).  A season with no entry uses Indiana's top `count` players at `positions` by yards.  Earlier seasons always use that top-by-yards rule, read from cfbstats.com's Indiana rushing and receiving pages.
- Game lines come from ESPN box scores of every Indiana game (`data/team.json`), so no player IDs are needed.  A player's games are the games he played according to his cfbstats.com game log, including games without a carry (RB) or catch (WR), which count as 0; each game's carries or catches and TD must also match that game log.  For the newest game, before cfbstats posts it, a game counts once the player has a line in ESPN's box score.
- Checks before anything is stored (`collect_tabs.py` + `update.py`): each box score's player lines must add up to that box score's team total; total yards must equal rushing plus passing; the score must match ESPN's schedule; turnovers must equal fumbles lost plus interceptions; each player's season must match his cfbstats.com season row, and each team season must match cfbstats.com's season team statistics, once cfbstats has posted the same games (completed seasons must match before they are stored at all).
- The AP Top 5 comes from ESPN's rankings feed (AP Top 25 entry).  If Indiana is in it, Indiana's own crimson line stands in for it.  Teams that drop out of the top 5 are removed from `data/team.json` on the next refresh.

## How it updates

The schedule did not change for the new tabs.  `.github/workflows/update.yml` runs a full refresh every Sunday and Wednesday at 10:47 Eastern (and on demand from the Actions tab, "Run workflow"). During game windows (Thursday/Friday/Saturday, 4 PM–2 AM Eastern) it also runs a lightweight check every 20 minutes: if ESPN shows an IU game has gone final since the last update, it runs the full pipeline; otherwise it exits in seconds without publishing anything.

1. `collect.py` pulls ESPN game logs (current QB, plus a one-time backfill of any earlier roster QB not yet stored), cfbstats.com schedule/leaderboards/pass defense, and the BetMGM Heisman odds table.  It then runs `collect_tabs.py`: the ESPN AP poll, ESPN box scores for every Indiana game and every AP Top 5 team's games (only games not already stored are fetched), cfbstats.com season cross-checks, and cfbstats.com national rushing and receiving leaderboards.  Finally `collect_natref.py` reads the cfbstats.com national passing, rushing and receiving leaderboards for every compare-chart stat, keeps the top 20 non-Indiana players at each position, and fetches each one's game log from the link on his leaderboard row (only when his leaderboard line has changed since the last run).  A log is stored only if its game count and totals equal his leaderboard line (and, for quarterbacks, every game's passer rating matches the NCAA formula); anything else is dropped and named in the run log.  Each section is independent; a failure keeps that section's last verified data.
2. `update.py` validates every row before it is stored (for example, each passer rating must match the NCAA formula).
3. `build_report.py` (with `build_tabs.py` for the RB, WR and Team tabs) recomputes everything from the stored rows and writes `index.html`.  If any check fails, nothing is published.  A tab whose data has not been collected yet shows a short notice instead.
4. Changes are committed back to `main`, which GitHub Pages serves.

## Installed app

The page can be installed from the browser menu ("Install app" or "Add to Home screen").  `manifest.webmanifest` at the repo root gives the installed app its name, its colours (`theme_color` #990000, the page's theme-color; `background_color` #111216, the dark theme's `--bg`, the theme Jeff runs) and its icons in `icons/`.  `build_report.py` refuses to publish if the manifest link, a member, or an icon does not resolve, or if `theme_color` drifts from the page's theme-color tag.  The 512px icons are drawn from `assets/iu-trident.svg` by `tools/make_icons.py`; rerun it if the logo changes.  There is no service worker: Chrome installs from the menu without one, and the page has no install button that would need one.  An installed copy picks up a changed manifest on Chrome's own cycle (about daily, on launch), not on publish; delete and re-add the app to force it.

If a source cannot be read, the run is marked failed (GitHub emails the owner) and `data/last_run.json` says which section.  The page still publishes with the last good data and a note.

No AI or paid service is involved in the weekly run.

## Secrets

No secret is stored in this repository, in GitHub Actions secrets, or in any file on disk.

| Credential | Where it lives | What it accesses | Scope | Owner | Expires | Renewal reminder | What breaks if it lapses |
|---|---|---|---|---|---|---|---|
| Fine-grained personal access token used for manual `git push` (and on-demand workflow runs from `tools/run_workflow.ps1`; `tools/gh_status.py` uses it only for a higher API rate limit) | Windows Credential Manager on Jeff's PC (entry `git:https://github.com`), stored by Git Credential Manager on first push.  Master copy in LastPass ("GitHub Token - iu-qb-report") | `daboodah-oss/iu-qb-report` only: Contents read/write, Actions read/write, Workflows read/write, Pages read/write, Metadata read | Single-repo fine-grained PAT; no Administration, no other repositories, no account settings | Jeff Bandera (GitHub account `daboodah-oss`) | Created 2026-09-26; expires 2027-01-04 | 2026-12-21 (14 days before expiry) | Code pushes from Jeff's PC (including changes Claude prepares as patch files) and on-demand workflow dispatches from the PC.  The scheduled Actions runs are unaffected: they use GitHub's temporary per-run `GITHUB_TOKEN` (`contents: write`, this repository only), which expires when each run ends |

**Machine-bound step: code pushes and on-demand runs.**
- Machine: Jeff's Windows PC (`jeff-cppc-2022`), git working copy at `C:\Users\jeffb\github\iu-qb-report` (outside OneDrive; the OneDrive project folder is not a repository).
- Helper scripts (in `tools/`): `push_feature.ps1` (push a non-main branch), `run_workflow.ps1` (start a run), `gh_status.py` (recent runs and repo files; works without a credential because the repo is public).
- Why the credential lives there: Git Credential Manager keeps the PAT encrypted in Windows Credential Manager, so it never sits in a file, a chat, or the repository, and pushes need no copy-paste.
- When the PC is off: code changes cannot be pushed and on-demand runs cannot be started from the PC (a run can still be started from the GitHub app or website, Actions tab, "Run workflow").  The published page keeps updating on schedule, because the scheduled runs never use this credential.

Rules: never put a token in a file in this repository or its working folders (`.gitignore` blocks the usual names as a backstop).  To rotate: create a new fine-grained PAT with the same settings, update LastPass, remove the old `git:https://github.com` entry from Windows Credential Manager, push once and paste the new token at the prompt, then delete the old token on GitHub and update the expiry in the table above.
