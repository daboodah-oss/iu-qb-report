#!/usr/bin/env python3
"""National reference players for the QB, RB and WR compare charts.  Called from collect.py (no AI step).

Sources
  national boards .... cfbstats.com national player leaders (passing, rushing, receiving), one page per stat
  game logs .......... the cfbstats.com game log of each listed player, reached from the link on his
                       leaderboard row (never by name matching)

For each tab and each compare-chart stat that has a national leaderboard, the top 20 players at the tab's
positions (Indiana excluded) form the search pool; the first 3 are that stat's "National Top 3".  A player
is stored only if his game log has as many games as his leaderboard G and its totals equal his leaderboard
line (for QBs, every game's passer rating must also match the NCAA formula).  Anything else is dropped and
named in the run log, never estimated.  A stored log is reused until that player's leaderboard line changes.
"""
import io, os, re, time

import pandas as pd

POOL_N, TOP_N = 20, 3
BASE = "https://cfbstats.com/{season}/leader/national/player/split01/category{cat}/"
TABS = {  # cfbstats category, game-log page, positions, line keys {ours: column}, chart stats {key: column}
    "qb": {"cat": "02", "page": "passing", "positions": ["QB"],
           "line": {"att": "Att", "cmp": "Comp", "yds": "Yards", "td": "TD", "int": "Int"},
           "stats": {"yds": "Yards", "td": "TD", "rating": "Rating", "pct": "Pct", "att": "Att"}},
    "rb": {"cat": "01", "page": "rushing", "positions": ["RB"],
           "line": {"att": "Att", "yds": "Yards", "td": "TD"},
           "stats": {"yds": "Yards", "td": "TD", "ypc": "Avg", "ypg": "Yards/G", "att": "Att"}},
    "wr": {"cat": "03", "page": "receiving", "positions": ["WR", "TE"],
           "line": {"rec": "Rec", "yds": "Yards", "td": "TD"},
           "stats": {"yds": "Yards", "rec": "Rec", "td": "TD", "ypr": "Avg", "ypg": "Yards/G"}},
}
LOG_COLS = {"att": "att", "cmp": "comp", "yds": "yards", "td": "td", "int": "int", "rec": "rec"}  # game-log column names


class Mismatch(ValueError): pass


def reject(msg):
    raise Mismatch(msg.split(": ", 1)[-1] if msg.startswith("natref") else msg)


def whole(v):
    """'1,234' or 5.0 -> int; refuses a fraction rather than truncating it."""
    f = float(str(v).replace(",", "").strip())
    if f != int(f): raise ValueError(f"not a whole number: {v}")
    return int(f)


def clean(c):
    return re.sub(r"\.", "", str(c)).strip()


def board(C, url, html, col, positions):
    """Rows of one leaderboard page, with each player's link.  Verifies the page is sorted by `col`."""
    t = pd.read_html(io.StringIO(html), extract_links="body")[0]
    t.columns = [clean(c) for c in t.columns]
    txt = lambda v: str(v[0] if isinstance(v, tuple) else v).strip()
    vcol = next((c for c in t.columns if c.lower() == col.lower()), None)
    if not vcol: raise ValueError(f"{url}: no '{col}' column (columns: {list(t.columns)})")
    rk_col, last, rows = t.columns[0], None, []
    for _, r in t.iterrows():
        rk = txt(r[rk_col]); last = int(float(rk)) if rk and rk.lower() != "nan" else last
        name, href = r["Name"] if isinstance(r["Name"], tuple) else (r["Name"], None)
        m = re.search(r"/(\d{4})/player/(\d+)/(\d+)/", href or "")
        if not m: raise ValueError(f"{url}: no player link on the row for {txt(name)}")
        team = txt(r["Team"]); team = C.TEAM_FIX.get(team, team)
        pos = txt(r["Pos"]) if "Pos" in t.columns else ""
        rows.append({"rank": last, "name": txt(name), "team": team, "pos": pos, "g": whole(txt(r["G"])),
                     "value": float(txt(r[vcol]).replace(",", "")), "href": href,
                     "id": f"{m.group(2)}-{m.group(3)}", "cells": {clean(c): txt(r[c]) for c in t.columns}})
    vals = [x["value"] for x in rows]
    if vals != sorted(vals, reverse=True): raise ValueError(f"{url}: not sorted by {col}; wrong page for this stat")
    if positions:
        if "Pos" not in t.columns: raise ValueError(f"{url}: no Pos column, so the {'/'.join(positions)} filter cannot be applied")
        rows = [x for x in rows if x["pos"] in positions]
    return rows


def gamelog(C, season, href, page, tab):
    """The game log the leaderboard row links to: one row per game played (a '-' cell counts as 0)."""
    m = re.search(r"/(\d{4})/player/(\d+)/(\d+)/", href)
    url = f"https://cfbstats.com/{m.group(1)}/player/{m.group(2)}/{m.group(3)}/{page}/gamelog.html"
    t = pd.read_html(io.StringIO(C.get(url).text))[0]
    t.columns = [clean(c).lower() for c in t.columns]
    keys = list(TABS[tab]["line"])
    first = LOG_COLS[keys[0]]
    out = []
    for _, r in t.iterrows():
        d = re.match(r"(\d{2})/(\d{2})/(\d{2})", str(r.get("date", "")))
        if not d: continue  # totals row
        if not re.fullmatch(r"-?[\d,]+|-|nan|", str(r[first]).strip()): continue  # e.g. "Did not play" spans the row
        val = lambda k: 0 if str(r[k]).strip() in ("-", "nan", "") else whole(r[k])
        opp = str(r.get("opponent", "")).strip()
        g = {"date": f"20{d.group(3)}-{d.group(1)}-{d.group(2)}",
             "opp": re.sub(r"^\d+\s+", "", re.sub(r"^[@+]\s*", "", opp)).strip(),
             "site": "A" if opp.startswith("@") else "N" if opp.startswith("+") else "H",
             "result": "" if str(r.get("result", "")).lower() == "nan" else str(r.get("result", "")).strip(),
             **{k: val(LOG_COLS[k]) for k in keys}}
        if tab == "qb":
            rt = str(r.get("rating", "")).strip()
            g["src_rating"] = float(rt) if re.fullmatch(r"-?[\d.]+", rt) else None
        out.append(g)
    return out, url


def run_tab(C, U, tab, stored):
    spec, season = TABS[tab], C.SEASON
    base = BASE.format(season=season, cat=spec["cat"])
    first = C.get(base + "sort01.html").text
    links = {clean(lab).lower(): href for href, lab in re.findall(r'href="[^"]*?(sort\d+\.html)"[^>]*>([^<]+)</a>', first)}
    stats, dates, lines = {}, set(), {}
    for key, col in spec["stats"].items():
        href = links.get(col.lower(), "sort01.html")  # the unlinked column is the page's default sort
        html = first if href == "sort01.html" else C.get(base + href).text
        dates.add(C.through_date(html))
        rows = [x for x in board(C, base + href, html, col, spec["positions"]) if x["team"] != "Indiana"][:POOL_N]
        stats[key] = {"source_url": base + href, "order": [x["id"] for x in rows]}
        for x in rows: lines.setdefault(x["id"], x)
    dates.discard(None)
    if len(dates) != 1: raise ValueError(f"{tab} leaderboard pages disagree on 'through' date: {sorted(dates)}")
    players, dropped, fetched = {}, [], 0
    for pid, x in lines.items():
        line = {"g": x["g"], **{k: whole(x["cells"][c]) for k, c in spec["line"].items()}}
        old = stored.get(pid)
        if old and old.get("line") == line and old.get("games"):
            players[pid] = old; continue
        try:
            if fetched and not os.environ.get("OFFLINE_RAW"): time.sleep(0.4)  # be polite to cfbstats
            fetched += 1
            games, url = gamelog(C, season, x["href"], spec["page"], tab)
            U.natref_check(tab, x["name"], line, games, die=reject)  # the store step repeats this check
        except Mismatch as e:
            dropped.append(f"{x['name']} ({x['team']}): {e}"); continue
        except Exception as e:
            dropped.append(f"{x['name']} ({x['team']}): game log not read ({e})"); continue
        players[pid] = {"name": x["name"], "team": x["team"], "pos": x["pos"], "line": line, "url": url, "games": games}
    if lines and not players: raise ValueError(f"{tab}: no national player's game log could be verified ({'; '.join(dropped[:3])})")
    for s in stats.values():  # the Top 3 is the leaderboard's first 3; a dropped one is named, never replaced by #4
        s["top"] = [p for p in s["order"][:TOP_N] if p in players]
        s["top_dropped"] = [lines[p]["name"] for p in s["order"][:TOP_N] if p not in players]
        s["order"] = [p for p in s["order"] if p in players]
    C.log(f"[natref] {tab}: {len(players)} players stored ({fetched} game logs fetched, {len(players) - fetched + len(dropped)} unchanged)"
          + (f"; dropped {len(dropped)}: " + "; ".join(dropped) if dropped else ""))
    return {"data_through": dates.pop(), "positions": spec["positions"], "stats": stats, "players": players, "dropped": dropped}


def run(C, U):
    """One section per tab, so a failed tab keeps its last verified data and the others still update."""
    for tab in TABS:
        def job(tab=tab):
            stored = (U.load_or("national_logs.json", {}).get(tab) or {}).get("players", {})
            U.natref({"tab": tab, "season": C.SEASON, **run_tab(C, U, tab, stored)})
        C.section(f"natref_{tab}")(job)()
