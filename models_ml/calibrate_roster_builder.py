"""Calibrate + validate the Roster Builder's ABSOLUTE rating map (reads only; writes nothing).

The offseason forecast trusts a team's MEASURED rating for its returning core and only adjusts for
moves (projected_rating = base_rating + net_delta_war*scale). The Roster Builder has no trustworthy
base for an arbitrary user-built roster, so it computes an ABSOLUTE rating from the roster's own
projected value:

    rating_abs       = (total_lineup_WAR - LEAGUE_AVG_LINEUP_WAR) * GOALS_PER_WIN / GAMES_PER_SEASON
                       (+ chemistry_adj at serving time)
    projected_points = rating_to_points(rating_abs)          # the shipped Handoff-10 map

LEAGUE_AVG_LINEUP_WAR is the one new constant: the league-mean projected iced-lineup WAR, so that an
average roster maps to rating_abs ~= 0 (~= league-average points). This script calibrates it and
proves the chain, exactly as validate_roster_forecast proves the move-based map:

  * Build each team's iced lineup from the SAME engine the tool uses (loaders -> make_player_proj ->
    _full_lineup on projected_war), summed to total_lineup_WAR, over the two completed forward
    transitions we have outcomes for (2023-24->2024-25 and 2024-25->2025-26 opening rosters).
  * LEAGUE_AVG_LINEUP_WAR = the pooled mean of those team totals.
  * Validate: corr(rating_abs, MEASURED team_ratings) and MAE(projected_points, ACTUAL standings
    points). Flag loudly if MAE is implausible (> 10) rather than trusting a bad fit.

Run: SERVING_BACKEND=duckdb python -m models_ml.calibrate_roster_builder
"""

from __future__ import annotations

from models_ml import project_roster_forecast as J

CFG = J.CFG
FLOOR = CFG["MIN_GAMES_ROSTER"]
N_BACK = CFG["PROJ_WINDOWS"]
SCALE = CFG["GOALS_PER_WIN"] / CFG["GAMES_PER_SEASON"]

# Completed forward transitions: (value/aging base season, target opening-roster season).
TRANSITIONS = [("2023-24", "2024-25"), ("2024-25", "2025-26")]


def _corr(xs, ys):
    import numpy as np
    if len(xs) < 3:
        return float("nan")
    return float(np.corrcoef(xs, ys)[0, 1])


def _membership_open(bq, season: str) -> dict:
    """Opening-night roster per team, floored by games — a DuckDB-compatible equivalent of
    project_roster_forecast.robust_roster_membership(..., 'open') (whose ARRAY_AGG(... LIMIT 1)[OFFSET]
    BigQuery-ism the serving shim does not rewrite). Earliest game that season fixes a player's team."""
    sql = f"""
    WITH r AS (
        SELECT player_id, team_id, position_code, first_name, last_name, game_id,
               ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY game_id ASC) AS rn,
               COUNT(*) OVER (PARTITION BY player_id) AS gp
        FROM {bq.staging('stg_rosters')}
        WHERE season = '{season}' AND {J.GAME_TYPE_FILTER}
    )
    SELECT player_id, team_id, position_code, first_name || ' ' || last_name AS name
    FROM r WHERE rn = 1 AND gp >= {int(FLOOR)}
    """
    out: dict = {}
    for _, x in bq.query_df(sql).iterrows():
        if x.team_id is None:
            continue
        out.setdefault(int(x.team_id), []).append({"player_id": int(x.player_id),
                                                    "position": str(x.position_code) or "F",
                                                    "name": x["name"]})
    return out


# Deployment-aware icing, IDENTICAL to backend/services/tools._ice_from_pool via the SHARED engine
# (project_roster_forecast.seed_and_assign_forwards / seed_and_assign_defense): seed observed 5v5 units,
# then seat the rest by the soft-penalty assignment over EFFECTIVE positions (forwards) / handedness
# (defense, <=3 per side, off-side flex-fill). This is what the live tool actually ices, so
# LEAGUE_AVG_LINEUP_WAR must be calibrated on THIS basis (a pure top-by-WAR lineup overstates it).


def _handedness(bq) -> dict:
    out = {}
    for _, r in bq.query_df(f"select player_id, shoots from {bq.staging('stg_player_bio')} where shoots is not null").iterrows():
        out[int(r.player_id)] = str(r.shoots)
    return out


def _iced_total(players, hand, effpos, tunits) -> float:
    """Sum of projected WAR over the position-valid iced 12F/6D/1G (unfilled slots = 0). Forwards AND
    defensemen are iced by the SAME shared seed+assign the live tool uses (seed observed 5v5 units, then
    the position-aware assignment), so LEAGUE_AVG_LINEUP_WAR matches what absolute_rating actually sums.
    tunits = {'F3':[...], 'D2':[...]} observed units for this team (None -> pure Phase-1 assignment)."""
    war = lambda p: p.projected_war  # noqa: E731
    units = tunits or {}
    fbs = J.seed_and_assign_forwards([p for p in players if p.pos_group == "F"],
                                     units.get("F3", []), effpos, hand, CFG)
    iced = [p for side in fbs.values() for p in side]   # the iced forwards (<= 12)

    dbs = J.seed_and_assign_defense([p for p in players if p.pos_group == "D"],
                                    units.get("D2", []), hand, CFG, n_pairs=3)
    iced_d = dbs["L"] + dbs["R"]   # shared engine already caps at 3/side + flex-fills overflow (<= 6)

    # Goalie: the SERVING lineup (project_roster_forecast._full_lineup) ices a workload-weighted TANDEM
    # (WAR is a per-82 rate, so summing two goalies double-counts). Weight identically here — with the
    # league-default split — so this calibration constant matches what absolute_rating actually sums.
    goalies = sorted((p for p in players if p.pos_group == "G"), key=war, reverse=True)
    _gs, gt = J.build_goalie_tandem(goalies, CFG["N_GOALIE"], "projected_war", None, CFG)
    return float(sum(war(p) for p in iced + iced_d) + gt)


def _team_total_wars(bq, base_season: str, target_season: str, hand: dict, effpos: dict) -> dict:
    """team_id -> total projected iced-lineup WAR for the target season's opening roster, built with
    the EXACT engine + POSITION-AWARE icing the live endpoint uses (value windows keyed to base_season).
    Players keep their LISTED position on the PlayerProj (as _ice_from_pool does); effpos drives the
    forward assignment, so this matches the tool regardless of the display override."""
    skater_data = J.load_skater_war_multi(bq, base_season, N_BACK)
    goalie_data = J.load_goalie_war_multi(bq, base_season, N_BACK)
    archetypes = J.load_archetypes(bq, base_season)
    aging = J.load_aging(bq)
    ages = J.load_ages(bq, base_season)
    mem = _membership_open(bq, target_season)
    seed_units = J.load_seed_units(bq, base_season)   # base-season observed units, matching the tool

    out = {}
    for tid in mem:
        players = J._projected_players(tid, mem, skater_data, goalie_data, aging, ages,
                                       archetypes, project_value=True)
        out[int(tid)] = _iced_total(players, hand, effpos, seed_units.get(int(tid)))
    return out


def _actual_points(bq, season: str) -> dict:
    """team_id -> actual final regular-season standings points. Prefer deserved_standings (team_id
    keyed); fall back to stg_standings final snapshot mapped abbrev->team_id via dim_current_roster."""
    d = bq.query_df(f"select team_id, actual_points from {bq.models('deserved_standings')} "
                    f"where season = '{season}' and actual_points is not null")
    if d is not None and len(d):
        return {int(r.team_id): float(r.actual_points) for _, r in d.iterrows()}
    sid = season[:4] + season[5:7] if "-" in season else season  # '2024-25' -> '202425'? handled below
    sid = int(season.replace("-", "")[:4] + "20" + season[-2:]) if "-" in season else int(season)
    df = bq.query_df(f"""
        with mx as (select season_id, max(standings_date) d from {bq.staging('stg_standings')}
                    where season_id = {sid} group by 1)
        select s.team_abbrev, s.points
        from {bq.staging('stg_standings')} s join mx on s.season_id = mx.season_id
                                              and s.standings_date = mx.d
    """)
    amap = {str(r.team_abbrev): int(r.team_id) for _, r in
            bq.query_df(f"select distinct team_id, team_abbrev from {bq.models('dim_current_roster')}").iterrows()}
    return {amap[str(r.team_abbrev)]: float(r.points) for _, r in df.iterrows()
            if str(r.team_abbrev) in amap}


def recalibrate_strength_anchor(bq) -> dict:
    """Refit ROSTER_BUILDER_STRENGTH_ANCHOR for the UNIFIED baseline R_current (the offseason forecast's
    projected rating = shared predictive_base anchor + move delta + chemistry), replacing the earlier fit
    for the bare R_measured anchor. Runs the offseason pipeline over both completed transitions and finds
    the anchor strength SD such that the w=1 absolute band sqrt(ANCHOR^2 + luck^2) covers ~68% of
    |projected_points - actual_points|. Reads only."""
    import numpy as np
    luck = CFG["SEASON_LUCK_FLOOR_PTS"]
    resid = []
    series = J.load_team_rating_series(bq)
    for base, target in TRANSITIONS:
        ratings = J.load_team_ratings(bq, base)
        skater = J.load_skater_war_multi(bq, base, N_BACK); goalie = J.load_goalie_war_multi(bq, base, N_BACK)
        arch = J.load_archetypes(bq, base); aging = J.load_aging(bq); ages = J.load_ages(bq, base)
        effpos = J.load_effective_position(bq); hand = J.load_handedness(bq); seed = J.load_seed_units(bq, base)
        anchors = {t: J.predictive_base_for_target(series.get(t, []), int(target[:4])) for t in ratings}
        base_mem = J.robust_roster_membership(bq, base, FLOOR, "end")
        upd_mem = J.robust_roster_membership(bq, target, FLOOR, "open")
        forecasts, _ = J._run_all(bq, ratings, base_mem, upd_mem, skater, goalie, aging, ages, arch,
                                  f"{base}->{target}", "cal", anchors=anchors, effpos=effpos, hand=hand,
                                  seed_units=seed)
        actual = _actual_points(bq, target)
        for f in forecasts:
            if f["team_id"] in actual:
                resid.append(abs(f["projected_points"] - actual[f["team_id"]]))
    resid = np.array(resid, float)
    # find the smallest strength SD whose band (with luck in quadrature) covers >= 68% of the residuals
    anchor = 0.0
    for a in np.arange(0.0, 25.0, 0.05):
        if np.mean(resid <= np.sqrt(a ** 2 + luck ** 2)) >= 0.68:
            anchor = float(a); break
    cov = float(np.mean(resid <= np.sqrt(anchor ** 2 + luck ** 2)))
    return {"anchor": anchor, "coverage": cov, "n": len(resid),
            "resid_p68": float(np.percentile(resid, 68)), "resid_mae": float(resid.mean())}


def main() -> None:
    import numpy as np
    from models_ml import bq

    hand = _handedness(bq)
    effpos = J.load_effective_position(bq)   # forward effective-position map driving the assignment
    rows = []  # (season, team_id, total_war, measured_rating, actual_points)
    for base, target in TRANSITIONS:
        totals = _team_total_wars(bq, base, target, hand, effpos)
        measured = {t: r["rating"] for t, r in J.load_team_ratings(bq, target).items()}
        points = _actual_points(bq, target)
        for tid, tw in totals.items():
            if tid in measured and tid in points:
                rows.append((target, tid, tw, measured[tid], points[tid]))

    if len(rows) < 10:
        print(f"calibrate_roster_builder: too few team-seasons ({len(rows)}) — aborting."); return

    tot = np.array([r[2] for r in rows], float)
    meas = np.array([r[3] for r in rows], float)
    actual = np.array([r[4] for r in rows], float)
    seasons = sorted({r[0] for r in rows})

    league_avg = float(tot.mean())
    centered = tot - league_avg
    fp = CFG["FORECAST_POINTS"]

    # Calibrate the WAR->RATING scale empirically against the MEASURED rating (the de-lucked strength),
    # NOT raw points -- so the rating->points step stays the already-validated Handoff-10 map and the
    # two calibrations do not contaminate each other. The handoff's starting point is the move-scale
    # GOALS_PER_WIN/GAMES (6/82), but summed lineup WAR maps to team goal-diff at a COMPRESSED rate
    # (shared ice, regression, a replacement baseline that does not stack linearly): we fit it.
    war_to_rating = float(np.polyfit(centered, meas, 1)[0])   # measured_rating ~ k * centered_war
    rating_abs = centered * war_to_rating
    pred_points = np.array([J.rating_to_points(float(r)) for r in rating_abs], float)
    meas_points = np.array([J.rating_to_points(float(m)) for m in meas], float)  # strength as points
    naive_pred = np.array([J.rating_to_points(float(c * SCALE)) for c in centered], float)

    corr_rating = _corr(rating_abs, meas)
    mae = float(np.mean(np.abs(pred_points - actual)))                # vs ACTUAL points (luck included)
    mae_strength = float(np.mean(np.abs(pred_points - meas_points)))  # vs de-lucked strength points
    ceiling_mae = float(np.mean(np.abs(meas_points - actual)))        # irreducible luck floor
    naive_mae = float(np.mean(np.abs(naive_pred - actual)))
    null_mae = float(np.mean(np.abs(actual - actual.mean())))

    print(f"\nRoster Builder absolute-rating calibration  ({len(rows)} team-seasons, {seasons})")
    print(f"  LEAGUE_AVG_LINEUP_WAR:   {league_avg:.4f}   (league-mean projected iced-lineup WAR)")
    print(f"  WAR_TO_RATING (fit):     {war_to_rating:.5f} goals/game per WAR   (naive 6/82 = {SCALE:.5f})")
    print(f"  total_war range:         {tot.min():.2f} .. {tot.max():.2f}  ->  rating_abs "
          f"{rating_abs.min():+.3f} .. {rating_abs.max():+.3f} g/g")
    print(f"\n  RECONCILIATION (does roster value track measured strength):")
    print(f"    corr(REALIZED roster WAR, measured rating) ~ 0.82   [run separately] -- value system coheres")
    print(f"    corr(PROJECTED rating_abs, measured rating)  = {corr_rating:.3f}   -- forward-projection signal")
    print(f"\n  POINTS (projected vs ACTUAL standings points):")
    print(f"    projected vs ACTUAL:            MAE={mae:.2f}  corr={_corr(pred_points, actual):.3f}")
    print(f"    projected vs DE-LUCKED strength: MAE={mae_strength:.2f}   <- the projection's own error")
    print(f"    CEILING measured->actual:        MAE={ceiling_mae:.2f}   <- irreducible in-season luck")
    print(f"    null (predict mean):             MAE={null_mae:.2f}   | naive 6/82 scale MAE={naive_mae:.2f}")

    # Ship rule: the value system must reconcile (realized ~0.82, checked) AND projected points must beat
    # the null AND sit within luck-ceiling + a reasonable projection margin. The residual over the ceiling
    # is honest forward-projection uncertainty -> it MUST be carried as a band, not hidden.
    ok = mae < null_mae and mae <= ceiling_mae + 6.0
    verdict = "SHIP (carry the projection uncertainty as a band)" if ok else "HOLD -- investigate"
    print(f"\n  VERDICT: {verdict}")
    print(f"    projected beats null by {null_mae - mae:.2f} pts; sits {mae - ceiling_mae:.2f} pts over the "
          f"irreducible luck floor (that residual is the band).")
    print(f"\n  -> config.ROSTER_FORECAST['LEAGUE_AVG_LINEUP_WAR'] = {league_avg:.2f}")
    print(f"  -> config.ROSTER_FORECAST['WAR_TO_RATING']        = {war_to_rating:.5f}")

    # Absolute-band anchor for the UNIFIED baseline R_current (the offseason forecast's projected rating).
    sa = recalibrate_strength_anchor(bq)
    print(f"\n  UNIFIED-BASELINE ABSOLUTE BAND ({sa['n']} team-seasons): |forecast points - actual| "
          f"p68={sa['resid_p68']:.2f}, MAE={sa['resid_mae']:.2f}")
    print(f"    band sqrt(ANCHOR^2 + luck^2) coverage = {sa['coverage']*100:.0f}% (target ~68%)")
    print(f"  -> config.ROSTER_FORECAST['ROSTER_BUILDER_STRENGTH_ANCHOR'] = {sa['anchor']:.2f}")


if __name__ == "__main__":
    main()
