#!/usr/bin/env python3
"""Data for the RB, WR and Team tabs.  Called from collect.py (same run, same rules, no AI step).

Sources
  AP Top 5 ............... ESPN rankings JSON (AP Top 25 entry: poll name, week, release date)
  team game rows ......... ESPN team schedule JSON (finals, scores) + ESPN game summary JSON (box score)
  RB / WR game lines ..... the same ESPN box scores (Indiana's rushing and receiving tables)
  season cross-checks .... cfbstats.com team pages: season team statistics and player rushing/receiving
  national RB / WR boards  cfbstats.com national player leaders (rushing, receiving)

Every stored row is checked before it is written (update.py): box-score player lines must add up to the
team totals in the same box score, total yards must equal rushing plus passing, the score must match the
schedule, and each season must match cfbstats.com's season totals once cfbstats has posted the same games.
"""
import datetime as dt, io, re

import pandas as pd

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
IU_ESPN, IU_CFB = "84", 306
TABS = {  # cfbstats category, stat columns used on the national boards
    "rb": {"page": "rushing", "cat": "01", "count_key": "att",
           "stats": {"yds": ("Yards", "Rushing yards"), "td": ("TD", "Rushing TD"), "ypc": ("Avg", "Yards per carry"), "ypg": ("Yards/G", "Yards per game")},
           "qualified": {"ypc", "ypg"}},
    "wr": {"page": "receiving", "cat": "03", "count_key": "rec",
           "stats": {"rec": ("Rec", "Receptions"), "yds": ("Yards", "Receiving yards"), "td": ("TD", "Receiving TD"), "ypr": ("Avg", "Yards per catch"), "ypg": ("Yards/G", "Yards per game")},
           "qualified": {"ypr", "ypg"}},
}
ESPN_TO_CFB = {"Miami": "Miami (FL)", "Miami (OH)": "Miami (OH)", "Hawai'i": "Hawaii", "San José State": "San Jose State",
               "App State": "Appalachian State", "UL Monroe": "Louisiana-Monroe", "UMass": "Massachusetts"}


def norm(name):
    s = re.sub(r"[.,'’]", "", str(name).lower())
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def num(d, k):
    return int(float(str(d[k]).replace(",", "")))


# ------------------------------------------------------------------ ESPN
def espn_completed(C, team_id, season):
    """Completed games for a team and season (regular season + postseason), with scores, by Eastern date."""
    out = {}
    for st in (2, 3):
        j = C.get(f"{ESPN}/teams/{team_id}/schedule?season={season}&seasontype={st}").json()
        for ev in j.get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            if not (comp.get("status") or ev.get("status") or {}).get("type", {}).get("completed"): continue
            me = next((c for c in comp.get("competitors", []) if str(c.get("id")) == str(team_id)), None)
            op = next((c for c in comp.get("competitors", []) if str(c.get("id")) != str(team_id)), None)
            if not me or not op: continue
            sc = lambda c: int(float(c["score"].get("value", c["score"].get("displayValue")) if isinstance(c.get("score"), dict) else c.get("score")))
            date = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(C.ET).date().isoformat()
            pf, pa = sc(me), sc(op)
            out[str(ev["id"])] = {"event": str(ev["id"]), "date": date,
                                  "opp": op.get("team", {}).get("location") or op.get("team", {}).get("displayName", ""),
                                  "opp_id": str(op.get("id")),
                                  "site": "N" if comp.get("neutralSite") else ("H" if me.get("homeAway") == "home" else "A"),
                                  "pf": pf, "pa": pa, "result": f"{'W' if pf > pa else 'L' if pf < pa else 'T'} {pf}-{pa}"}
    return sorted(out.values(), key=lambda g: g["date"])


def box_row(C, g, team_id, with_players):
    """Add box-score team stats (and Indiana's rushing/receiving lines) to a schedule row."""
    j = C.get(f"{ESPN}/summary?event={g['event']}").json()
    bt = {str(t["team"]["id"]): {s["name"]: s.get("displayValue") for s in t.get("statistics", [])} for t in j["boxscore"]["teams"]}
    me = bt[str(team_id)]; op = next(v for k, v in bt.items() if k != str(team_id))
    tag = f"box {g['date']} {g['opp']}"
    for c in (j.get("header", {}).get("competitions") or [{}])[0].get("competitors", []):
        s = c.get("score")
        if s not in (None, ""):
            want = g["pf"] if str(c.get("id")) == str(team_id) else g["pa"]
            if int(float(s)) != want: raise ValueError(f"{tag}: summary score {s} != schedule score {want}")
    conv, att = (int(x) for x in str(me["thirdDownEff"]).split("-"))
    lost = num(me, "fumblesLost") + num(me, "interceptions")
    gained = num(op, "fumblesLost") + num(op, "interceptions")
    if "turnovers" in me and num(me, "turnovers") != lost: raise ValueError(f"{tag}: turnovers {me['turnovers']} != fumbles lost + interceptions {lost}")
    row = dict(g, total_yds=num(me, "totalYards"), rush_yds=num(me, "rushingYards"), pass_yds=num(me, "netPassingYards"),
               to_lost=lost, to_gained=gained, third_conv=conv, third_att=att)
    if with_players:
        side = next(p for p in j["boxscore"].get("players", []) if str(p["team"]["id"]) == str(team_id))
        for cat, key, cols in (("rushing", "rush", ("rushingAttempts", "rushingYards", "rushingTouchdowns")),
                               ("receiving", "rec", ("receptions", "receivingYards", "receivingTouchdowns"))):
            st = next((s for s in side.get("statistics", []) if s.get("name") == cat), None)
            if not st: row[key] = []; continue
            ix = [st["keys"].index(c) for c in cols]
            lines, sums = [], [0, 0, 0]
            for a in st.get("athletes", []):
                v = [int(float(str(a["stats"][i]).replace(",", "") or 0)) for i in ix]
                sums = [x + y for x, y in zip(sums, v)]
                if not str(a["athlete"].get("id", "")).startswith("-"):  # '-' ids are the 'Team' line
                    lines.append({"id": str(a["athlete"]["id"]), "name": a["athlete"]["displayName"].strip(), "n": v[0], "yds": v[1], "td": v[2]})
            tot = [int(float(str(st["totals"][i]).replace(",", "") or 0)) for i in ix]
            if sums != tot: raise ValueError(f"{tag}: {cat} player lines {sums} != box-score totals {tot}")
            row[key] = lines
    return row


# ------------------------------------------------------------------ cfbstats
def cfb_team_ids(C, season):
    html = C.get(f"https://cfbstats.com/{season}/team/index.html").text
    return {m.group(2).strip(): int(m.group(1)) for m in re.finditer(r'href="/?(?:https://cfbstats\.com)?/?\d{4}/team/(\d+)/index\.html">([^<]+)</a>', html)}


def cfb_team_totals(C, season, cfb_id):
    """Season totals from a cfbstats team page: {games, pf, pa, rush_yds, pass_yds, total_yds, third_att, third_conv, to_lost, to_gained}."""
    url = f"https://cfbstats.com/{season}/team/{cfb_id}/index.html"
    html = C.get(url).text
    vals, group = {}, ""
    for t in pd.read_html(io.StringIO(html)):
        if t.shape[1] < 3: continue
        for _, r in t.iterrows():
            lab, a, b = (str(x).strip() for x in r.iloc[:3])
            if a.lower() in ("nan", lab.lower()) and b.lower() in ("nan", lab.lower()): group = lab; continue  # group header row
            if ":" in lab: group, lab = (x.strip() for x in lab.split(":", 1))
            vals[(group.lower(), lab.lower())] = (a, b)
    def parts(group, label, side):
        v = vals.get((group, label)) or next((v for (g, l), v in vals.items() if g.startswith(group) and l == label), None)
        if not v: raise ValueError(f"cfbstats {season} team {cfb_id}: no '{group}: {label}' row; rows seen: {sorted(vals)[:60]}")
        return [int(float(x.replace(",", ""))) for x in re.split(r"\s+-\s+", v[side])]
    g, pf = parts("scoring", "games - points", 0); _, pa = parts("scoring", "games - points", 1)
    rush = parts("rushing", "attempts - yards - td", 0)[1]
    pas = parts("passing", "yards", 0)[0]
    tot = parts("total offense", "plays - yards", 0)[1]
    t_att, t_conv = parts("3rd down conversions", "attempts - conversions", 0)
    int_thrown = parts("passing", "attempts - completions - interceptions - td", 0)[2]
    opp_int_thrown = parts("passing", "attempts - completions - interceptions - td", 1)[2]
    fum_lost = parts("fumbles", "number - lost", 0)[1]; opp_fum_lost = parts("fumbles", "number - lost", 1)[1]
    return {"through": C.through_date(html), "url": url,
            "totals": {"games": g, "pf": pf, "pa": pa, "rush_yds": rush, "pass_yds": pas, "total_yds": tot,
                       "third_att": t_att, "third_conv": t_conv, "to_lost": int_thrown + fum_lost, "to_gained": opp_int_thrown + opp_fum_lost}}


def cfb_players(C, season, page):
    """Indiana's season rushing or receiving rows from cfbstats: [{name, pos, g, att|rec, yds, td}], through date, url."""
    url = f"https://cfbstats.com/{season}/team/{IU_CFB}/{page}/index.html"
    html = C.get(url).text
    t = pd.read_html(io.StringIO(html))[0]
    t.columns = [re.sub(r"\.", "", str(c)).strip().lower() for c in t.columns]
    first = "att" if page == "rushing" else "rec"
    rows = []
    for _, r in t.iterrows():
        nm = str(r.get("name", "")).strip()
        if not nm or nm.lower() in ("nan", "team", "total", "opponents"): continue
        rows.append({"name": nm, "pos": str(r.get("pos", "")).strip(), "g": C.ival(r["g"]), first: C.ival(r[first]),
                     "yds": C.ival(r["yards"]), "td": C.ival(r["td"])})
    return rows, C.through_date(html), url


# ------------------------------------------------------------------ sections
def ap_poll(C, U):
    j = C.get(f"{ESPN}/rankings").json()
    r = next((x for x in j.get("rankings", []) if x.get("type") == "ap" or "AP" in x.get("name", "")), None)
    if not r: raise ValueError("no AP poll in ESPN rankings")
    if str(C.SEASON) not in (r.get("headline", "") + r.get("date", "")): raise ValueError(f"AP poll is not for {C.SEASON}: {r.get('headline')}")
    ranks = sorted(r["ranks"], key=lambda x: x["current"])
    top = [{"rank": x["current"], "team_id": str(x["team"]["id"]), "name": x["team"].get("location") or x["team"].get("name"),
            "nickname": x["team"].get("name", ""), "abbr": x["team"].get("abbreviation", ""), "record": x.get("recordSummary", ""),
            "first_place": x.get("firstPlaceVotes", 0)} for x in ranks if x["current"] <= 5]
    U.ap_poll({"poll": r.get("name", "AP Top 25"), "week": (r.get("occurrence") or {}).get("displayValue", ""),
               "headline": r.get("headline", ""), "date": r.get("date", "")[:10], "season": C.SEASON, "top": top,
               "source_url": "https://www.espn.com/college-football/rankings"})


def team_seasons(C, U):
    seasons = sorted({q["season"] for q in U.roster()["qbs"]})
    d = U.load_or("team.json", {"teams": {}, "ap": None})
    ap = d.get("ap") or {}
    jobs = [(IU_ESPN, "Indiana", s, IU_CFB) for s in seasons]
    ids = None
    for t in ap.get("top", []):
        if t["team_id"] == IU_ESPN: continue
        if ids is None:
            try: ids = cfb_team_ids(C, C.SEASON)
            except Exception as e: ids = {}; C.log(f"[team] cfbstats team list not available: {e}")
        cfb = ids.get(ESPN_TO_CFB.get(t["name"], t["name"]))
        jobs.append((t["team_id"], t["name"], C.SEASON, cfb))
    keep = [j[0] for j in jobs]
    for tid, name, season, cfb in jobs:
        stored = d["teams"].get(tid, {}).get("seasons", {}).get(str(season))
        if stored and stored.get("complete") and str(stored.get("check", "")).startswith("cfbstats"):
            continue  # a finished season that matched cfbstats never changes
        have = {g["event"]: g for g in (stored or {}).get("games", [])}
        rows = []
        for g in espn_completed(C, tid, season):
            old = have.get(g["event"])
            rows.append(old if old and (tid != IU_ESPN or "rush" in old) else box_row(C, g, tid, with_players=(tid == IU_ESPN)))
        if not rows: C.log(f"[team] {name} {season}: no completed games yet"); continue
        cf, note = None, "not cross-checked: no cfbstats page found for this team"
        if cfb:
            try:
                tt = cfb_team_totals(C, season, cfb)
                if tt["totals"]["games"] == len(rows): cf = tt
                else: note = f"not cross-checked yet: cfbstats has {tt['totals']['games']} games through {tt['through']}, ESPN {len(rows)}"
            except Exception as e:
                note = f"not cross-checked: cfbstats season totals unreadable ({e})"
                if season < C.SEASON: raise
        U.team_season({"team_id": tid, "name": name, "season": season, "games": rows, "cfbstats": cf, "check_note": note,
                       "complete": season < C.SEASON, "keep_teams": keep})
        C.log(f"[team] {name} {season}: {len(rows)} games; " + (f"matches cfbstats through {cf['through']}" if cf else note))


def players(C, U):
    cfg = U.roster().get("tabs", {})
    seasons = sorted({q["season"] for q in U.roster()["qbs"]}, reverse=True)
    iu = U.load_or("team.json", {"teams": {}})["teams"].get(IU_ESPN, {}).get("seasons", {})
    for tab, spec in TABS.items():
        tc = cfg.get(tab, {}); key = spec["count_key"]; out = []
        for season in seasons:
            games = (iu.get(str(season)) or {}).get("games", [])
            if not games: C.log(f"[{tab}] {season}: no Indiana box scores stored yet"); continue
            rows, through, url = cfb_players(C, season, spec["page"])
            named = (tc.get("current") or {}).get(str(season))
            if named: names = named
            else:
                pool = [r for r in rows if not tc.get("positions") or r["pos"] in tc["positions"]]
                names = [r["name"] for r in sorted(pool, key=lambda r: -r["yds"])[:tc.get("count", 2)]]
            for nm in names:
                cf = next((r for r in rows if norm(r["name"]) == norm(nm)), None)
                lines, pid = [], None
                for g in games:
                    hit = next((a for a in g.get("rush" if tab == "rb" else "rec", []) if (pid and a["id"] == pid) or norm(a["name"]) == norm(nm)), None)
                    if not hit: continue
                    pid = pid or hit["id"]
                    lines.append({"date": g["date"], "event": g["event"], "opp": g["opp"], "site": g["site"], "result": g["result"],
                                  key: hit["n"], "yds": hit["yds"], "td": hit["td"]})
                if not lines: C.log(f"[{tab}] {nm} {season}: no box-score lines found"); continue
                checked = cf if (cf and through and through >= lines[-1]["date"] and season <= C.SEASON) else None
                if season < C.SEASON and not cf: raise ValueError(f"{nm} {season}: not found on cfbstats {spec['page']} page")
                if season < C.SEASON and through and through < games[-1]["date"]: raise ValueError(f"cfbstats {season} {spec['page']} page is incomplete")
                out.append({"name": nm, "season": season, "role": "current" if season == C.SEASON else "comparison", "espn_id": pid,
                            "games": lines, "cfbstats_row": checked, "cfbstats_through": through, "cfbstats_url": url,
                            "chosen": "named in roster.json" if named else f"top {tc.get('count', 2)} by {spec['page']} yards"})
        rule = (f"Current season: players named in roster.json. Earlier seasons: Indiana's top {tc.get('count', 2)} "
                f"{'/'.join(tc.get('positions', []))} by {spec['page']} yards (cfbstats.com).")
        if not out: C.log(f"[{tab}] nothing to store yet"); continue
        U.skill({"tab": tab, "players": out, "rule": rule})


def national_boards(C, U):
    cfg = U.roster().get("tabs", {})
    for tab, spec in TABS.items():
        names = (cfg.get(tab, {}).get("current") or {}).get(str(C.SEASON))
        if not names:
            sk = U.load_or("skill.json", {}).get(tab, {}).get("players", [])
            names = [p["name"] for p in sk if p["season"] == C.SEASON]
        base = f"https://cfbstats.com/{C.SEASON}/leader/national/player/split01/category{spec['cat']}/"
        html = C.get(base + "sort01.html").text
        links = {re.sub(r"\.", "", lab).strip().lower(): href for href, lab in re.findall(r'href="[^"]*?(sort\d+\.html)"[^>]*>([^<]+)</a>', html)}
        boards, dates, players_out = {}, set(), {}
        for stat, (col, label) in spec["stats"].items():
            href = links.get(col.lower(), "sort01.html")   # the unlinked column (Yards/G) is the page's default sort
            page = html if href == "sort01.html" else C.get(base + href).text
            dates.add(C.through_date(page))
            t = pd.read_html(io.StringIO(page))[0]
            t.columns = [re.sub(r"\.", "", str(c)).strip() for c in t.columns]
            vcol = next(c for c in t.columns if c.lower() == col.lower())
            rk_col, last, rows = t.columns[0], None, []
            for _, r in t.iterrows():
                rk = str(r[rk_col]).strip(); last = int(float(rk)) if rk and rk.lower() != "nan" else last
                rows.append({"rank": last, "name": str(r["Name"]).strip(), "team": C.TEAM_FIX.get(str(r["Team"]).strip(), str(r["Team"]).strip()),
                             "g": C.ival(r["G"]), "value": float(str(r[vcol]).replace(",", ""))})
            mine = {}
            for nm in names:
                hit = next((x for x in rows if norm(x["name"]) == norm(nm) and x["team"] == "Indiana"), None)
                mine[nm] = {"rank": hit["rank"], "value": hit["value"], "g": hit["g"]} if hit else None
            boards[stat] = {"label": label, "source_url": base + href, "qualified": stat in spec["qualified"],
                            "top": [x for x in rows if x["rank"] <= 5], "players": {k: v for k, v in mine.items() if v}}
            players_out = names
        dates.discard(None)
        if len(dates) != 1: raise ValueError(f"{tab} leaderboard pages disagree on 'through' date: {sorted(dates)}")
        U.skill_national({"tab": tab, "data_through": dates.pop(), "boards": boards, "players": players_out})


def run(C, U):
    """Run the tab sections in order.  Each is independent; a failure keeps that section's stored data."""
    C.section("ap_poll")(lambda: ap_poll(C, U))()
    C.section("team")(lambda: team_seasons(C, U))()
    C.section("players")(lambda: players(C, U))()
    C.section("skill_national")(lambda: national_boards(C, U))()
