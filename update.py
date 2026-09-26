#!/usr/bin/env python3
"""Small, safe editors for the IU QB Watch data files.

Each command takes one JSON argument (or '-' to read JSON from stdin), checks it,
and merges it into data/*.json. Run `python3 update.py status` first on every run.

  status                         summary of what is stored
  hoover-game   {game row}       append Hoover's newest game (skips if date exists)
  national      {latest block}   replace current leaderboards; upsert rank history
  heisman       {snapshot}       add one sportsbook snapshot (skips if book+date exists)
  cohort        {"qbs":[...]}    replace the Heisman QB field game logs
  opp-d         {"2026":{...}}   replace current-season opponent pass-D ranks
  next-game     {game} | null    set or clear the next scheduled IU game
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(ROOT, "data", f)
CATS = ["yds", "td", "pct", "rating", "ypa"]


def load(f): return json.load(open(P(f)))


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
    H = g["hoover"]["games"]
    print(f"Hoover games stored: {len(H)}; last: {H[-1]['date']} {H[-1]['opp']} {H[-1]['result']}")
    print(f"Mendoza rows: {len(g['mendoza']['games'])}")
    print(f"Next game: {g.get('next_game')}")
    L = n["latest"]
    print(f"National data_through: {L['data_through']} (Hoover row g={L['hoover_row']['g']}); ranks: " +
          ", ".join(f"{k}={L['boards'][k]['hoover_rank']}" for k in CATS))
    print("Rank history: " + "; ".join(f"{e['through']}:{e['ranks']}" for e in n["rank_history"]))
    latest = {}
    for s in h["snapshots"]: latest[s["book"]] = max(latest.get(s["book"], ""), s["as_of"])
    print("Heisman latest by book: " + ", ".join(f"{b} {d}" for b, d in sorted(latest.items())))
    print("Cohort: " + ", ".join(f"{q['name']} ({len(q['games'])} g)" for q in c["qbs"]))
    print(f"Opp pass D 2026 through: {g['opp_pass_defense']['2026']['through']}")


def arg():
    raw = sys.argv[2] if len(sys.argv) > 2 else "-"
    return json.loads(sys.stdin.read() if raw == "-" else raw)


def hoover_game(r):
    need_ints(r, ["cmp", "att", "yds", "td", "int", "rush_att", "rush_yds", "rush_td"], "hoover-game")
    for k in ("date", "opp", "site", "level", "result"):
        if not r.get(k): die(f"hoover-game: '{k}' required")
    datetime.date.fromisoformat(r["date"])
    if r["site"] not in ("H", "A", "N"): die("site must be H, A or N")
    if r["level"] not in ("FBS", "FCS"): die("level must be FBS or FCS")
    g = load("games.json"); H = g["hoover"]["games"]
    if any(x["date"] == r["date"] for x in H): print("SKIPPED: game already stored for", r["date"]); return
    if r["date"] < H[-1]["date"]: die("date is older than the last stored game")
    if len(H) >= len(g["mendoza"]["games"]): die("Hoover would exceed Mendoza's 16 rows; comparison cannot extend")
    H.append(r)
    g["hoover"]["retrieved_at"] = datetime.datetime.now().astimezone().isoformat(timespec="minutes")
    save("games.json", g); print(f"ADDED game {len(H)}: {r['opp']} {r['result']}")


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
    n["rank_history"] = [e for e in n["rank_history"] if e["through"] != entry["through"]] + [entry]
    n["rank_history"].sort(key=lambda e: e["through"])
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
    h["snapshots"].append(s); save("heisman.json", h); print("ADDED", s["book"], s["as_of"], "Hoover:", s["odds"].get("Josh Hoover"))


def cohort(c):
    qbs = c.get("qbs") or die("cohort: 'qbs' required")
    if len(qbs) != 4: die("cohort: exactly four quarterbacks (Hoover is added automatically)")
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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    fn = {"status": None, "hoover-game": hoover_game, "national": national, "heisman": heisman,
          "cohort": cohort, "opp-d": opp_d, "next-game": next_game}.get(cmd)
    if cmd == "status": status()
    elif fn: fn(arg())
    else: print(__doc__); sys.exit(1)
