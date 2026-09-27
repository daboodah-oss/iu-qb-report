#!/usr/bin/env python3
"""Build the IU QB Watch report (Hoover 2026 vs Mendoza 2025).

Reads data/*.json, validates every row, computes one model object, and writes
report.html (template.html with the model injected). No network access.

Usage:  python3 build_report.py [--root DIR] [--out report.html] [--as-of ISO]
Exit code is non-zero if any validation check fails; nothing is written then.
"""
import argparse, json, statistics, sys, datetime, hashlib, os
from zoneinfo import ZoneInfo

CATS = ["yds", "td", "pct", "rating", "ypa"]
CAT_LABEL = {"yds": "Passing yards", "td": "Passing TD", "pct": "Completion %",
             "rating": "Passer rating", "ypa": "Yards per attempt"}
ERRORS = []


def check(cond, msg):
    if not cond:
        ERRORS.append(msg)


def rating(c, a, y, t, i):
    return (8.4 * y + 330 * t + 100 * c - 200 * i) / a if a else None


def metric(row, key):
    c, a = row["cmp"], row["att"]
    if key == "pct":
        return 100.0 * c / a if a else None
    if key == "ypa":
        return row["yds"] / a if a else None
    if key == "rating":
        return rating(c, a, row["yds"], row["td"], row["int"])
    return row[key]


def totals(games):
    keys = ["cmp", "att", "yds", "td", "int", "rush_att", "rush_yds", "rush_td"]
    t = {k: sum(g.get(k, 0) for g in games) for k in keys}
    t["games"] = len(games)
    for k in ("pct", "ypa", "rating"):
        t[k] = metric(t, k)
    t["total_td"] = t["td"] + t["rush_td"]
    return t


def validate_game(g, who):
    tag = f"{who} {g.get('date')} {g.get('opp')}"
    try:
        datetime.date.fromisoformat(g["date"])
    except Exception:
        ERRORS.append(f"{tag}: bad date")
    for k in ("cmp", "att", "yds", "td", "int"):
        check(isinstance(g.get(k), int), f"{tag}: {k} missing or not an integer")
    if all(isinstance(g.get(k), int) for k in ("cmp", "att")):
        check(0 <= g["cmp"] <= g["att"], f"{tag}: completions exceed attempts")
        check(g["att"] >= 0 and g["int"] >= 0 and g["td"] >= 0, f"{tag}: negative count")


def ordered_unique(games, who):
    dates = [g["date"] for g in games]
    check(dates == sorted(dates), f"{who}: games not in date order")
    check(len(set(dates)) == len(dates), f"{who}: duplicate game date")


def comp_rank(values, v, higher_better=True):
    """Competition ranking: 1 + count strictly better."""
    return 1 + sum(1 for x in values if (x > v if higher_better else x < v))


def american_to_prob(o):
    return 100.0 / (o + 100.0) if o > 0 else (-o) / (-o + 100.0)


def build(root, as_of):
    D = lambda f: json.load(open(os.path.join(root, "data", f)))
    games, nat, heis, coh = D("games.json"), D("national.json"), D("heisman.json"), D("cohort.json")

    H, M = games["hoover"]["games"], games["mendoza"]["games"]
    for g in H: validate_game(g, "Hoover")
    for g in M: validate_game(g, "Mendoza")
    ordered_unique(H, "Hoover"); ordered_unique(M, "Mendoza")
    N = len(H)
    check(N >= 1, "no Hoover games")
    check(len(M) >= N, f"Mendoza has only {len(M)} rows for a {N}-game comparison")

    ht, mt = totals(H), totals(M[:N])
    mfull = totals(M)

    # Regression fixture (4-game values verified 2026-09-26)
    if N == 4:
        check((mt["cmp"], mt["att"], mt["yds"], mt["td"]) == (76, 99, 975, 14), "fixture: Mendoza 4-game totals changed")
        check((ht["cmp"], ht["att"], ht["yds"], ht["td"]) == (56, 80, 850, 11), "fixture: Hoover 4-game totals changed")
        check(abs(mt["rating"] - 206.2) < 0.06 and abs(ht["rating"] - 204.6) < 0.06, "fixture: ratings changed")
    check((mfull["yds"], mfull["td"], mfull["int"]) == (3535, 41, 6), "Mendoza 2025 season totals do not reconcile")

    # Head to head
    h2h_defs = [("yds", "Passing yards", True, 0), ("td", "Passing TD", True, 0),
                ("pct", "Completion %", True, 1), ("rating", "Passer rating", True, 1),
                ("ypa", "Yards per attempt", True, 1), ("int", "Interceptions", False, 0),
                ("rush_yds", "Rushing yards", True, 0), ("total_td", "Total TD (pass + rush)", True, 0)]
    h2h = []
    for key, label, hb, dp in h2h_defs:
        hv, mv = ht[key], mt[key]
        hr, mr = round(hv, dp), round(mv, dp)
        if hr == mr: w = "tie"
        elif (hr > mr) == hb: w = "hoover"
        else: w = "mendoza"
        h2h.append({"key": key, "label": label, "hoover": hv, "mendoza": mv, "dp": dp,
                    "higher_better": hb, "winner": w, "headline": key in CATS})
    head = [x for x in h2h if x["headline"]]
    hl = sum(1 for x in head if x["winner"] == "hoover")
    ml = sum(1 for x in head if x["winner"] == "mendoza")
    ties = len(head) - hl - ml
    names = lambda w: [x["label"].lower() for x in head if x["winner"] == w]
    def join(xs): return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
    if hl > ml: lead = f"Hoover leads Mendoza's same-point line in {hl} of {len(head)} headline passing measures"
    elif ml > hl: lead = f"Mendoza's 2025 line leads {ml} of {len(head)} headline passing measures"
    else: lead = f"Hoover and Mendoza split the {len(head)} headline passing measures"
    if ties: lead += f", with {ties} tied"
    minority = "hoover" if ml > hl else "mendoza"
    mn = names(minority)
    extra = (f"; {'Hoover' if minority == 'hoover' else 'Mendoza'} has the edge in {join(mn)}" if mn and hl != ml else "")
    diff_y = ht["yds"] - mt["yds"]; diff_t = ht["td"] - mt["td"]
    def part(v, unit): return f"{abs(v):,} {unit}"
    if diff_y < 0 and diff_t < 0:
        gap_s = f"Hoover trails Mendoza's game-{N} totals by {part(diff_y,'yards')} and {part(diff_t,'passing TD')}."
    elif diff_y > 0 and diff_t > 0:
        gap_s = f"Hoover is ahead of Mendoza's game-{N} totals by {part(diff_y,'yards')} and {part(diff_t,'passing TD')}."
    else:
        def one(v, unit): return f"even on {unit}" if v == 0 else f"{part(v, unit)} {'ahead' if v > 0 else 'behind'}"
        gap_s = f"Against Mendoza's game-{N} totals, Hoover is {one(diff_y,'yards')} and {one(diff_t,'passing TD')}."
    verdict = f"Through {N} game{'s' if N > 1 else ''}, {lead}{extra}. {gap_s}"

    # Pace vs Mendoza's full season
    SEASON_G = len(M)
    pace = []
    for key, label in [("yds", "Passing yards"), ("td", "Passing TD"), ("int", "Interceptions"), ("total_td", "Total TD")]:
        per = ht[key] / N
        pace.append({"key": key, "label": label, "to_date": ht[key], "pace": per * SEASON_G,
                     "mendoza_final": mfull[key], "share": ht[key] / mfull[key] if mfull[key] else None})

    # Game rows with per-game metrics and cumulative series
    opp_d = games.get("opp_pass_defense", {})
    def rows(gs, season):
        out, cum = [], {"yds": 0, "td": 0, "total_td": 0, "cmp": 0, "att": 0, "int": 0}
        rk = opp_d.get(str(season), {}).get("ranks", {})
        for i, g in enumerate(gs):
            for k in ("yds", "td", "cmp", "att", "int"): cum[k] += g[k]
            cum["total_td"] += g["td"] + g.get("rush_td", 0)
            r = dict(g)
            r.update({"n": i + 1, "pct": metric(g, "pct"), "ypa": metric(g, "ypa"), "rating": metric(g, "rating"),
                      "cum_yds": cum["yds"], "cum_td": cum["td"], "cum_total_td": cum["total_td"],
                      "cum_rating": rating(cum["cmp"], cum["att"], cum["yds"], cum["td"], cum["int"]),
                      "opp_d_rank": rk.get(g["opp"]) if g.get("level") == "FBS" else None})
            out.append(r)
        return out
    hrows, mrows = rows(H, games["hoover"]["season"]), rows(M, games["mendoza"]["season"])
    check(hrows[-1]["cum_yds"] == ht["yds"] and hrows[-1]["cum_td"] == ht["td"], "Hoover cumulative series does not reconcile")

    # National boards
    L = nat["latest"]
    hrow_nat = L["hoover_row"]
    check((hrow_nat["cmp"], hrow_nat["att"], hrow_nat["yds"], hrow_nat["td"], hrow_nat["int"]) ==
          (ht["cmp"], ht["att"], ht["yds"], ht["td"], ht["int"]) or hrow_nat["g"] < N,
          "cfbstats Hoover row disagrees with his game log")
    nat_current = hrow_nat["g"] >= N
    boards = {}
    for cat in CATS:
        b = L["boards"][cat]
        rws = []
        for r in b["rows"]:
            check(r["cmp"] <= r["att"], f"national {cat}: {r['name']} cmp > att")
            cr = rating(r["cmp"], r["att"], r["yds"], r["td"], r["int"])
            check(abs(cr - r["src_rating"]) < 0.06, f"national {cat}: {r['name']} rating {cr:.2f} != source {r['src_rating']} (transcription error?)")
            rws.append(dict(r, value=metric(r, cat), is_hoover=r["name"] == "Josh Hoover"))
        vals = [x["value"] for x in rws]
        for x in rws: x["rank"] = comp_rank(vals, x["value"])
        rws.sort(key=lambda x: (x["rank"], x["name"]))
        top = [x for x in rws if x["rank"] <= 5]
        check(len(top) >= 5, f"national {cat}: fewer than five leaders")
        hv = metric(hrow_nat, cat)
        in_top = any(x["is_hoover"] for x in top)
        tied = sum(1 for x in top if abs(x["value"] - hv) < 1e-9 and not x["is_hoover"]) > 0
        if in_top:
            hrank = next(x["rank"] for x in top if x["is_hoover"])
            check(hrank == b["hoover_rank"], f"national {cat}: computed Hoover rank {hrank} != source {b['hoover_rank']}")
        else:
            hrank = b["hoover_rank"]
            check(hrank > 5, f"national {cat}: Hoover rank {hrank} but not in top-five rows")
        boards[cat] = {"label": CAT_LABEL[cat], "source_url": b["source_url"], "qualified": b.get("qualified", False),
                       "top": top, "hoover": dict(hrow_nat, value=hv, rank=hrank, tied=tied, in_top=in_top)}
    rank_hist = nat["rank_history"]
    last_hist = rank_hist[-1]
    for cat in CATS:
        if cat in last_hist["ranks"] and last_hist["through"] == L["data_through"]:
            check(last_hist["ranks"][cat] == boards[cat]["hoover"]["rank"], f"rank history {cat} disagrees with board")

    # Heisman
    latest_by_book = {}
    for s in sorted(heis["snapshots"], key=lambda s: s["as_of"]):
        latest_by_book[s["book"]] = s
    newest = max(s["as_of"] for s in latest_by_book.values())
    stale_books = [b for b, s in latest_by_book.items()
                   if (datetime.date.fromisoformat(newest) - datetime.date.fromisoformat(s["as_of"])).days > 10]
    for b in stale_books: del latest_by_book[b]
    books = sorted(latest_by_book.values(), key=lambda s: s["book"])
    players = []
    for name, info in heis["players"].items():
        odds = {s["book"]: s["odds"].get(name) for s in books}
        probs = [american_to_prob(o) for o in odds.values() if o is not None]
        if not probs: continue
        players.append({"name": name, **info, "odds": odds, "prob": statistics.median(probs), "n_books": len(probs)})
    players.sort(key=lambda p: -p["prob"])
    pv = [round(p["prob"], 6) for p in players]
    for p in players: p["rank"] = comp_rank(pv, round(p["prob"], 6))
    hp = next((p for p in players if p["name"] == "Josh Hoover"), None)
    trail = [{"date": "preseason", "book": heis["hoover_opening"]["book"], "odds": heis["hoover_opening"]["odds"], "url": heis["hoover_opening"]["source_url"]}]
    for s in sorted(heis["snapshots"], key=lambda s: (s["as_of"], s["book"])):
        if "Josh Hoover" in s["odds"]:
            trail.append({"date": s["as_of"], "book": s["book"], "odds": s["odds"]["Josh Hoover"], "url": s["url"], "outlet": s["outlet"]})
    qb_rank = [p["name"] for p in players if p["pos"] == "QB" and p["name"] != "Josh Hoover"]
    expected_field = qb_rank[:4]
    players = [p for p in players if p["rank"] <= 12 or p["name"] == "Josh Hoover"]

    # Heisman QB field (cohort) charts
    cohort = []
    for q in coh["qbs"]:
        for g in q["games"]: validate_game(g, q["name"])
        ordered_unique(q["games"], q["name"])
        cohort.append({"name": q["name"], "school": q["school"], "games": rows(q["games"], None)})
    cohort.insert(0, {"name": "Josh Hoover", "school": "Indiana", "games": hrows, "is_hoover": True})
    # cross-check cohort logs against the national rows where both exist
    all_nat = {r["name"]: r for b in L["boards"].values() for r in b["rows"]}
    for q in cohort[1:]:
        t = totals(q["games"])
        if q["name"] in all_nat and all_nat[q["name"]]["g"] == len(q["games"]):
            r = all_nat[q["name"]]
            check((t["cmp"], t["att"], t["yds"], t["td"], t["int"]) == (r["cmp"], r["att"], r["yds"], r["td"], r["int"]),
                  f"cohort {q['name']}: game log totals disagree with cfbstats")

    caveats = []
    lr_path = os.path.join(root, "data", "last_run.json")
    if os.path.exists(lr_path):
        lr = json.load(open(lr_path))
        if lr.get("failed"):
            caveats.append("The latest automatic update could not refresh: " + ", ".join(lr["failed"]) + ". Those sections show the last verified data.")
    if stale_books:
        caveats.append("Odds older than 10 days are hidden: " + ", ".join(stale_books) + ".")
    have = {q["name"] for q in coh["qbs"]}
    if set(expected_field) != have:
        caveats.append("The Heisman QB field chart shows " + ", ".join(sorted(have)) + "; by the latest odds the top four QBs are " + ", ".join(expected_field) + ". The chart updates on the next refresh.")
    if not nat_current:
        caveats.append(f"National leaderboards are through {L['data_through']} and do not yet include Hoover's latest game.")
    if hp and hp["n_books"] < len(books):
        caveats.append("Some books did not list every contender; missing odds show as a dash.")
    caveats.append("Opponent pass-defense ranks for 2026 opponents are early-season figures and will move week to week.")
    if len([h for h in rank_hist if len(h["ranks"]) == 5]) < 3:
        caveats.append(f"National rank history starts {rank_hist[0]['through']}; each weekly refresh adds a point.")

    sources = [
        {"label": "ESPN: Josh Hoover 2026 game log", "url": games["hoover"]["source_url"]},
        {"label": "FOX Sports: Fernando Mendoza 2025 game log", "url": games["mendoza"]["source_url"]},
        {"label": "cfbstats.com: 2026 national passing leaders", "url": "https://cfbstats.com/2026/leader/national/player/split01/category02/sort08.html"},
        {"label": "cfbstats.com: team passing defense (2025 final, 2026 current)", "url": opp_d.get("2026", {}).get("source_url", "https://cfbstats.com")},
    ] + [{"label": f"{s['outlet']}: {s['book']} Heisman odds, {s['as_of']}", "url": s["url"]} for s in sorted(heis["snapshots"], key=lambda s: s["as_of"])] \
      + [{"label": f"ESPN: {q['name']} 2026 game log", "url": f"https://www.espn.com/college-football/player/gamelog/_/id/{q['espn_id']}"} for q in coh["qbs"]]

    # data freshness: what each section's data covers and when it was last successfully checked
    fp = os.path.join(root, "data", "freshness.json")
    fr = json.load(open(fp)) if os.path.exists(fp) else {}
    last_game = H[-1]
    cohort_last = max((g["date"] for q in coh["qbs"] for g in q["games"]), default=None)
    def d(iso): return datetime.date.fromisoformat(iso).strftime("%b %-d") if iso else "?"
    fresh = {
        "games": {"what": f"Game data through {d(last_game['date'])} vs {last_game['opp']}",
                  "checked": fr.get("hoover") or games["hoover"].get("retrieved_at")},
        "national": {"what": f"Leaderboards through {d(L['data_through'])} games",
                     "checked": fr.get("national") or L.get("retrieved_at")},
        "field": {"what": f"Contender game logs through {d(cohort_last)}",
                  "checked": fr.get("cohort") or coh.get("retrieved_at")},
        "heisman": {"what": "Odds as published: " + ", ".join(f"{s['book']} {d(s['as_of'])}" for s in books),
                    "checked": fr.get("heisman")},
    }
    checks = [v["checked"] for v in fresh.values() if v["checked"]]
    fresh["checked_any"] = max(checks, key=lambda x: datetime.datetime.fromisoformat(x)) if checks else None
    now = datetime.datetime.fromisoformat(as_of)
    for k, v in fresh.items():
        if isinstance(v, dict) and v["checked"]:
            v["stale"] = (now - datetime.datetime.fromisoformat(v["checked"])).days >= 5

    model = {
        "fresh": fresh,
        "as_of": as_of, "N": N, "season_games_mendoza": SEASON_G,
        "latest": hrows[-1], "next_game": games.get("next_game"),
        "hoover": {"rows": hrows, "totals": ht}, "mendoza": {"rows": mrows, "totals": mt, "season": mfull},
        "h2h": h2h, "verdict": verdict, "leads": {"hoover": hl, "mendoza": ml, "tie": ties},
        "pace": pace,
        "national": {"data_through": L["data_through"], "current": nat_current, "boards": boards,
                     "qualifier_note": nat["qualifier_note"], "rank_history": rank_hist, "order": CATS},
        "heisman": {"books": [{"book": s["book"], "as_of": s["as_of"], "outlet": s["outlet"], "url": s["url"]} for s in books],
                    "players": players, "hoover": hp, "trail": trail, "note": heis["note"]},
        "cohort": {"rule": coh["rule"], "qbs": cohort},
        "opp_d_method": opp_d.get("method"),
        "caveats": caveats, "sources": sources,
    }
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", default="report.html")
    ap.add_argument("--standalone", action="store_true", help="wrap in a full HTML document (for GitHub Pages)")
    ap.add_argument("--as-of", default=datetime.datetime.now(ZoneInfo("America/Indiana/Indianapolis")).isoformat(timespec="minutes"))
    a = ap.parse_args()
    model = build(a.root, a.as_of)
    if ERRORS:
        print("VALIDATION FAILED - report not written:", file=sys.stderr)
        for e in ERRORS: print("  -", e, file=sys.stderr)
        sys.exit(1)
    tpl = open(os.path.join(a.root, "template.html")).read()
    blob = json.dumps(model, separators=(",", ":")).replace("</", "<\\/")
    html = tpl.replace("/*__MODEL__*/null", blob)
    for bad in ("TODO", "lorem", "PLACEHOLDER", "ghp_", "Bearer "):
        if bad in html: print(f"VALIDATION FAILED - found '{bad}' in output", file=sys.stderr); sys.exit(1)
    if a.standalone:
        html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>'
                '</head><body>\n' + html + '\n</body></html>\n')
    tmp = a.out + ".tmp"
    open(tmp, "w").write(html)
    os.replace(tmp, a.out)
    print(f"OK  games={model['N']}  verdict: {model['verdict']}")
    print(f"    sha256={hashlib.sha256(html.encode()).hexdigest()[:16]}  bytes={len(html)}")


if __name__ == "__main__":
    main()
