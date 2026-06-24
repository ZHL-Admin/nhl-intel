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


def main() -> None:
    from models_ml import bq

    base_season, next_s = "2024-25", "2025-26"
    print(f"roster-forecast backtest: {base_season} -> {next_s}")

    # Projected: run the same pipeline the job runs under --backtest (updated = actual next rosters).
    window = J.value_season_window(bq, base_season)
    ratings = J.load_team_ratings(bq, base_season)
    gar_rows = J.load_skater_gar(bq, window)
    goalie_rows = J.load_goalie_gar(bq, window)
    archetypes = J.load_archetypes(bq, base_season)
    aging = J.load_aging(bq)
    ages = J.load_ages(bq, base_season)
    floor = J.CFG["MIN_GAMES_ROSTER"]
    base_mem = J.robust_roster_membership(bq, base_season, floor, "end")   # 2024-25 season-end
    upd_mem = J.robust_roster_membership(bq, next_s, floor, "open")        # 2025-26 opening night
    trans = f"{base_season}->{next_s}"
    forecasts, _ = J._run_all(bq, ratings, base_mem, upd_mem, gar_rows, goalie_rows,
                              aging, ages, archetypes, trans, "backtest")
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
    print("\nCopy these into docs/methodology/offseason-forecast.md (Backtest calibration). They are a "
          "prior the verdict inherits, not a guarantee.")


if __name__ == "__main__":
    main()
