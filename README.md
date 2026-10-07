# IU QB Report

The current Indiana starting quarterback against every earlier Cignetti-era starter, lined up by game number (Game 1 vs Game 1, and so on), plus national leaderboards, the Heisman field, and BetMGM Heisman odds.  In 2026 that is Josh Hoover (2026) against Fernando Mendoza (2025) and Kurtis Rourke (2024).  Completed seasons also show full-season totals in the game logs and pace tiles.

Live page: https://qb.daboodah.com/ (the old https://daboodah-oss.github.io/iu-qb-report/ address redirects here)

The page follows the OS light/dark setting automatically; the sun/moon button in the header overrides it and remembers the choice (localStorage `qb-theme`).

## Quarterbacks: roster.json

`roster.json` lists one starter per season (`key`, `name`, `short`, `season`, `espn_id`, optional `note`, and `final_totals` once a season is over).  The newest season is the current QB; every earlier season is a comparison QB.  Page headings, copy, charts, link-preview text, national ranks and the Heisman section all read from it, so nothing names a player in code.

To start a new season (for example 2027):
1. Add the new starter to `roster.json` and add `final_totals` (published passing yards, TD, INT) to the season that just ended.
2. Nothing else changes: `collect.py` takes the season from the roster.  The next full refresh tracks the new QB's games, and the previous current QB becomes a comparison QB automatically.
3. Optional: record the new QB's preseason Heisman line in `data/heisman.json` as `<key>_opening` (a hand-recorded odds snapshot, the one allowed hand edit).

A comparison QB whose game log is not stored yet is backfilled once, automatically, by the `backfill` step in `collect.py`: it reads ESPN's athlete game log for that season, checks every row against the NCAA passer-rating formula, joins it to that season's cfbstats schedule (ESPN's schedule fills any game cfbstats lacks), and stores it only if the season reconciles to `final_totals`.  It also stores that season's final opponent pass-defense ranks.  Until then the page shows the other QBs plus a Data note.  Chart colors: crimson for the current QB, then blue, amber, teal and purple for earlier starters, newest first.

## How it updates

`.github/workflows/update.yml` runs a full refresh every Sunday and Wednesday at 10:47 Eastern (and on demand from the Actions tab, "Run workflow"). During game windows (Thursday/Friday/Saturday, 4 PM–2 AM Eastern) it also runs a lightweight check every 20 minutes: if ESPN shows an IU game has gone final since the last update, it runs the full pipeline; otherwise it exits in seconds without publishing anything.

1. `collect.py` pulls ESPN game logs (current QB, plus a one-time backfill of any earlier roster QB not yet stored), cfbstats.com schedule/leaderboards/pass defense, and the BetMGM Heisman odds table.  Each section is independent; a failure keeps that section's last verified data.
2. `update.py` validates every row before it is stored (for example, each passer rating must match the NCAA formula).
3. `build_report.py` recomputes everything from the stored rows and writes `index.html`.  If any check fails, nothing is published.
4. Changes are committed back to `main`, which GitHub Pages serves.

If a source cannot be read, the run is marked failed (GitHub emails the owner) and `data/last_run.json` says which section.  The page still publishes with the last good data and a note.

No AI or paid service is involved in the weekly run.
