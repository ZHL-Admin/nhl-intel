"""Validation for the rebuilt Player Fit: quality FLOORS fit (never caps), need is the core.

The four behaviors that must ALL hold at once (blueprint of this rebuild):
  1. A low-value SPECIALIST scores a HIGH fit for the need he serves — uncapped by his low quality.
  2. A STAR's fit VARIES meaningfully across teams (it is not pinned high everywhere).
  3. A STAR is NEVER rated a poor fit anywhere — the quality floor holds.
  4. A low-value player nobody needs scores LOW.

Prints the decomposition (quality axis + need/style/line) per case and asserts the four properties.

Run:  python -m models_ml.validate_trade_fit              (compute mode, against BigQuery)
      SERVING_BACKEND=duckdb python -m models_ml.validate_trade_fit   (fast, against the serving file)
"""
from __future__ import annotations

from models_ml import bq, config
from models_ml.score_team_fit import score_team_fit, best_team_fits

CFG = config.TRADE_FIT
B_FLOOR = dict(CFG["GRADE_BANDS"])["B"]   # the "good fit" threshold (B band floor)
C_FLOOR = dict(CFG["GRADE_BANDS"])["C"]


def _season() -> str:
    return bq.query_df(f"select max(season) s from `{bq.project()}.nhl_models.team_needs`").iloc[0]["s"]


def _elite_skater(season: str) -> int:
    return int(bq.query_df(f"""select player_id from `{bq.project()}.nhl_models.player_gar`
        where season_window='{season}' and position in ('C','L','R') order by war desc limit 1""").iloc[0]["player_id"])


def _bad_skater(season: str) -> int:
    return int(bq.query_df(f"""select player_id from `{bq.project()}.nhl_models.player_gar`
        where season_window='{season}' and toi_5v5>=600 order by war asc limit 1""").iloc[0]["player_id"])


def _specialist(season: str) -> tuple[int, str]:
    """A LOW-overall skater who is ELITE in one component within his role (a true specialist), and
    the component he's elite at."""
    p = bq.project()
    df = bq.query_df(f"""
        with base as (
          select c.player_id,
            case when c.position='C' then 'C' when c.position in ('L','R') then 'W'
                 when c.position='D' then 'D' else c.position end as role,
            c.ev_offense, c.ev_defense, c.pp, c.pk, c.finishing
          from `{p}.nhl_models.player_composite` c
          where c.season_window='{season}' and c.toi_5v5>=400),
        r as (
          select player_id, role,
            percent_rank() over (partition by role order by ev_offense) as ev_offense,
            percent_rank() over (partition by role order by ev_defense) as ev_defense,
            percent_rank() over (partition by role order by pk) as pk,
            percent_rank() over (partition by role order by finishing) as finishing
          from base),
        ov as (select player_id, overall_percentile from `{p}.nhl_models.player_overall`
               where season_window='{season}'),
        m as (
          select r.player_id, r.role, o.overall_percentile,
            greatest(r.ev_defense, r.pk) as def_spec
          from r join ov o using (player_id))
        select player_id, role, def_spec from m
        where overall_percentile < 0.45 and def_spec >= 0.85
        order by def_spec desc limit 1""")
    if df.empty:
        return _bad_skater(season), "ev_defense"
    return int(df.iloc[0]["player_id"]), "ev_defense"


def _starter_goalie(season: str) -> int:
    return int(bq.query_df(f"""select goalie_id from `{bq.project()}.nhl_models.goalie_gar`
        where season_window='{season}' order by war desc limit 1""").iloc[0]["goalie_id"])


def tempering_report(season: str) -> bool:
    """The projection must temper an OLDER player's spike MORE than a YOUNG player's (proj/last lower
    for old). Reads the same projection the fit floor uses."""
    import statistics
    from models_ml.score_team_fit import _skater_projection
    proj = _skater_projection(bq.project(), season)
    young = [(d["proj_war"] / d["last_war"], d) for d in proj.values()
             if d["last_war"] and d["last_war"] >= 1.0 and (d["age"] or 99) <= 23]
    old = [(d["proj_war"] / d["last_war"], d) for d in proj.values()
           if d["last_war"] and d["last_war"] >= 1.0 and (d["age"] or 0) >= 31]
    print("\n=== Projection tempering (proj/last WAR; < 1.0 = regressed below last season) ===")
    my = statistics.mean(t for t, _ in young) if young else None
    mo = statistics.mean(t for t, _ in old) if old else None
    if my is not None:
        print(f"  young (<=23): n={len(young)} mean proj/last = {my:.2f}")
    if mo is not None:
        print(f"  old   (>=31): n={len(old)} mean proj/last = {mo:.2f}")
    names = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) nm
        from `{bq.project()}.nhl_staging.stg_rosters` group by 1""")
    nm = dict(zip(names["player_id"], names["nm"]))
    # illustrative ends: the most-regressed OLD spike vs the least-regressed YOUNG player
    for tag, grp, pick in (("OLD most-regressed spike", old, min),
                           ("YOUNG projection holds  ", young, max)):
        if grp:
            t, d = pick(grp, key=lambda x: x[0])
            pid = next(k for k, v in proj.items() if v is d)
            print(f"  {tag}: {nm.get(pid, pid)} age {d['age']}  last {d['last_war']:+.1f} -> "
                  f"proj {d['proj_war']:+.1f} (±{d['proj_war_sd']:.1f}, {t:.2f}x)")
    ok = (mo is None or my is None or mo <= my)
    print("  OK: older spikes regressed more than young." if ok
          else "  FAIL: older NOT regressed more than young.")
    return ok


def _show(pid: int, tid: int, season: str, title: str) -> dict:
    r = score_team_fit(pid, tid, season)
    q = r["quality"]
    dims = {d["key"]: d.get("level") for d in r["dimensions"]}
    qpct = None if q["percentile"] is None else round(q["percentile"], 2)
    print(f"\n{title}")
    print(f"  {r['player_name']} ({r['role']}) -> {tid}: FIT={r['overall_score']:.1f} {r['overall_grade']}"
          f"   quality_pctile={qpct} ({q['label']})")
    print(f"     dims: " + "  ".join(f"{k}={'n/a' if v is None else round(v,2)}" for k, v in dims.items()))
    top_bd = sorted(r["need_breakdown"], key=lambda b: -b["opportunity"])[:3]
    nb = ", ".join(f"{b['label'].split('· ')[-1]}: need {b['team_need']} x str {b['player_strength']}"
                   for b in top_bd)
    print(f"     need breakdown: {nb}")
    print(f"     verdict: {r['verdict_sentence']}")
    return r


def main() -> None:
    season = _season()
    elite = _elite_skater(season)
    bad = _bad_skater(season)
    spec, spec_comp = _specialist(season)
    goalie = _starter_goalie(season)
    print(f"season={season}  elite={elite}  specialist={spec} (def)  bad={bad}  goalie={goalie}")

    temper_ok = tempering_report(season)

    # ---- star spread (cases 2 & 3): lightweight fit across all 32 teams ----
    star_fits = best_team_fits(elite, season, top_n=99)
    star_scores = sorted(f["fit_score"] for f in star_fits)
    star_min, star_max = star_scores[0], star_scores[-1]
    print(f"\n[STAR spread] {len(star_scores)} teams: min={star_min:.1f} max={star_max:.1f} "
          f"spread={star_max - star_min:.1f}  (B floor={B_FLOOR*100:.0f})")

    # detailed decompositions at the star's best and worst fit teams
    best_t = max(star_fits, key=lambda f: f["fit_score"])["team_id"]
    worst_t = min(star_fits, key=lambda f: f["fit_score"])["team_id"]
    _show(elite, best_t, season, "STAR -> BEST-fit team (expect A)")
    _show(elite, worst_t, season, "STAR -> WORST-fit team (still >= B: floor holds)")

    # ---- specialist (case 1): his best team should be a HIGH fit despite low quality ----
    spec_fits = best_team_fits(spec, season, top_n=99)
    spec_best = max(spec_fits, key=lambda f: f["fit_score"])
    r_spec = _show(spec, spec_best["team_id"], season,
                   "SPECIALIST -> his best-need team (expect HIGH fit, uncapped by low quality)")

    # ---- bad player (case 4): even his best team is a LOW fit ----
    bad_fits = best_team_fits(bad, season, top_n=99)
    bad_best = max(bad_fits, key=lambda f: f["fit_score"])
    r_bad = _show(bad, bad_best["team_id"], season, "BAD player -> his best team (expect LOW fit)")

    # ---- goalie (Phase 5): need-only path + floor ----
    g_fits = best_team_fits(goalie, season, top_n=99)
    if g_fits:
        _show(goalie, max(g_fits, key=lambda f: f["fit_score"])["team_id"], season,
              "GOALIE -> most goalie-needy team (need-only + floor)")

    # ---------------------------------------------------------------- assertions
    print("\n=== BEHAVIOR CHECKS ===")
    ok = True
    # 1. specialist reaches a high (>= B) fit somewhere
    if r_spec["overall_score"] / 100.0 < B_FLOOR:
        print(f"  FAIL (1): specialist best fit {r_spec['overall_score']:.1f} < B ({B_FLOOR*100:.0f}) "
              f"— a need-serving specialist should reach a high fit"); ok = False
    else:
        print(f"  OK (1): specialist reaches {r_spec['overall_grade']} ({r_spec['overall_score']:.1f}) "
              f"despite {r_spec['quality']['label']} quality")
    # 2. star fit varies meaningfully across teams
    if star_max - star_min < 8.0:
        print(f"  FAIL (2): star spread only {star_max - star_min:.1f} pts — fit barely varies"); ok = False
    else:
        print(f"  OK (2): star fit varies {star_max - star_min:.1f} pts across teams")
    # 3. star never a POOR fit: the quality floor keeps a star out of D/F (>= C) even at a bad-fit
    #    team (under the conventional hard bands a poor-stylistic-match star reads C, not a forced B).
    if star_min / 100.0 < C_FLOOR - 1e-9:
        print(f"  FAIL (3): star worst fit {star_min:.1f} < C floor — the quality floor did not hold"); ok = False
    else:
        print(f"  OK (3): star worst fit {star_min:.1f} >= C floor — floor keeps a star out of D/F")
    # 4. bad player's best fit is low (< C)
    if r_bad["overall_score"] / 100.0 >= C_FLOOR:
        print(f"  FAIL (4): bad player's best fit {r_bad['overall_score']:.1f} >= C — too high"); ok = False
    else:
        print(f"  OK (4): bad player's best fit {r_bad['overall_score']:.1f} < C")
    ok = ok and temper_ok
    print("\n  ALL CHECKS HOLD (4 behaviors + projection tempering)." if ok
          else "\n  *** ONE OR MORE CHECKS VIOLATED ***")


if __name__ == "__main__":
    main()
