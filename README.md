# IU QB Watch

Josh Hoover's 2026 season against Fernando Mendoza's 2025 Heisman season at the same game count, plus national leaderboards, the Heisman QB field, and BetMGM Heisman odds.

Live page: https://daboodah-oss.github.io/iu-qb-report/

## How it updates

`.github/workflows/update.yml` runs every Sunday and Wednesday at 10:47 Eastern (and on demand from the Actions tab, "Run workflow").

1. `collect.py` pulls ESPN game logs, cfbstats.com schedule/leaderboards/pass defense, and the BetMGM Heisman odds table.  Each section is independent; a failure keeps that section's last verified data.
2. `update.py` validates every row before it is stored (for example, each passer rating must match the NCAA formula).
3. `build_report.py` recomputes everything from the stored rows and writes `index.html`.  If any check fails, nothing is published.
4. Changes are committed back to `main`, which GitHub Pages serves.

If a source cannot be read, the run is marked failed (GitHub emails the owner) and `data/last_run.json` says which section.  The page still publishes with the last good data and a note.

No AI or paid service is involved in the weekly run.
