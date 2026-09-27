#!/usr/bin/env python3
"""Collect fresh data for IU QB Watch without any AI step.

Runs inside GitHub Actions (or any machine with open internet). Each section is
independent: a failure keeps that section's stored data, is logged, and makes
the script exit 1 at the end (so GitHub emails the owner), but every section
that did succeed is still saved and the page is still rebuilt.

Sources
  schedule + results ... cfbstats.com team page (Indiana = 306)
  Hoover game line ..... ESPN athlete gamelog JSON
  national boards ...... cfbstats.com national passing leaders (5 sort pages)
  opponent pass D ...... cfbstats.com team passing defense
  Heisman odds ......... BetMGM Heisman odds page (table)
  Heisman QB field ..... ESPN athlete gamelog JSON (+ ESPN search for new names)
"""
import datetime as dt, io, json, os, re, sys, traceback
from zoneinfo import ZoneInfo
import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402  (the same validated editors Claude used)

ET = ZoneInfo("America/Indiana/Indianapolis")
SEASON = 2026
IU_CFBSTATS = 306
HOOVER_ESPN = "4685401"
UA = {"User-Agent": "Mozilla/5.0 (compatible; iu-qb-watch/1.0; +https://github.com/daboodah-oss/iu-qb-report)"}
BOARD_SORT = {"yds": "sort08", "td": "sort10", "pct": "sort03", "rating": "sort02", "ypa": "sort04"}
BETMGM = "https://sports.betmgm.com/en/blog/college-football/heisman-trohpy-odds-favorites-to-win-bm06/"
TEAM_FIX = {"Oregon St": "Oregon State", "Miss St": "Mississippi State", "Coast Car": "Coastal Carolina",
            "SJSU": "San Jose State", "Va Tech": "Virginia Tech", "Miami (Fl)": "Miami", "Miami (FL)": "Miami",
            "Sam Hou St": "Sam Houston", "Wk Forest": "Wake Forest", "Okla St": "Oklahoma State",
            "N Texas": "North Texas", "Ariz St": "Arizona State", "Mich St": "Michigan State",
            "Ga Tech": "Georgia Tech", "Ga South": "Georgia Southern", "S Carolina": "South Carolina",
            "N Carolina": "North Carolina", "Texas A&M": "Texas A&M", "N'western": "Northwestern",
            "WKU": "Western Kentucky", "CSU": "Colorado State", "BC": "Boston College"}
LOG, FAILED = [], []


def log(msg):
    print(msg); LOG.append(msg)


class _Raw:  # offline testing: OFFLINE_RAW=<dir of saved pages>
    def __init__(s, t): s.status_code, s.text = int(t.split("\n", 1)[0]), t.split("\n", 1)[1]
    def json(s): return json.loads(s.text)
    def raise_for_status(s):
        if s.status_code >= 400: raise ValueError(f"HTTP {s.status_code}")


def get(url, **kw):
    if os.environ.get("OFFLINE_RAW"):
        f = os.path.join(os.environ["OFFLINE_RAW"], re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:] + ".txt")
        return _Raw(open(f).read())
    r = requests.get(url, headers=UA, timeout=30, **kw)
    if os.environ.get("SAVE_RAW"):  # debugging aid: keep exactly what each source returned
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw"); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:] + ".txt"), "w").write(f"{r.status_code}\n{r.text}")
    r.raise_for_status()
    return r


def mark_fresh(name):
    """Record when a section last collected successfully (shown on the page as 'last checked')."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "freshness.json")
    d = json.load(open(p)) if os.path.exists(p) else {}
    d[name] = dt.datetime.now(ET).isoformat(timespec="minutes")
    json.dump(d, open(p, "w"), indent=1)


def section(name):
    def wrap(fn):
        def run(*a, **k):
            try:
                out = fn(*a, **k)
                mark_fresh(name)
                return out
            except SystemExit as e:  # update.py refused the data
                FAILED.append(name); log(f"[{name}] REFUSED by validator (exit {e.code})")
            except Exception as e:
                FAILED.append(name); log(f"[{name}] FAILED: {e}"); traceback.print_exc()
        return run
    return wrap


def tables(url):
    return pd.read_html(io.StringIO(get(url).text))


def through_date(html):
    m = re.search(r"through\s+(\d{2})/(\d{2})/(\d{4})", html, re.I) or re.search(r"through\s+(\d{2})/(\d{2})/(\d{2})\b", html, re.I)
    if not m: return None
    y = int(m.group(3)); y = y + 2000 if y < 100 else y
    return dt.date(y, int(m.group(1)), int(m.group(2))).isoformat()


def ival(x):
    return int(str(x).replace(",", "").strip())


# ---------------------------------------------------------------- schedule
@section("schedule")
def schedule():
    url = f"https://cfbstats.com/{SEASON}/team/{IU_CFBSTATS}/index.html"
    tbs = tables(url)
    sch = next(t for t in tbs if "Opponent" in [str(c) for c in t.columns])
    games = []
    for _, r in sch.iterrows():
        d, opp, res = str(r.iloc[0]), str(r["Opponent"]), str(r.get("Result", "") or "")
        m = re.match(r"(\d{2})/(\d{2})/(\d{2})", d)
        if not m: continue
        date = dt.date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        site = "A" if opp.startswith("@") else "N" if opp.startswith("+") else "H"
        name = re.sub(r"^[@+]\s*", "", opp).strip()
        name = re.sub(r"^\d+\s+", "", name).strip()          # AP rank prefix
        res = "" if res.lower() == "nan" else res.strip()
        games.append({"date": date, "opp": name, "site": site, "result": res})
    log(f"[schedule] {len(games)} games, {sum(1 for g in games if g['result'])} played")
    return games


def fbs_teams():
    t = tables(f"https://cfbstats.com/{SEASON}/leader/national/team/defense/split01/category02/sort01.html")[0]
    col = "Team" if "Team" in t.columns else "Name"
    return set(TEAM_FIX.get(str(x), str(x)) for x in t[col])


# ---------------------------------------------------------------- ESPN gamelog
def espn_gamelog(athlete_id, seasontype=None):
    url = f"https://site.web.api.espn.com/apis/common/v3/sports/football/college-football/athletes/{athlete_id}/gamelog?season={SEASON}"
    if seasontype: url += f"&seasontype={seasontype}"
    j = get(url).json()
    labels = j.get("names") or j.get("labels")
    rows = {}
    for st in j.get("seasonTypes", []):
        for cat in st.get("categories", []):
            for ev in cat.get("events", []):
                rows[ev["eventId"]] = dict(zip(labels, ev["stats"]))
    out = []
    for eid, meta in j.get("events", {}).items():
        if eid not in rows: continue
        s = rows[eid]
        when = dt.datetime.fromisoformat(meta["gameDate"].replace("Z", "+00:00")).astimezone(ET)
        g = lambda *k: next((s[x] for x in k if x in s), "0")
        out.append({"espn_event": eid, "date": when.date().isoformat(),
                    "opp": meta.get("opponent", {}).get("displayName", ""),
                    "score": meta.get("score", ""), "wl": meta.get("gameResult", ""),
                    "cmp": ival(g("completions", "CMP")), "att": ival(g("passingAttempts", "ATT")),
                    "yds": ival(g("passingYards", "YDS")), "td": ival(g("passingTouchdowns", "TD")),
                    "int": ival(g("interceptions", "INT")), "sacks": ival(g("sacks", "SACK")),
                    "rtg": float(g("QBRating", "RTG")),
                    "rush_att": ival(g("rushingAttempts", "CAR")), "rush_yds": ival(g("rushingYards")),
                    "rush_td": ival(g("rushingTouchdowns"))})
    out.sort(key=lambda x: x["date"])
    for r in out:  # the listed rating must match the formula, or the row was misread
        calc = U.rating(r)
        if abs(calc - r["rtg"]) > 0.06:
            raise ValueError(f"ESPN row {r['date']} rating {r['rtg']} != computed {calc:.1f}")
    return out


# ---------------------------------------------------------------- Hoover's new games
@section("hoover")
def hoover(sched, fbs):
    if not sched: raise ValueError("no schedule")
    g = U.load("games.json"); have = {x["date"] for x in g["hoover"]["games"]}
    played = [x for x in sched if x["result"]]
    logs = espn_gamelog(HOOVER_ESPN)
    for i, sg in enumerate(played):
        if sg["date"] in have: continue
        # match ESPN row by date (ESPN date is converted to Eastern time)
        e = next((r for r in logs if r["date"] == sg["date"]), None)
        if not e:
            log(f"[hoover] {sg['date']} {sg['opp']}: no ESPN line yet (did not play, or not posted)"); continue
        row = {"date": sg["date"], "espn_event": e["espn_event"], "opp": sg["opp"], "site": sg["site"],
               "level": "FBS" if sg["opp"] in fbs else "FCS", "result": sg["result"],
               **{k: e[k] for k in ("cmp", "att", "yds", "td", "int", "rush_att", "rush_yds", "rush_td", "sacks")}}
        U.hoover_game(row); log(f"[hoover] added {sg['date']} {sg['opp']} {sg['result']}")
    nxt = next((x for x in sched if not x["result"]), None)
    ng = {"date": nxt["date"], "opp": nxt["opp"], "site": nxt["site"],
          "source_url": f"https://cfbstats.com/{SEASON}/team/{IU_CFBSTATS}/index.html"} if nxt else None
    if ng:
        try: ng.update(kickoff_info(ng["date"]))
        except Exception as e: log(f"[hoover] kickoff time not available: {e}")
    U.next_game(ng)


def kickoff_info(date):
    """Kickoff time and TV for IU's game on `date` (Eastern), from ESPN's team schedule. Empty if not set yet."""
    j = get(f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/84/schedule?season={SEASON}").json()
    for ev in j.get("events", []):
        when = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
        if when.date().isoformat() != date: continue
        comp = (ev.get("competitions") or [{}])[0]
        out = {}
        if comp.get("timeValid", True) and not comp.get("status", {}).get("type", {}).get("detail", "").upper().endswith("TBD"):
            out["kickoff"] = when.isoformat(timespec="minutes")
        tv = [b.get("media", {}).get("shortName") or ", ".join(b.get("names", [])) for b in comp.get("broadcasts", [])]
        tv = [t for t in tv if t]
        if tv: out["tv"] = tv[0]
        log(f"[hoover] next game kickoff: {out or 'not announced'}")
        return out
    return {}


# ---------------------------------------------------------------- national boards
@section("national")
def national():
    boards, dates, hoover_row = {}, set(), None
    for cat, sort in BOARD_SORT.items():
        url = f"https://cfbstats.com/{SEASON}/leader/national/player/split01/category02/{sort}.html"
        html = get(url).text; dates.add(through_date(html))
        t = pd.read_html(io.StringIO(html))[0]
        t.columns = [str(c).strip() for c in t.columns]
        rank_col = t.columns[0]
        rows, last_rank = [], None
        for _, r in t.iterrows():
            rk = str(r[rank_col]).strip()
            last_rank = int(float(rk)) if rk and rk.lower() != "nan" else last_rank
            row = {"name": str(r["Name"]).strip(), "team": TEAM_FIX.get(str(r["Team"]).strip(), str(r["Team"]).strip()),
                   "g": ival(r["G"]), "cmp": ival(r["Comp"]), "att": ival(r["Att"]), "yds": ival(r["Yards"]),
                   "td": ival(r["TD"]), "int": ival(r["Int"]), "src_rating": float(r["Rating"]), "_rank": last_rank}
            rows.append(row)
        hv = next((x for x in rows if x["name"] == "Josh Hoover"), None)
        if not hv: raise ValueError(f"Hoover not listed on the {cat} board (top 100)")
        hoover_row = {k: hv[k] for k in ("name", "team", "g", "cmp", "att", "yds", "td", "int", "src_rating")}
        top = [x for x in rows if x["_rank"] <= 5]
        vals = [U.rating(x) if cat == "rating" else x["yds"] / x["att"] if cat == "ypa" else 100 * x["cmp"] / x["att"] if cat == "pct" else x[cat] for x in top]
        hv_rank = hv["_rank"]
        if hv in top:  # recompute with full precision so it matches the builder's tie rule
            v = vals[top.index(hv)]; hv_rank = 1 + sum(1 for x in vals if x > v)
        boards[cat] = {"rows": [{k: v for k, v in x.items() if k != "_rank"} for x in top], "hoover_rank": hv_rank}
    dates.discard(None)
    if len(dates) != 1: raise ValueError(f"leaderboard pages disagree on 'through' date: {sorted(dates)}")
    U.national({"data_through": dates.pop(), "boards": boards, "hoover_row": hoover_row})


# ---------------------------------------------------------------- opponent pass D
@section("opp_d")
def opp_d():
    url = f"https://cfbstats.com/{SEASON}/leader/national/team/defense/split01/category02/sort01.html"
    html = get(url).text
    t = pd.read_html(io.StringIO(html))[0]
    rank_col, last, ranks = t.columns[0], None, {}
    for _, r in t.iterrows():
        rk = str(r[rank_col]).strip(); last = int(float(rk)) if rk and rk.lower() != "nan" else last
        tm = str(r["Team"] if "Team" in t.columns else r["Name"]).strip()
        ranks[TEAM_FIX.get(tm, tm)] = last
    g = U.load("games.json")
    mine = {x["opp"]: ranks[x["opp"]] for x in g["hoover"]["games"] if x.get("level") == "FBS" and x["opp"] in ranks}
    nxt = (g.get("next_game") or {}).get("opp")
    if nxt in ranks: mine[nxt] = ranks[nxt]
    U.opp_d({str(SEASON): {"through": through_date(html) or dt.date.today().isoformat(), "ranks": mine}})


# ---------------------------------------------------------------- Heisman odds (BetMGM)
def espn_player(name):
    url = "https://site.web.api.espn.com/apis/common/v3/search"
    j = get(url, params={"query": name, "type": "player", "sport": "football", "league": "college-football", "limit": 5}).json()
    for it in j.get("items", []) + [x for grp in j.get("results", []) for x in grp.get("contents", [])]:
        nm = it.get("displayName") or it.get("name")
        if nm and nm.lower() == name.lower():
            uid = str(it.get("id") or re.sub(r".*~a:", "", it.get("uid", "")))
            pos = (it.get("position") or {}).get("abbreviation") if isinstance(it.get("position"), dict) else it.get("subtitle", "")
            return uid, pos
    return None, None


@section("heisman")
def heisman():
    html = get(BETMGM).text
    m = re.search(r'dateModified"?\s*:\s*"(\d{4}-\d{2}-\d{2})T', html) or re.search(r'article:modified_time" content="(\d{4}-\d{2}-\d{2})', html)
    if not m: raise ValueError("BetMGM page has no modified date")
    as_of = m.group(1)
    t = next(x for x in pd.read_html(io.StringIO(html)) if any("odds" in str(c).lower() for c in x.columns))
    pcol = next(c for c in t.columns if "player" in str(c).lower())
    ocol = next(c for c in t.columns if "odds" in str(c).lower() and "open" not in str(c).lower())
    h = U.load("heisman.json"); odds, new = {}, {}
    for _, r in t.iterrows():
        o = re.sub(r"[^\d+-]", "", str(r[ocol]))
        if not re.fullmatch(r"[+-]?\d+", o): continue
        mm = re.match(r"\s*(.+?)\s*\(([^)]*)\)\s*$", str(r[pcol]))
        name, school = (mm.group(1), mm.group(2)) if mm else (str(r[pcol]).strip(), "")
        odds[name] = int(o)
        if name not in h["players"]:
            try: _, pos = espn_player(name)
            except Exception: pos = None
            new[name] = {"school": school, "pos": pos or "?"}
    if len(odds) < 8: raise ValueError(f"only {len(odds)} odds rows read from BetMGM")
    U.heisman({"book": "BetMGM", "as_of": as_of, "outlet": "BetMGM", "url": BETMGM, "odds": odds, "players": new})


# ---------------------------------------------------------------- Heisman QB field
@section("cohort")
def cohort():
    h, c = U.load("heisman.json"), U.load("cohort.json")
    latest = {}
    for s in sorted(h["snapshots"], key=lambda s: s["as_of"]): latest[s["book"]] = s
    newest = max(s["as_of"] for s in latest.values())
    books = [s for s in latest.values() if (dt.date.fromisoformat(newest) - dt.date.fromisoformat(s["as_of"])).days <= 10]
    prob = lambda o: 100 / (o + 100) if o > 0 else -o / (-o + 100)
    import statistics
    ranked = sorted(((statistics.median([prob(s["odds"][n]) for s in books if n in s["odds"]]), n)
                     for n, p in h["players"].items() if p.get("pos") == "QB" and n != "Josh Hoover"
                     and any(n in s["odds"] for s in books)), reverse=True)
    want = [n for _, n in ranked[:4]]
    ids = {q["name"]: q for q in c["qbs"]}
    qbs = []
    for n in want:
        q = ids.get(n)
        if not q:
            pid, _ = espn_player(n)
            if not pid: raise ValueError(f"no ESPN id found for {n}")
            q = {"name": n, "school": h["players"][n]["school"], "espn_id": pid}
        games = espn_gamelog(q["espn_id"])
        seen = set(); games = [x for x in games if not (x["espn_event"] in seen or seen.add(x["espn_event"]))]
        qbs.append({"name": n, "school": q["school"], "espn_id": q["espn_id"],
                    "games": [{"date": x["date"], "opp": x["opp"], "result": f"{x['wl']} {x['score']}".strip(),
                               **{k: x[k] for k in ("cmp", "att", "yds", "td", "int")}} for x in games]})
    U.cohort({"qbs": qbs})


def main():
    sched = schedule()
    fbs = set()
    try: fbs = fbs_teams()
    except Exception as e: log(f"[fbs list] {e}")
    hoover(sched, fbs)
    national()
    heisman()
    cohort()
    opp_d()
    log("FAILED sections: " + (", ".join(FAILED) if FAILED else "none"))
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "last_run.json"), "w").write(
        json.dumps({"at": dt.datetime.now(ET).isoformat(timespec="minutes"), "failed": FAILED, "log": LOG}, indent=1))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
