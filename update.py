#!/usr/bin/env python3
"""Small, safe editors for the IU QB Report data files.

Each command takes one JSON argument (or '-' to read JSON from stdin), checks it,
and merges it into data/*.json. Run `python3 update.py status` first on every run.

  status                         summary of what is stored
  qb-game       {game row}       append the current QB's newest game (skips if date exists)
                                 ('hoover-game' is kept as an alias)
  backfill      {season block}   store a completed season for an earlier roster QB (once)
  national      {latest block}   replace current leaderboards; upsert rank history
  heisman       {snapshot}       add one sportsbook snapshot (skips if book+date exists)
  cohort        {"qbs":[...]}    replace the Heisman field game logs
  opp-d         {"2026":{...}}   replace one season's opponent pass-D ranks
  next-game     {game} | null    set or clear the next scheduled IU game
  team-season   {season block}   store one team's box-score season (must match cfbstats totals when given)
  ap-poll       {poll}           store the latest AP Top 5 (poll name, date, teams)
  skill         {tab, players}   store RB or WR player game logs (must match cfbstats season rows)
  skill-national {tab, boards}   replace RB or WR national boards; upsert weekly rank history

The quarterbacks come from roster.json: the newest season is the current QB,
earlier seasons are comparison QBs. National/odds fields named hoover_* in
data files are legacy names that always mean "the current QB".
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(ROOT, "data", f)
CATS = ["yds", "td", "pct", "rating", "ypa"]


def load(f): return json.load(open(P(f)))


def roster():
    return json.load(open(os.path.join(ROOT, "roster.json")))


def current():
    """Roster entry for the current season's QB (the newest season)."""
    return max(roster()["qbs"], key=lambda q: q["season"])


def espn_log_url(espn_id):
    return f"https://www.espn.com/college-football/player/gamelog/_/id/{espn_id}"


def save(f, d):
    tmp = P(f) + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1)
    os.replace(tmp, P(f))


def die(msg):
    print("REFUSED:", msg); sys.exit(2)


def rating(r):
    return (8.4 * r["yds"] + 330 * r["td"] + 100 * r["cmp"] - 200 * r["int"]) / r["att"]


def need_ints(r, keys, tag):
    for k in keys:
        if not isinstance(r.get(k), int): die(f"{tag}: '{k}' must be an integer")
    if r["cmp"] > r["att"]: die(f"{tag}: completions exceed attempts")


def status():
    g, n, h, c = load("games.json"), load("national.json"), load("heisman.json"), load("cohort.json")
    cur = current()
    for q in sorted(roster()["qbs"], key=lambda q: -q["season"]):
        G = g.get(q["key"], {}).get("games", [])
        tag = "current" if q is cur or q["key"] == cur["key"] else "comparison"
        last = f"; last: {G[-1]['date']} {G[-1]['opp']} {G[-1]['result']}" if G else " (not collected yet)"
        print(f"{q['name']} {q['season']} ({tag}): {len(G)} games{last}")
    print(f"Next game: {g.get('next_game')}")
    L = n["latest"]
    print(f"National data_through: {L['data_through']} ({cur['short']} row g={L['hoover_row']['g']}); ranks: " +
          ", ".join(f"{k}={L['boards'][k]['hoover_rank']}" for k in CATS))
    print("Rank history: " + "; ".join(f"{e['through']}:{e['ranks']}" for e in n["rank_history"]))
    latest = {}
    for s in h["snapshots"]: latest[s["book"]] = max(latest.get(s["book"], ""), s["as_of"])
    print("Heisman latest by book: " + ", ".join(f"{b} {d}" for b, d in sorted(latest.items())))
    print("Cohort: " + ", ".join(f"{q['name']} ({len(q['games'])} g)" for q in c["qbs"]))
    print("Opp pass D: " + ", ".join(f"{k} through {v['through']}" for k, v in sorted(g["opp_pass_defense"].items()) if isinstance(v, dict)))


def arg():
    raw = sys.argv[2] if len(sys.argv) > 2 else "-"
    return json.loads(sys.stdin.read() if raw == "-" else raw)


MAX_GAMES = 17  # sanity cap: no FBS season (12 regular + title game + full playoff run) is longer


def check_row(r, tag):
    need_ints(r, ["cmp", "att", "yds", "td", "int", "rush_att", "rush_yds", "rush_td"], tag)
    for k in ("date", "opp", "site", "level", "result"):
        if not r.get(k): die(f"{tag}: '{k}' required")
    datetime.date.fromisoformat(r["date"])
    if r["site"] not in ("H", "A", "N"): die(f"{tag}: site must be H, A or N")
    if r["level"] not in ("FBS", "FCS"): die(f"{tag}: level must be FBS or FCS")


def qb_game(r):
    cur = current(); tag = f"qb-game ({cur['short']})"
    check_row(r, tag)
    g = load("games.json")
    blk = g.setdefault(cur["key"], {"name": cur["name"], "season": cur["season"], "espn_id": cur["espn_id"],
                                    "source_url": espn_log_url(cur["espn_id"]), "games": []})
    H = blk["games"]
    if any(x["date"] == r["date"] for x in H): print("SKIPPED: game already stored for", r["date"]); return
    if H and r["date"] < H[-1]["date"]: die("date is older than the last stored game")
    if not r["date"].startswith((str(cur["season"]), str(cur["season"] + 1))): die(f"{tag}: date is outside the {cur['season']} season")
    if len(H) >= MAX_GAMES: die(f"{tag}: already {len(H)} games stored")
    H.append(r)
    blk["retrieved_at"] = datetime.datetime.now().astimezone().isoformat(timespec="minutes")
    save("games.json", g); print(f"ADDED {cur['short']} game {len(H)}: {r['opp']} {r['result']}")


hoover_game = qb_game  # legacy name


def backfill(b):
    """Store a completed season for an earlier roster QB. Runs once per QB: an existing block is never replaced."""
    q = next((x for x in roster()["qbs"] if x["key"] == b.get("key")), None) or die("backfill: key is not in roster.json")
    if q["season"] >= current()["season"]: die("backfill: only completed seasons can be backfilled")
    g = load("games.json")
    if g.get(q["key"], {}).get("games"): print(f"SKIPPED: {q['name']} {q['season']} already stored"); return
    games = b.get("games") or die("backfill: no games")
    if len(games) > MAX_GAMES: die("backfill: too many games")
    for r in games:
        check_row(r, f"backfill {q['short']} {r.get('date')}")
        if not r["date"].startswith((str(q["season"]), str(q["season"] + 1))): die(f"backfill: {r['date']} is outside the {q['season']} season")
        if r["att"] and abs(rating(r) - r.pop("src_rating", rating(r))) > 0.06: die(f"backfill: {r['date']} rating does not match the NCAA formula")
    dates = [r["date"] for r in games]
    if dates != sorted(dates) or len(set(dates)) != len(dates): die("backfill: games out of order or duplicated")
    ft = q.get("final_totals")
    if ft:
        got = {k: sum(r[k] for r in games) for k in ft}
        if got != ft: die(f"backfill: season totals {got} do not reconcile to published {ft}")
    g[q["key"]] = {"name": q["name"], "season": q["season"], "espn_id": q["espn_id"],
                   "source_url": b.get("source_url") or espn_log_url(q["espn_id"]),
                   "verified_note": b.get("verified_note", ""),
                   "retrieved_at": datetime.datetime.now().astimezone().isoformat(timespec="minutes"), "games": games}
    save("games.json", g); print(f"BACKFILLED {q['name']} {q['season']}: {len(games)} games")


def national(L):
    for k in ("data_through", "boards", "hoover_row"):
        if k not in L: die(f"national: '{k}' required")
    need_ints(L["hoover_row"], ["g", "cmp", "att", "yds", "td", "int"], "hoover_row")
    for cat in CATS:
        b = L["boards"].get(cat) or die(f"national: board '{cat}' missing")
        if not isinstance(b.get("hoover_rank"), int) or b["hoover_rank"] < 1: die(f"{cat}: hoover_rank must be a positive integer")
        if len(b.get("rows", [])) < 5: die(f"{cat}: need at least five rows")
        for r in b["rows"]:
            need_ints(r, ["g", "cmp", "att", "yds", "td", "int"], f"{cat} {r.get('name')}")
            if abs(rating(r) - r["src_rating"]) > 0.06:
                die(f"{cat} {r['name']}: computed rating {rating(r):.2f} != source {r['src_rating']}; re-read the row")
    n = load("national.json")
    old = n["latest"]["boards"]
    for cat in CATS:  # keep labels / urls / qualifier flags
        for k in ("label", "source_url", "qualified"):
            if k in old[cat] and k not in L["boards"][cat]: L["boards"][cat][k] = old[cat][k]
    L.setdefault("retrieved_at", datetime.datetime.now().astimezone().isoformat(timespec="minutes"))
    n["latest"] = L
    entry = {"through": L["data_through"], "games": L["hoover_row"]["g"], "ranks": {c: L["boards"][c]["hoover_rank"] for c in CATS}}
    # one point per football week (Tue-Mon): a newer snapshot in the same week replaces the older one
    def wk(d):
        d = datetime.date.fromisoformat(d); return (d - datetime.timedelta(days=(d.weekday() - 1) % 7)).isoformat()
    keep = {}
    for e in sorted(n["rank_history"] + [entry], key=lambda e: e["through"]):
        keep[wk(e["through"])] = e
    n["rank_history"] = [keep[k] for k in sorted(keep)]
    save("national.json", n); print("UPDATED national through", L["data_through"], entry["ranks"])


def heisman(s):
    for k in ("book", "as_of", "outlet", "url", "odds"):
        if not s.get(k): die(f"heisman: '{k}' required")
    datetime.date.fromisoformat(s["as_of"])
    h = load("heisman.json")
    new_players = s.pop("players", {})
    for name, o in s["odds"].items():
        if not isinstance(o, int) or o == 0: die(f"heisman: odds for {name} must be a non-zero integer (American)")
        if name not in h["players"] and name not in new_players:
            die(f"heisman: new player '{name}' needs players entry with school and pos")
    h["players"].update(new_players)
    if any(x["book"] == s["book"] and x["as_of"] == s["as_of"] for x in h["snapshots"]):
        print("SKIPPED: snapshot exists for", s["book"], s["as_of"]); return
    cur = current()
    h["snapshots"].append(s); save("heisman.json", h); print("ADDED", s["book"], s["as_of"], f"{cur['short']}:", s["odds"].get(cur["name"]))


def cohort(c):
    qbs = c.get("qbs") or die("cohort: 'qbs' required")
    if len(qbs) != 4: die("cohort: exactly four players (the current QB is added automatically)")
    for q in qbs:
        for g in q["games"]:
            need_ints(g, ["cmp", "att", "yds", "td", "int"], q["name"])
            datetime.date.fromisoformat(g["date"])
    d = load("cohort.json"); d["qbs"] = qbs
    d["retrieved_at"] = datetime.datetime.now().astimezone().isoformat(timespec="minutes")
    save("cohort.json", d); print("UPDATED cohort:", ", ".join(q["name"] for q in qbs))


def opp_d(x):
    g = load("games.json")
    for season, v in x.items():
        if "through" not in v or "ranks" not in v: die("opp-d: need through and ranks")
        v.setdefault("source_url", g["opp_pass_defense"].get(season, {}).get("source_url"))
        g["opp_pass_defense"][season] = v
    save("games.json", g); print("UPDATED opponent pass-D ranks")


def next_game(x):
    g = load("games.json"); g["next_game"] = x; save("games.json", g); print("UPDATED next game:", x)



# ================================================================ RB, WR and Team tabs
TEAM_KEYS = ["pf", "pa", "total_yds", "rush_yds", "pass_yds", "to_lost", "to_gained", "third_conv", "third_att"]
SKILL_KEYS = {"rb": ["att", "yds", "td"], "wr": ["rec", "yds", "td"]}


def load_or(f, default):
    return json.load(open(P(f))) if os.path.exists(P(f)) else default


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="minutes")


def check_team_game(g, tag):
    need_ints(dict(g, cmp=0, att=0), TEAM_KEYS, tag)
    datetime.date.fromisoformat(g["date"])
    if g.get("site") not in ("H", "A", "N"): die(f"{tag}: bad site")
    if g["total_yds"] != g["rush_yds"] + g["pass_yds"]: die(f"{tag}: total yards {g['total_yds']} != rushing {g['rush_yds']} + passing {g['pass_yds']}")
    if not 0 <= g["third_conv"] <= g["third_att"]: die(f"{tag}: third-down conversions exceed attempts")
    if min(g["to_lost"], g["to_gained"], g["pf"], g["pa"]) < 0: die(f"{tag}: negative count")
    wl = "W" if g["pf"] > g["pa"] else "L" if g["pf"] < g["pa"] else "T"
    if g.get("result") != f"{wl} {g['pf']}-{g['pa']}": die(f"{tag}: result '{g.get('result')}' disagrees with the score")


def season_sums(games):
    return {"games": len(games), **{k: sum(g[k] for g in games) for k in TEAM_KEYS}}


def team_season(x):
    """Store one team's season of box-score rows: {team_id, name, season, games, cfbstats|None, complete}.
    If cfbstats season totals are given they must match the sums exactly, or nothing is stored."""
    tid, season, games = str(x["team_id"]), str(x["season"]), x.get("games") or die("team-season: no games")
    for g in games: check_team_game(g, f"team {x.get('name')} {season} {g.get('date')}")
    dates = [g["date"] for g in games]
    if dates != sorted(dates) or len(set(g["event"] for g in games)) != len(games): die("team-season: games out of order or duplicated")
    cf = x.get("cfbstats")
    if cf:
        got = season_sums(games)
        bad = {k: (got[k], v) for k, v in cf["totals"].items() if got.get(k) != v}
        if bad: die(f"team-season {x.get('name')} {season}: ESPN box scores disagree with cfbstats season totals {bad}")
    d = load_or("team.json", {"teams": {}, "ap": None})
    t = d["teams"].setdefault(tid, {"name": x.get("name"), "seasons": {}})
    t["name"] = x.get("name") or t.get("name")
    t["seasons"][season] = {"games": games, "complete": bool(x.get("complete")), "retrieved_at": now_iso(),
                            "check": f"cfbstats season totals matched through {cf['through']}" if cf else x.get("check_note", "not cross-checked"),
                            "cfbstats_url": cf.get("url") if cf else None}
    keep = set(map(str, x.get("keep_teams") or [])) | {tid}
    if x.get("keep_teams") is not None: d["teams"] = {k: v for k, v in d["teams"].items() if k in keep}
    save("team.json", d); print(f"STORED team {x.get('name')} {season}: {len(games)} games")


def ap_poll(p):
    for k in ("poll", "date", "top"):
        if not p.get(k): die(f"ap-poll: '{k}' required")
    datetime.date.fromisoformat(p["date"][:10])
    ranks = [t["rank"] for t in p["top"]]
    if ranks != sorted(ranks) or ranks[0] != 1 or len(p["top"]) < 5: die("ap-poll: need ranks 1..5 in order")
    for t in p["top"]:
        if not t.get("team_id") or not t.get("name"): die("ap-poll: team id and name required")
    d = load_or("team.json", {"teams": {}, "ap": None})
    d["ap"] = dict(p, retrieved_at=now_iso()); save("team.json", d)
    print("STORED", p["poll"], p["date"][:10], ", ".join(f"{t['rank']} {t['name']}" for t in p["top"]))


def skill(x):
    """Store one tab's players: {tab, players:[{name, season, role, games, cfbstats_row|None}]}.
    Each player's game rows must sum exactly to the cfbstats season row when one is given."""
    tab = x.get("tab"); keys = SKILL_KEYS.get(tab) or die("skill: tab must be rb or wr")
    out = []
    for p in x.get("players") or die("skill: no players"):
        tag = f"skill {tab} {p.get('name')} {p.get('season')}"
        if not p.get("games"): die(f"{tag}: no games")
        for g in p["games"]:
            need_ints(dict(g, cmp=0, att=g.get("att", 0)), keys, tag)
            datetime.date.fromisoformat(g["date"])
        row = p.get("cfbstats_row")
        if row:
            got = {k: sum(g[k] for g in p["games"]) for k in keys}
            want = {k: row[k] for k in keys}
            if got != want: die(f"{tag}: ESPN box scores {got} disagree with cfbstats season row {want}")
        out.append(p)
    d = load_or("skill.json", {})
    d[tab] = {"players": out, "retrieved_at": now_iso(), "rule": x.get("rule", "")}
    save("skill.json", d); print(f"STORED {tab}: " + ", ".join(f"{p['name']} {p['season']} ({len(p['games'])} g)" for p in out))


def skill_national(x):
    """Replace one tab's national boards and upsert its weekly rank history."""
    tab = x.get("tab")
    if tab not in SKILL_KEYS: die("skill-national: tab must be rb or wr")
    for cat, b in (x.get("boards") or die("skill-national: no boards")).items():
        if len(b.get("top", [])) < 5: die(f"skill-national {tab} {cat}: need at least five leaders")
        for r in b["top"]:
            if not isinstance(r.get("rank"), int) or r["rank"] < 1: die(f"skill-national {tab} {cat}: bad rank for {r.get('name')}")
    d = load_or("skill_national.json", {})
    t = d.setdefault(tab, {"latest": None, "rank_history": []})
    t["latest"] = {k: x[k] for k in ("data_through", "boards", "players")}
    t["latest"]["retrieved_at"] = now_iso()
    entry = {"through": x["data_through"], "ranks": {n: {c: b["players"].get(n, {}).get("rank") for c, b in x["boards"].items()} for n in x["players"]}}
    def wk(s):
        s = datetime.date.fromisoformat(s); return (s - datetime.timedelta(days=(s.weekday() - 1) % 7)).isoformat()
    keep = {}
    for e in sorted(t["rank_history"] + [entry], key=lambda e: e["through"]): keep[wk(e["through"])] = e
    t["rank_history"] = [keep[k] for k in sorted(keep)]
    save("skill_national.json", d); print(f"STORED {tab} national boards through {x['data_through']}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    fn = {"status": None, "qb-game": qb_game, "hoover-game": qb_game, "backfill": backfill, "national": national, "heisman": heisman,
          "cohort": cohort, "opp-d": opp_d, "next-game": next_game,
          "team-season": team_season, "ap-poll": ap_poll, "skill": skill, "skill-national": skill_national}.get(cmd)
    if cmd == "status": status()
    elif fn: fn(arg())
    else: print(__doc__); sys.exit(1)
