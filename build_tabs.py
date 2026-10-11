#!/usr/bin/env python3
"""Models for the RB, WR and Team tabs and the site title.  No network.  Called by build_report.py.

Every number is recomputed from the stored rows in data/team.json, data/skill.json and
data/skill_national.json (checked when they were stored, re-checked here).  A tab whose data has
not been collected yet renders a short 'not collected yet' notice instead of failing the build.
"""
import datetime, json, os, re

SHORT = {"Rushing yards": "Rush yds", "Rushing TD": "Rush TD", "Yards per carry": "Yds/carry", "Yards per game": "Yds/game", "Receptions": "Rec",
         "Receiving yards": "Rec yds", "Receiving TD": "Rec TD", "Yards per catch": "Yds/catch", "Record": "Record", "Points scored": "Pts for",
         "Points allowed": "Pts against", "Total yards": "Total yds", "Passing yards": "Pass yds", "Turnover margin": "TO +/-", "Third-down %": "3rd down %"}
SKILL = {
    "rb": {"label": "Running backs", "noun": "backs", "count": ("att", "Car"),
           "stats": [("yds", "Rushing yards", 0, True), ("td", "Rushing TD", 0, True), ("ypc", "Yards per carry", 2, True), ("ypg", "Yards per game", 1, True)],
           "chart": [("yds", "Rush yds"), ("td", "Rush TD"), ("ypc", "YPC"), ("ypg", "Yds/game"), ("att", "Carries")],
           "board_order": ["yds", "td", "ypc", "ypg"]},
    "wr": {"label": "Wide receivers", "noun": "receivers", "count": ("rec", "Rec"),
           "stats": [("rec", "Receptions", 0, True), ("yds", "Receiving yards", 0, True), ("td", "Receiving TD", 0, True), ("ypr", "Yards per catch", 2, True), ("ypg", "Yards per game", 1, True)],
           "chart": [("yds", "Rec yds"), ("rec", "Receptions"), ("td", "Rec TD"), ("ypr", "Yds/catch"), ("ypg", "Yds/game")],
           "board_order": ["rec", "yds", "td", "ypr", "ypg"]},
}
TEAM_STATS = [("wins", "Record", 0, True), ("pf", "Points scored", 0, True), ("pa", "Points allowed", 0, False),
              ("total_yds", "Total yards", 0, True), ("rush_yds", "Rushing yards", 0, True), ("pass_yds", "Passing yards", 0, True),
              ("to_margin", "Turnover margin", 0, True), ("third_pct", "Third-down %", 1, True)]
PALETTE = ["p1", "p2", "p3", "p4"]
AP_SLOTS = ["a1", "a2", "a3", "a4", "a5"]


def short_name(name):
    parts = [p for p in re.sub(r"[.,]", "", name).split() if p.lower() not in ("jr", "sr", "ii", "iii", "iv")]
    return parts[-1] if parts else name


def load(root, f, default):
    p = os.path.join(root, "data", f)
    return json.load(open(p)) if os.path.exists(p) else default


# ------------------------------------------------------------------ RB / WR
def skill_rows(games, ck):
    out, c = [], {"n": 0, "yds": 0, "td": 0}
    for i, g in enumerate(games):
        c["n"] += g[ck]; c["yds"] += g["yds"]; c["td"] += g["td"]
        n = i + 1
        out.append(dict(g, n=n, per=g["yds"] / g[ck] if g[ck] else None,
                        cum_n=c["n"], cum_yds=c["yds"], cum_td=c["td"],
                        cum_per=c["yds"] / c["n"] if c["n"] else None, cum_ypg=c["yds"] / n))
    return out


def skill_totals(games, ck):
    t = {"games": len(games), ck: sum(g[ck] for g in games), "yds": sum(g["yds"] for g in games), "td": sum(g["td"] for g in games)}
    per = t["yds"] / t[ck] if t[ck] else None
    t.update({"ypc": per, "ypr": per, "ypg": t["yds"] / len(games) if games else None})
    return t


def skill_tab(tab, sk, nat, check, cur_season, fresh):
    spec = SKILL[tab]; ck = spec["count"][0]
    stored = (sk.get(tab) or {}).get("players", [])
    if not stored:
        return {"status": "pending", "label": spec["label"], "message": f"{spec['label']} data has not been collected yet; the next full refresh adds it."}
    seasons = sorted({p["season"] for p in stored}, reverse=True)
    players = []
    for si, season in enumerate(seasons):
        group = [p for p in stored if p["season"] == season]
        for di, p in enumerate(group):
            tag = f"{tab} {p['name']} {season}"
            dates = [g["date"] for g in p["games"]]
            check(dates == sorted(dates) and len(set(dates)) == len(dates), f"{tag}: games out of order or duplicated")
            for g in p["games"]:
                check(all(isinstance(g.get(k), int) for k in (ck, "yds", "td")) and g[ck] >= 0 and g["td"] >= 0, f"{tag} {g.get('date')}: bad stat line")
            row = p.get("cfbstats_row")
            if row:
                check(all(sum(g[k] for g in p["games"]) == row[k] for k in (ck, "yds", "td")), f"{tag}: game log no longer matches cfbstats season row")
            slot = "cur" if season == cur_season else PALETTE[min(si - (1 if seasons[0] == cur_season else 0), len(PALETTE) - 1)]
            players.append({"name": p["name"], "short": short_name(p["name"]), "season": season, "role": p["role"],
                            "slot": slot, "dash": di % 2 == 1, "rows": skill_rows(p["games"], ck),
                            "games": len(p["games"]), "full": skill_totals(p["games"], ck), "chosen": p.get("chosen", ""),
                            "checked": (f"matches cfbstats season totals through {p['cfbstats_through']}" + (f", except {'; '.join(p['check_diff'])}" if p.get("check_diff") else "") if row else
                                        f"cfbstats not caught up yet (through {p.get('cfbstats_through')})"),
                            "source_url": p.get("cfbstats_url")})
    cur = [p for p in players if p["season"] == cur_season]
    if not cur:
        return {"status": "pending", "label": spec["label"], "message": f"No {cur_season} {spec['noun']} have been collected yet."}
    N = max(p["games"] for p in cur)
    for p in players:
        p["totals"] = skill_totals([r for r in p["rows"]][:N], ck)
        p["short_of_n"] = p["games"] < N
        if p["season"] == cur_season: p.pop("full")
    # head to head (through N games): leader per stat among players who reached N games
    h2h = []
    for key, label, dp, hb in spec["stats"]:
        vals = {i: p["totals"][key] for i, p in enumerate(players)}
        comp = [i for i, p in enumerate(players) if not p["short_of_n"] and vals[i] is not None]
        r = {i: round(vals[i], dp) for i in comp}
        best = (max if hb else min)(r.values()) if r else None
        leaders = [i for i in comp if r[i] == best]
        if len(leaders) == len(comp): leaders = []
        h2h.append({"key": key, "label": label, "dp": dp, "leaders": leaders})
    parts = []
    for s in h2h:
        if not s["leaders"]: continue
        who = " and ".join(f"{players[i]['short']} ({players[i]['season']})" for i in s["leaders"])
        v = players[s["leaders"][0]]["totals"][s["key"]]
        parts.append(f"{s['label']}: {who} {v:,.{s['dp']}f}")
    cur_names = " and ".join(p["short"] for p in cur)
    lede = (f"Every {spec['noun'][:-1]} lined up by his own game count, through {N} game{'s' if N > 1 else ''}. "
            + (f"Leaders: {'; '.join(parts)}." if parts else "No single leader yet."))
    # national boards
    L = (nat.get(tab) or {}).get("latest")
    national = None
    if L:
        boards = []
        for key in spec["board_order"]:
            b = L["boards"].get(key)
            if not b: continue
            check(len(b["top"]) >= 5, f"{tab} national {key}: fewer than five leaders")
            boards.append({"key": key, "label": b["label"], "source_url": b["source_url"], "qualified": b.get("qualified"),
                           "top": b["top"], "players": [{"name": p["name"], "short": p["short"], "dash": p["dash"],
                                                         **(b["players"].get(p["name"]) or {"rank": None})} for p in cur]})
        national = {"data_through": L["data_through"], "boards": boards,
                    "history": [{"through": e["through"], "ranks": e["ranks"]} for e in nat[tab].get("rank_history", [])],
                    "current": all(any(x.get("g") == p["games"] for b in L["boards"].values() for x in [b["players"].get(p["name"]) or {}]) for p in cur)}
    sources = []
    for p in players:
        if p.get("source_url"): sources.append({"label": f"cfbstats.com: Indiana {p['season']} {'rushing' if tab == 'rb' else 'receiving'}", "url": p["source_url"]})
    sources = list({s["url"]: s for s in sources}.values())
    return {"status": "ok", "label": spec["label"], "noun": spec["noun"], "count": spec["count"], "N": N,
            "title": f"{cur_names} vs the Cignetti era", "lede": lede, "players": players, "h2h": h2h,
            "stats": [{"key": k, "label": l, "short": SHORT.get(l, l), "dp": d, "hb": hb} for k, l, d, hb in spec["stats"]],
            "chart": [{"key": k, "label": l} for k, l in spec["chart"]], "national": national,
            "rule": sk[tab].get("rule", ""), "sources": sources, "fresh": fresh}


# ------------------------------------------------------------------ Team
def team_rows(games):
    out, c = [], {k: 0 for k in ("wins", "losses", "ties", "pf", "pa", "total_yds", "rush_yds", "pass_yds", "to_margin", "third_conv", "third_att")}
    for i, g in enumerate(games):
        w = 1 if g["pf"] > g["pa"] else 0; l = 1 if g["pf"] < g["pa"] else 0; c["ties"] += 1 if g["pf"] == g["pa"] else 0
        tom = g["to_gained"] - g["to_lost"]
        for k, v in (("wins", w), ("losses", l), ("pf", g["pf"]), ("pa", g["pa"]), ("total_yds", g["total_yds"]), ("rush_yds", g["rush_yds"]),
                     ("pass_yds", g["pass_yds"]), ("to_margin", tom), ("third_conv", g["third_conv"]), ("third_att", g["third_att"])):
            c[k] += v
        r = {k: g[k] for k in ("date", "event", "opp", "site", "result", "pf", "pa", "total_yds", "rush_yds", "pass_yds", "to_lost", "to_gained", "third_conv", "third_att")}
        r.update({"n": i + 1, "wins": w, "to_margin": tom, "third_pct": 100 * g["third_conv"] / g["third_att"] if g["third_att"] else None,
                  "cum": {**{k: c[k] for k in ("wins", "losses", "ties", "pf", "pa", "total_yds", "rush_yds", "pass_yds", "to_margin")},
                          "third_pct": 100 * c["third_conv"] / c["third_att"] if c["third_att"] else None,
                          "third_conv": c["third_conv"], "third_att": c["third_att"]}})
        out.append(r)
    return out


def team_totals(rows):
    if not rows: return None
    t = dict(rows[-1]["cum"]); t["games"] = len(rows); t["record"] = f"{t['wins']}-{t['losses']}" + (f"-{t['ties']}" if t["ties"] else "")
    return t


def team_tab(td, check, cur_season, fresh):
    teams_raw, ap = td.get("teams", {}), td.get("ap")
    iu = teams_raw.get("84", {}).get("seasons", {})
    if str(cur_season) not in iu:
        return {"status": "pending", "label": "Team", "message": "Team data has not been collected yet; the next full refresh adds it."}
    entries = []
    iu_seasons = sorted((int(s) for s in iu), reverse=True)
    for i, s in enumerate(iu_seasons):
        blk = iu[str(s)]
        entries.append({"key": f"iu{s}", "label": f"Indiana {s}", "short": f"IU {s}", "season": s, "kind": "cur" if s == cur_season else "prev",
                        "slot": "cur" if s == cur_season else PALETTE[min(i - 1, len(PALETTE) - 1)], "games_raw": blk["games"],
                        "check": blk.get("check", ""), "url": blk.get("cfbstats_url")})
    poll = None
    if ap:
        poll = {"name": ap["poll"], "week": ap.get("week", ""), "date": ap["date"], "source_url": ap.get("source_url"),
                "top": [{"rank": t["rank"], "name": t["name"], "record": t.get("record", ""), "is_iu": t["team_id"] == "84"} for t in ap["top"]]}
        for t in ap["top"]:
            if t["team_id"] == "84":
                entries[0]["ap_rank"] = t["rank"]; continue
            blk = teams_raw.get(t["team_id"], {}).get("seasons", {}).get(str(cur_season))
            if not blk: continue
            entries.append({"key": f"ap{t['team_id']}", "label": f"#{t['rank']} {t['name']}", "short": t.get("abbr") or t["name"],
                            "season": cur_season, "kind": "ap", "rank": t["rank"], "record_poll": t.get("record", ""),
                            "slot": AP_SLOTS[min(t["rank"] - 1, len(AP_SLOTS) - 1)], "games_raw": blk["games"],
                            "check": blk.get("check", ""), "url": blk.get("cfbstats_url")})
    for e in entries:
        tag = f"team {e['label']}"
        for g in e["games_raw"]:
            check(g["total_yds"] == g["rush_yds"] + g["pass_yds"], f"{tag} {g['date']}: total yards != rushing + passing")
            check(0 <= g["third_conv"] <= g["third_att"], f"{tag} {g['date']}: third-down conversions exceed attempts")
        dates = [g["date"] for g in e["games_raw"]]
        check(dates == sorted(dates), f"{tag}: games out of order")
        e["rows"] = team_rows(e.pop("games_raw")); e["games"] = len(e["rows"])
        if e["kind"] == "ap" and e.get("record_poll"):
            rec = team_totals(e["rows"])["record"]
            e["record_note"] = "" if rec == e["record_poll"] else f"poll lists {e['record_poll']}, stored games give {rec}"
    N = entries[0]["games"]
    for e in entries:
        e["totals"] = team_totals(e["rows"][:N]); e["short_of_n"] = e["games"] < N
        if e["kind"] == "prev": e["full"] = team_totals(e["rows"])
    h2h = []
    for key, label, dp, hb in TEAM_STATS:
        get = lambda e: e["totals"]["third_pct"] if key == "third_pct" else e["totals"][key]
        comp = [i for i, e in enumerate(entries) if not e["short_of_n"] and get(e) is not None]
        r = {i: round(get(entries[i]), dp) for i in comp}
        best = (max if hb else min)(r.values()) if r else None
        leaders = [i for i in comp if r[i] == best]
        if len(leaders) == len(comp): leaders = []
        h2h.append({"key": key, "label": label, "dp": dp, "hb": hb, "leaders": leaders})
    c = entries[0]["totals"]
    prev = [e for e in entries if e["kind"] == "prev"]
    lede = (f"Indiana {cur_season} is {c['record']} through {N} game{'s' if N > 1 else ''}, scoring {c['pf']:,} and allowing {c['pa']:,}. "
            + " ".join(f"At the same point in {e['season']}: {e['totals']['record']}, {e['totals']['pf']:,} scored and {e['totals']['pa']:,} allowed." for e in prev))
    return {"status": "ok", "label": "Team", "N": N, "teams": entries, "poll": poll, "h2h": h2h,
            "stats": [{"key": k, "label": l, "short": SHORT.get(l, l), "dp": d, "hb": hb} for k, l, d, hb in TEAM_STATS],
            "chart": [{"key": "pf", "label": "Points scored"}, {"key": "pa", "label": "Points allowed"}, {"key": "total_yds", "label": "Total yds"},
                      {"key": "rush_yds", "label": "Rush yds"}, {"key": "pass_yds", "label": "Pass yds"}, {"key": "to_margin", "label": "TO margin"},
                      {"key": "third_pct", "label": "3rd down %"}, {"key": "wins", "label": "Wins"}],
            "lede": lede, "fresh": fresh}


def build(root, roster, cur_season, check, as_of):
    fr = load(root, "freshness.json", {})
    title = roster.get("site_title", "Hoosiers {season}").format(season=cur_season)
    sk, nat, td = load(root, "skill.json", {}), load(root, "skill_national.json", {}), load(root, "team.json", {"teams": {}, "ap": None})
    def f(keys, what):
        when = [fr[k] for k in keys if fr.get(k)]
        return {"what": what, "checked": max(when) if when else None}
    out = {"site": {"title": title, "season": cur_season}}
    for tab in ("rb", "wr"):
        out[tab] = skill_tab(tab, sk, nat, check, cur_season, f(["players", "team"], "Box scores and cfbstats season rows"))
    out["team"] = team_tab(td, check, cur_season, f(["team", "ap_poll"], "ESPN box scores and AP poll"))
    return out
