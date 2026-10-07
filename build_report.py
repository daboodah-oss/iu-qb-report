#!/usr/bin/env python3
"""Build the IU QB Report: the current season's Indiana QB against the earlier
Cignetti-era starters (roster.json), game for game.

Reads data/*.json, validates every row, computes one model object, and writes
report.html (template.html with the model injected). No network access.

Usage:  python3 build_report.py [--root DIR] [--out report.html] [--as-of ISO]
Exit code is non-zero if any validation check fails; nothing is written then.
"""
import argparse, json, statistics, sys, datetime, hashlib, os
from html import escape
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


HEADLINE = [("yds", "Passing yards", True, 0), ("td", "Passing TD", True, 0),
            ("pct", "Completion %", True, 1), ("rating", "Passer rating", True, 1),
            ("ypa", "Yards per attempt", True, 1), ("int", "Interceptions", False, 0),
            ("rush_yds", "Rushing yards", True, 0), ("total_td", "Total TD (pass + rush)", True, 0)]


def gap_phrase(dy, dt, who):
    """'107 yards and 1 passing TD behind Mendoza', '20 yards ahead of Rourke but 1 passing TD behind', ..."""
    y, t = (f"{abs(dy):,} yards", dy), (f"{abs(dt)} passing TD", dt)
    rel = lambda v: f"ahead of {who}" if v > 0 else f"behind {who}"
    if dy == 0 and dt == 0: return f"even with {who} on yards and passing TD"
    if dy == 0 or dt == 0:
        z, nz = ("yards", t) if dy == 0 else ("passing TD", y)
        return f"even with {who} on {z} and {nz[0]} {'ahead' if nz[1] > 0 else 'behind'}"
    if (dy > 0) == (dt > 0): return f"{y[0]} and {t[0]} {rel(dy)}"
    return f"{y[0]} {rel(dy)} but {t[0]} {'ahead' if dt > 0 else 'behind'}"


def join(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def source_label(url):
    return "FOX Sports" if "foxsports" in url else "ESPN" if "espn" in url else url.split("/")[2]


def build(root, as_of):
    D = lambda f: json.load(open(os.path.join(root, "data", f)))
    games, nat, heis, coh = D("games.json"), D("national.json"), D("heisman.json"), D("cohort.json")
    roster = json.load(open(os.path.join(root, "roster.json")))

    # Quarterbacks: the newest roster season is the current QB; earlier seasons are comparison QBs (newest first).
    cfg = sorted(roster["qbs"], key=lambda q: -q["season"])
    check(len({q["season"] for q in cfg}) == len(cfg), "roster.json: two quarterbacks share a season")
    cur_cfg, prev_cfg = cfg[0], cfg[1:]
    C = games.get(cur_cfg["key"], {}).get("games", [])
    for g in C: validate_game(g, cur_cfg["short"])
    ordered_unique(C, cur_cfg["short"])
    N = len(C)
    check(N >= 1, f"no {cur_cfg['short']} games")
    if N < 1:
        return None
    ct = totals(C)

    prev, missing = [], []
    for q in prev_cfg:
        G = games.get(q["key"], {}).get("games", [])
        if not G:
            missing.append(q); continue
        for g in G: validate_game(g, q["short"])
        ordered_unique(G, q["short"])
        full = totals(G)
        ft = q.get("final_totals")
        if ft:
            check({k: full[k] for k in ft} == ft, f"{q['name']} {q['season']} season totals do not reconcile to roster.json final_totals")
        prev.append({"cfg": q, "games": G, "totals": totals(G[:N]), "full": full, "short_of_n": len(G) < N})

    # Regression fixture (4-game values verified 2026-09-26)
    if cur_cfg["key"] == "hoover" and N == 4:
        mt = next(p["totals"] for p in prev if p["cfg"]["key"] == "mendoza")
        check((mt["cmp"], mt["att"], mt["yds"], mt["td"]) == (76, 99, 975, 14), "fixture: Mendoza 4-game totals changed")
        check((ct["cmp"], ct["att"], ct["yds"], ct["td"]) == (56, 80, 850, 11), "fixture: Hoover 4-game totals changed")
        check(abs(mt["rating"] - 206.2) < 0.06 and abs(ct["rating"] - 204.6) < 0.06, "fixture: ratings changed")

    # Head to head: every QB through the same number of games. A QB whose season was shorter than N shows
    # his full season but is left out of the leader box.
    h2h = []
    for key, label, hb, dp in HEADLINE:
        vals = {cur_cfg["key"]: ct[key], **{p["cfg"]["key"]: p["totals"][key] for p in prev}}
        comparable = [cur_cfg["key"]] + [p["cfg"]["key"] for p in prev if not p["short_of_n"]]
        r = {k: round(vals[k], dp) for k in comparable}
        best = (max if hb else min)(r.values())
        leaders = [k for k in comparable if r[k] == best]
        if len(leaders) == len(comparable): leaders = []  # everyone level: no leader
        h2h.append({"key": key, "label": label, "values": vals, "dp": dp, "higher_better": hb,
                    "leaders": leaders, "headline": key in CATS})
    head = [x for x in h2h if x["headline"]]
    leads, lead_parts, gap_parts = {}, [], []
    cs = cur_cfg["short"]
    for p in prev:
        k = p["cfg"]["key"]
        def beats(x, a, b):
            ra, rb = round(x["values"][a], x["dp"]), round(x["values"][b], x["dp"])
            return ra != rb and (ra > rb) == x["higher_better"]
        w = sum(1 for x in head if beats(x, cur_cfg["key"], k))
        l = sum(1 for x in head if beats(x, k, cur_cfg["key"]))
        t = len(head) - w - l
        leads[k] = {"cur": w, "prev": l, "tie": t}
        who = f"{p['cfg']['short']}'s {p['cfg']['season']} line"
        if p["short_of_n"]:
            who = f"{p['cfg']['short']}'s full {p['cfg']['season']} season ({len(p['games'])} games)"
        lead_parts.append(f"{who} in {w} of {len(head)}" + (f" ({t} tied)" if t else ""))
        gap_parts.append(gap_phrase(ct["yds"] - p["totals"]["yds"], ct["td"] - p["totals"]["td"], p["cfg"]["short"]))
    if prev:
        verdict = (f"Through {N} game{'s' if N > 1 else ''}, {cs} leads {join(lead_parts)} headline passing measures. "
                   f"At the same point he is {join(gap_parts)}.")
    else:
        verdict = f"Through {N} game{'s' if N > 1 else ''}, {cs} has {ct['yds']:,} passing yards and {ct['td']} passing TD."

    # Pace: the current per-game average stretched over the most recent completed season's length
    basis = prev[0] if prev else None
    SEASON_G = len(basis["games"]) if basis else N
    pace = []
    for key, label in [("yds", "Passing yards"), ("td", "Passing TD"), ("int", "Interceptions"), ("total_td", "Total TD")]:
        pace.append({"key": key, "label": label, "to_date": ct[key], "pace": ct[key] / N * SEASON_G,
                     "finals": [{"key": p["cfg"]["key"], "value": p["full"][key], "games": len(p["games"])} for p in prev]})

    # Game rows with per-game metrics and cumulative series
    opp_d = games.get("opp_pass_defense", {})
    def rows(gs, season):
        out, cum = [], {"yds": 0, "td": 0, "total_td": 0, "cmp": 0, "att": 0, "int": 0, "tot_yds": 0, "tot_td": 0}
        rk = opp_d.get(str(season), {}).get("ranks", {})
        for i, g in enumerate(gs):
            for k in ("yds", "td", "cmp", "att", "int"): cum[k] += g[k]
            cum["total_td"] += g["td"] + g.get("rush_td", 0)
            ty = g["yds"] + g.get("rush_yds", 0) + g.get("rec_yds", 0)
            tt = g["td"] + g.get("rush_td", 0) + g.get("rec_td", 0)
            cum["tot_yds"] += ty; cum["tot_td"] += tt
            r = dict(g)
            r.update({"tot_yds": ty, "tot_td": tt, "cum_tot_yds": cum["tot_yds"], "cum_tot_td": cum["tot_td"]})
            r.update({"n": i + 1, "pct": metric(g, "pct"), "ypa": metric(g, "ypa"), "rating": metric(g, "rating"),
                      "cum_yds": cum["yds"], "cum_td": cum["td"], "cum_total_td": cum["total_td"],
                      "cum_rating": rating(cum["cmp"], cum["att"], cum["yds"], cum["td"], cum["int"]),
                      "opp_d_rank": rk.get(g["opp"]) if g.get("level") == "FBS" else None})
            out.append(r)
        return out
    crows = rows(C, cur_cfg["season"])
    check(crows[-1]["cum_yds"] == ct["yds"] and crows[-1]["cum_td"] == ct["td"], f"{cs} cumulative series does not reconcile")
    PALETTE = ["p1", "p2", "p3", "p4"]  # CSS color slots for comparison QBs, newest first
    check(len(prev) <= len(PALETTE), "more comparison QBs than chart colors; add a slot to template.html")
    def qb_model(q, rws, tot, slot, **kw):
        blk = games.get(q["key"], {})
        return {"key": q["key"], "name": q["name"], "short": q["short"], "season": q["season"], "note": q.get("note", ""),
                "slot": slot, "rows": rws, "totals": tot, "games": len(rws),
                "source": source_label(blk.get("source_url", "espn")), "source_url": blk.get("source_url", ""), **kw}
    cur_m = qb_model(cur_cfg, crows, ct, "cur")
    prev_m = [qb_model(p["cfg"], rows(p["games"], p["cfg"]["season"]), p["totals"], PALETTE[i],
                       season_totals=p["full"], short_of_n=p["short_of_n"]) for i, p in enumerate(prev[:len(PALETTE)])]

    # National boards
    L = nat["latest"]
    hrow_nat = L["hoover_row"]  # legacy field name: always the current QB's cfbstats row
    check((hrow_nat["cmp"], hrow_nat["att"], hrow_nat["yds"], hrow_nat["td"], hrow_nat["int"]) ==
          (ct["cmp"], ct["att"], ct["yds"], ct["td"], ct["int"]) or hrow_nat["g"] < N,
          f"cfbstats {cs} row disagrees with his game log")
    nat_current = hrow_nat["g"] >= N
    boards = {}
    for cat in CATS:
        b = L["boards"][cat]
        rws = []
        for r in b["rows"]:
            check(r["cmp"] <= r["att"], f"national {cat}: {r['name']} cmp > att")
            cr = rating(r["cmp"], r["att"], r["yds"], r["td"], r["int"])
            check(abs(cr - r["src_rating"]) < 0.06, f"national {cat}: {r['name']} rating {cr:.2f} != source {r['src_rating']} (transcription error?)")
            rws.append(dict(r, value=metric(r, cat), is_cur=r["name"] == cur_cfg["name"]))
        vals = [x["value"] for x in rws]
        for x in rws: x["rank"] = comp_rank(vals, x["value"])
        rws.sort(key=lambda x: (x["rank"], x["name"]))
        top = [x for x in rws if x["rank"] <= 5]
        check(len(top) >= 5, f"national {cat}: fewer than five leaders")
        hv = metric(hrow_nat, cat)
        in_top = any(x["is_cur"] for x in top)
        tied = sum(1 for x in top if abs(x["value"] - hv) < 1e-9 and not x["is_cur"]) > 0
        if in_top:
            hrank = next(x["rank"] for x in top if x["is_cur"])
            check(hrank == b["hoover_rank"], f"national {cat}: computed {cs} rank {hrank} != source {b['hoover_rank']}")
        else:
            hrank = b["hoover_rank"]
            check(hrank > 5, f"national {cat}: {cs} rank {hrank} but not in top-five rows")
        boards[cat] = {"label": CAT_LABEL[cat], "source_url": b["source_url"], "qualified": b.get("qualified", False),
                       "top": top, "cur": dict(hrow_nat, value=hv, rank=hrank, tied=tied, in_top=in_top)}
    rank_hist = nat["rank_history"]
    last_hist = rank_hist[-1]
    for cat in CATS:
        if cat in last_hist["ranks"] and last_hist["through"] == L["data_through"]:
            check(last_hist["ranks"][cat] == boards[cat]["cur"]["rank"], f"rank history {cat} disagrees with board")

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
    CN = cur_cfg["name"]
    hp = next((p for p in players if p["name"] == CN), None)
    opening = heis.get(f"{cur_cfg['key']}_opening")  # e.g. hoover_opening: the current QB's preseason line
    trail = [{"date": "preseason", "book": opening["book"], "odds": opening["odds"], "url": opening["source_url"]}] if opening else []
    for s in sorted(heis["snapshots"], key=lambda s: (s["as_of"], s["book"])):
        if CN in s["odds"]:
            trail.append({"date": s["as_of"], "book": s["book"], "odds": s["odds"][CN], "url": s["url"], "outlet": s["outlet"]})
    qb_rank = [p["name"] for p in players if p["name"] != CN]
    expected_field = qb_rank[:4]
    players = [dict(p, is_cur=p["name"] == CN) for p in players if p["rank"] <= 12 or p["name"] == CN]

    # Heisman QB field (cohort) charts
    cohort = []
    for q in coh["qbs"]:
        for g in q["games"]: validate_game(g, q["name"])
        ordered_unique(q["games"], q["name"])
        pos = q.get("pos") or heis["players"].get(q["name"], {}).get("pos", "?")
        cohort.append({"name": q["name"], "school": q["school"], "pos": pos, "games": rows(q["games"], None)})
    cohort.insert(0, {"name": CN, "school": roster.get("team", "Indiana"), "pos": "QB", "games": crows, "is_cur": True})
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
        caveats.append("The Heisman field chart shows " + ", ".join(sorted(have)) + "; by the latest odds the top four candidates are " + ", ".join(expected_field) + ". The chart updates on the next refresh.")
    if not nat_current:
        caveats.append(f"National leaderboards are through {L['data_through']} and do not yet include {cs}'s latest game.")
    for q in missing:
        caveats.append(f"{q['name']}'s {q['season']} game log has not been collected yet, so he is not on the page; the next full refresh adds it.")
    for p in prev_m:
        if p["short_of_n"]:
            caveats.append(f"{p['name']} played {p['games']} games in {p['season']}, so his columns show his full season, not {N} games, and he is left out of the leader boxes.")
    if hp and hp["n_books"] < len(books):
        caveats.append("Some books did not list every contender; missing odds show as a dash.")
    caveats.append(f"Opponent pass-defense ranks for {cur_cfg['season']} opponents are in-season figures and will move week to week.")
    if len([h for h in rank_hist if len(h["ranks"]) == 5]) < 3:
        caveats.append(f"National rank history starts {rank_hist[0]['through']}; each weekly refresh adds a point.")

    yrs = lambda xs: ", ".join(str(x) for x in xs)
    sources = [{"label": f"{q['source']}: {q['name']} {q['season']} game log", "url": q["source_url"]} for q in [cur_m] + prev_m] + [
        {"label": f"cfbstats.com: {cur_cfg['season']} national passing leaders", "url": f"https://cfbstats.com/{cur_cfg['season']}/leader/national/player/split01/category02/sort08.html"},
        {"label": f"cfbstats.com: team passing defense ({yrs([p['season'] for p in prev_m][::-1])} final, {cur_cfg['season']} current)",
         "url": opp_d.get(str(cur_cfg["season"]), {}).get("source_url", "https://cfbstats.com")},
    ] + [{"label": f"{s['outlet']}: {s['book']} Heisman odds, {s['as_of']}", "url": s["url"]} for s in sorted(heis["snapshots"], key=lambda s: s["as_of"])] \
      + [{"label": f"ESPN: {q['name']} {cur_cfg['season']} game log", "url": f"https://www.espn.com/college-football/player/gamelog/_/id/{q['espn_id']}"} for q in coh["qbs"]]

    # data freshness: what each section's data covers and when it was last successfully checked
    fp = os.path.join(root, "data", "freshness.json")
    fr = json.load(open(fp)) if os.path.exists(fp) else {}
    last_game = C[-1]
    cohort_last = max((g["date"] for q in coh["qbs"] for g in q["games"]), default=None)
    def d(iso): return datetime.date.fromisoformat(iso).strftime("%b %-d") if iso else "?"
    fresh = {
        "games": {"what": f"Game data through {d(last_game['date'])} vs {last_game['opp']}",
                  "checked": fr.get("games") or fr.get("hoover") or games[cur_cfg["key"]].get("retrieved_at")},
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

    # Prominent data-quality flags (a short, visible subset of the caveats).
    notices = []
    if os.path.exists(lr_path):
        _lr = json.load(open(lr_path))
        if _lr.get("failed"):
            notices.append("The latest automatic update could not refresh: " + ", ".join(_lr["failed"]) +
                           ". Those sections show the last verified data.")
    if not nat_current:
        notices.append(f"National leaderboards are through {L['data_through']} and do not include {cs}'s latest game yet.")
    for q in missing:
        notices.append(f"{q['name']} ({q['season']}) is not on the page yet: his game log has not been collected.")
    _stale_names = {"games": "Game data", "national": "National leaderboards",
                    "field": "Heisman-field game logs", "heisman": "Heisman odds"}
    for _k, _v in fresh.items():
        if isinstance(_v, dict) and _v.get("stale"):
            notices.append(f"{_stale_names.get(_k, _k)} has not refreshed in over 5 days "
                           f"(last checked {_v['checked'][:10]}).")

    # Most recent change in the current QB's odds trail, for a one-line narrative.
    move = None
    for i in range(len(trail) - 1, 0, -1):
        if trail[i]["odds"] != trail[i - 1]["odds"]:
            move = {"book": trail[i]["book"], "from": trail[i - 1]["odds"],
                    "to": trail[i]["odds"], "date": trail[i]["date"]}
            break

    model = {
        "fresh": fresh,
        "as_of": as_of, "N": N, "team": roster.get("team", "Indiana"), "coach": roster.get("coach", ""),
        "latest": crows[-1], "next_game": games.get("next_game"),
        "cur": cur_m, "prev": prev_m,
        "h2h": h2h, "verdict": verdict, "leads": leads,
        "pace": pace, "pace_games": SEASON_G, "pace_basis": prev_m[0]["key"] if prev_m else None,
        "national": {"data_through": L["data_through"], "current": nat_current, "boards": boards,
                     "qualifier_note": nat["qualifier_note"], "rank_history": rank_hist, "order": CATS},
        "heisman": {"books": [{"book": s["book"], "as_of": s["as_of"], "outlet": s["outlet"], "url": s["url"]} for s in books],
                    "players": players, "cur": hp, "trail": trail, "note": heis["note"], "move": move},
        "cohort": {"rule": "The four players with the best consensus Heisman odds, any position. Game logs from ESPN.", "qbs": cohort},
        "opp_d_method": "Opponent's national rank in passing yards allowed per game (cfbstats.com, FBS). Completed seasons use final ranks; "
                        f"{cur_cfg['season']} opponents use the current rank, which moves every week.",
        "caveats": caveats, "notices": notices, "sources": sources,
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
    if ERRORS or model is None:
        print("VALIDATION FAILED - report not written:", file=sys.stderr)
        for e in ERRORS: print("  -", e, file=sys.stderr)
        sys.exit(1)
    tpl = open(os.path.join(a.root, "template.html")).read()
    blob = json.dumps(model, separators=(",", ":")).replace("</", "<\\/")
    html = tpl.replace("/*__MODEL__*/null", blob)
    for bad in ("TODO", "lorem", "PLACEHOLDER", "ghp_", "Bearer "):
        if bad in html: print(f"VALIDATION FAILED - found '{bad}' in output", file=sys.stderr); sys.exit(1)
    if a.standalone:
        c, pv = model["cur"], model["prev"]
        og_title = escape(f"IU QB Report: {c['short']} vs the Cignetti era")
        og_desc = escape(f"{c['name']}'s {c['season']} season against " +
                         (join([f"{p['name']} ({p['season']})" for p in pv]) if pv else "earlier Indiana starters") +
                         ", game for game, plus national ranks and the Heisman race.")
        html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                '<link rel="icon" type="image/png" sizes="32x32" href="icons/favicon-32.png">'
                '<link rel="icon" type="image/png" sizes="192x192" href="icons/icon-192.png">'
                '<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">'
                '<meta name="theme-color" content="#990000">'
                f'<meta property="og:title" content="{og_title}">'
                f'<meta property="og:description" content="{og_desc}">'
                '<meta property="og:image" content="https://qb.daboodah.com/icons/og.png">'
                '<meta property="og:url" content="https://qb.daboodah.com/">'
                '<meta name="twitter:card" content="summary_large_image">'
                '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>'
                '</head><body>\n' + html + '\n</body></html>\n')
    tmp = a.out + ".tmp"
    open(tmp, "w").write(html)
    os.replace(tmp, a.out)
    print(f"OK  games={model['N']}  verdict: {model['verdict']}")
    print(f"    sha256={hashlib.sha256(html.encode()).hexdigest()[:16]}  bytes={len(html)}")


if __name__ == "__main__":
    main()
