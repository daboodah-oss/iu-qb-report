# AGENTS.md — working conventions for iu-qb-report

This repo is a self-running pipeline. It must keep working with no human or AI
in the loop: GitHub Actions does everything on a schedule, and the validation
in `build_report.py` is the quality gate. Follow these rules so any helper
(human, Claude, or otherwise) can safely contribute.

## Pipeline

1. `collect.py` pulls ESPN game logs, cfbstats.com leaderboards, and sportsbook
   Heisman odds into `data/*.json`. Each section is independent; a failed
   section keeps its last verified data and is recorded in `data/last_run.json`.
2. `update.py` validates every row before it is stored (e.g. each passer rating
   must match the NCAA formula).
3. `build_report.py` recomputes everything from the stored rows and writes
   `index.html` from `template.html`. **If any validation check fails, nothing
   is published** — this is the rule that lets strangers contribute safely.
4. `.github/workflows/update.yml` commits the result back to `main`, which
   GitHub Pages serves at https://qb.daboodah.com/.

No AI or paid service is involved in the scheduled run. Keep it that way.

## Schedule

- Full refresh: Sunday and Wednesday, 10:47 AM Eastern (plus backups).
- Game-window quick checks: every 20 minutes, Thu/Fri/Sat 4 PM–2 AM Eastern.
  Each check exits in seconds unless ESPN shows a new IU final, then runs the
  full pipeline. A run with no new data changes nothing.

## Rules for contributors

1. **Pull before pushing.** The bot commits on schedule; push with
   `git pull --rebase` first to avoid collisions.
2. **Never hand-edit `data/*.json`.** Data comes from `collect.py`. The one
   exception is Heisman odds snapshots, which are recorded by hand from
   published reports — each snapshot must carry `book`, `as_of`, `outlet`,
   and `url`.
3. **Run the build locally before pushing** template or build changes:
   `python3 build_report.py --standalone --out /tmp/test.html` must print `OK`.
4. **Update this file and README.md when behavior changes.** Docs going stale
   is how multi-helper projects rot; the schedule change of 2026-10-04 was
   almost missed.
5. **Do not remove or let any step overwrite the `CNAME` file.** It holds the
   custom domain (`qb.daboodah.com`). The workflow only stages
   `data/`, `index.html`, and `logs/` — keep it that way.
6. **Keep page output deterministic.** No live API calls, no AI-generated
   text in the scheduled build. Editorial judgment (discrepancy writeups,
   caveats) is added by a human as data/notes, and the page renders them.
7. The output check in `build_report.py` rejects `TODO`, `lorem`,
   `PLACEHOLDER`, and anything looking like a credential. Don't add those.

## File map

- `collect.py` — data fetching (network)
- `update.py` — row validation before storage
- `build_report.py` — validation + model + render (no network)
- `template.html` — page; the model is injected at `/*__MODEL__*/null`
- `data/` — stored rows: `games.json`, `national.json`, `heisman.json`,
  `cohort.json`, `freshness.json`, `last_run.json`
- `icons/`, `assets/` — PWA icons, trident logo, link-preview card
- `logs/` — per-run logs, force-added to git

## Page behavior notes

- Theme: the page follows `prefers-color-scheme` unless the reader picks the
  header sun/moon toggle, which sets `data-theme` on `:root` and persists in
  localStorage (`qb-theme`). Charts redraw on `data-theme` changes via a
  MutationObserver. An inline head script applies the saved theme before first
  paint to avoid a flash.
