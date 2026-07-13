"""Backtest calibration for the offseason roster forecast (reads only; writes nothing).

Projects the 2024-25 final rosters forward to 2025-26 (base = 2024-25 end-of-season team_ratings;
updated = the ACTUAL 2025-26 rosters) and compares each team's PROJECTED 2025-26 rank delta to its
ACTUAL 2025-26 power-rating rank delta. Reports Spearman rank correlation and mean absolute rank
error — the tool's calibration, which the verdict language inherits as a prior, not a guarantee.

Run: python -m models_ml.validate_roster_forecast   (or: make roster-forecast-validate)
"""

from __future__ import annotations

from models_ml import project_roster_forecast as J


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rho = Pearson correlation of the ranks (no scipy dependency)."""
    import numpy as np
    if len(xs) < 3:
        return float("nan")
    rx = np.argsort(np.argsort(xs)).astype(float)
    ry = np.argsort(np.argsort(ys)).astype(float)
    rx -= rx.mean(); ry -= ry.mean()
    denom = (np.sqrt((rx ** 2).sum()) * np.sqrt((ry ** 2).sum()))
    return float((rx * ry).sum() / denom) if denom else float("nan")


def _rank_desc(values: dict) -> dict:
    """team_id -> rank (1 = best/highest value)."""
    order = sorted(values, key=lambda t: values[t], reverse=True)
    return {tid: i + 1 for i, tid in enumerate(order)}


def points_calibration() -> None:
    """Validate the rating -> projected-points map (project_roster_forecast.rating_to_points, constants
    in config.FORECAST_POINTS) against ACTUAL final standings points. Joins each (team, season)'s final
    team_ratings.total_rating to deserved_standings.actual_points, then:
      * recomputes the OLS fit (intercept/slope/R2) so FORECAST_POINTS can be refreshed from data, and
      * reports MAE / correlation / residual spread of the SHIPPED mapping's predicted points vs actual.
    Flags loudly if MAE is implausibly large (> 10 points) rather than trusting a bad fit.
    This is how the conversion is proven, not asserted. Reads only.
    """
    import numpy as np
    from models_ml import bq

    sql = f"""
        with fin as (
            select team_id, season, total_rating,
                   row_number() over (partition by team_id, season
                                      order by game_date desc, games_played desc) as rn
            from {bq.models('team_ratings')}
        )
        select f.season, f.team_id, f.total_rating as r, d.actual_points as p
        from fin f
        join {bq.models('deserved_standings')} d using (team_id, season)
        where f.rn = 1 and d.actual_points is not null
    """
    df = bq.query_df(sql)
    if df is None or len(df) < 5:
        print("\npoints calibration: too few (team, season) pairs to validate — skipped.")
        return

    R = df["r"].to_numpy(dtype=float)
    P = df["p"].to_numpy(dtype=float)
    seasons = sorted(df["season"].unique().tolist())

    # Refit OLS from the data (so the shipped constants can be refreshed when more seasons land).
    slope, intercept = np.polyfit(R, P, 1)
    fit_pred = intercept + slope * R
    ss_res = float(np.sum((P - fit_pred) ** 2)); ss_tot = float(np.sum((P - P.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")

    # Score the SHIPPED mapping (config constants) the serving layer actually uses.
    pred = np.array([J.rating_to_points(float(r)) for r in R], dtype=float)
    mae = float(np.mean(np.abs(P - pred)))
    corr = float(np.corrcoef(pred, P)[0, 1]) if len(P) > 1 else float("nan")
    resid_sd = float(np.std(P - pred))

    fp = J.CFG["FORECAST_POINTS"]
    span = f"{seasons[0]}..{seasons[-1]}" if len(seasons) > 1 else seasons[0]
    print(f"\npoints calibration: {len(df)} team-seasons across {len(seasons)} season(s) ({span})")
    print(f"  refit OLS:        intercept={intercept:.2f}  slope={slope:.2f}  R^2={r2:.3f}")
    print(f"  shipped mapping:  intercept={fp['intercept']}  slope={fp['slope']}  ceiling={fp['ceiling']}")
    print(f"  predicted vs actual points -> MAE={mae:.2f}  corr={corr:.3f}  residual_sd={resid_sd:.2f}")
    if mae > 10:
        print(f"  ** FLAG: MAE {mae:.1f} > 10 points — rating->points looks miscalibrated. Refresh "
              f"config.ROSTER_FORECAST['FORECAST_POINTS'] from the refit OLS above before trusting "
              f"projected points.")
    else:
        print("  OK: MAE within tolerance (<= 10 points).")


def main() -> None:
    from models_ml import bq

    base_season, next_s = "2024-25", "2025-26"
    print(f"roster-forecast backtest: {base_season} -> {next_s}")

    # Projected: run the same pipeline the job runs under --backtest (updated = actual next rosters).
    n_back = J.CFG["PROJ_WINDOWS"]
    ratings = J.load_team_ratings(bq, base_season)
    skater_data = J.load_skater_war_multi(bq, base_season, n_back)
    goalie_data = J.load_goalie_war_multi(bq, base_season, n_back)
    archetypes = J.load_archetypes(bq, base_season)
    aging = J.load_aging(bq)
    ages = J.load_ages(bq, base_season)
    floor = J.CFG["MIN_GAMES_ROSTER"]
    base_mem = J.robust_roster_membership(bq, base_season, floor, "end")   # 2024-25 season-end
    upd_mem = J.robust_roster_membership(bq, next_s, floor, "open")        # 2025-26 opening night
    trans = f"{base_season}->{next_s}"
    # Shared predictive_base anchor for the target season (2-year regressed, seasons < target year).
    series = J.load_team_rating_series(bq)
    anchors = {tid: J.predictive_base_for_target(series.get(tid, []), int(next_s[:4])) for tid in ratings}
    forecasts, _ = J._run_all(bq, ratings, base_mem, upd_mem, skater_data, goalie_data,
                              aging, ages, archetypes, trans, "backtest", anchors=anchors)
    J._rank_and_finalize(forecasts)

    # Actual: rank delta from real end-of-season team_ratings (2024-25 -> 2025-26).
    base_ratings = {t: r["rating"] for t, r in ratings.items()}
    actual_next = {t: r["rating"] for t, r in J.load_team_ratings(bq, next_s).items()}
    base_rank = _rank_desc(base_ratings)
    actual_rank = _rank_desc(actual_next)

    proj_delta, actual_delta = [], []
    for f in forecasts:
        tid = f["team_id"]
        if tid not in actual_rank or tid not in base_rank:
            continue
        proj_delta.append(f["projected_rank_delta"])
        actual_delta.append(base_rank[tid] - actual_rank[tid])

    rho = _spearman(proj_delta, actual_delta)
    mae = sum(abs(p - a) for p, a in zip(proj_delta, actual_delta)) / max(1, len(proj_delta))
    print(f"teams: {len(proj_delta)}")
    print(f"Spearman rank-delta correlation: {rho:.3f}")
    print(f"mean absolute rank-delta error:  {mae:.2f} positions")

    # Points calibration: prove the rating -> projected-points map against actual standings.
    points_calibration()

    print("\nCopy these into docs/methodology/offseason-forecast.md (Backtest calibration). They are a "
          "prior the verdict inherits, not a guarantee.")


if __name__ == "__main__":
    main()
