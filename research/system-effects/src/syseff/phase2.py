"""Phase 2 runner — reliability (2.2) and the discontinuity test (2.3), plus the
consolidation sensitivity, recomputed plausibility, and example fingerprint tables.

Reproducible from cache: reads cached seq/prim/deploy + frozen assets, writes
reports/phase2_analysis.json. Seeded (config.SEED)."""
from __future__ import annotations

import json
import math
import random

import polars as pl

from . import config, fingerprints as F, regime_ledger as R

random.seed(config.SEED)

METRICS = [
    "pace", "rush_share_for", "cycle_share_for", "forecheck_share_for",
    "point_shot_share_for", "rush_share_against", "cycle_share_against",
    "loc_inner_against", "loc_outer_against", "loc_point_against",
    "forecheck_pressure_per60", "top6_fwd_toi_share", "zone_start_polarization",
]


def _load(dir_, seasons):
    return pl.concat([pl.read_parquet(dir_ / f"{s.replace('-', '_')}.parquet")
                      for s in seasons], how="diagonal_relaxed")


def metric_vector(prim, deploy, game_ids, team_id) -> dict:
    m = F.aggregate(prim, game_ids, team_id)
    m.update(F.deployment_over(deploy, game_ids, team_id))
    return m


# ---------------------------------------------------------------- regime game sets
def consolidated_regime_games(tg: pl.DataFrame, raw_annotated: pl.DataFrame):
    """Yield (team_id, cons_id, season_label, [game_ids]) per consolidated regime-season."""
    reg = R.annotate_regimes(tg.filter(pl.col("coach").is_not_null()))
    raw_start = reg.group_by("regime_seq").agg(
        team_id=pl.col("team_id").first(), start_game_id=pl.col("game_id").min())
    reg = reg.join(raw_start, on="regime_seq")
    key = raw_annotated.select("team_id", "start_game_id", "consolidated_start_game_id")
    reg = reg.join(key, on=["team_id", "start_game_id"], how="left")
    return reg  # per team-game: has consolidated_start_game_id + season_label


# ---------------------------------------------------------------- reliability (2.2)
def reliability(reg, prim, deploy) -> dict:
    # consolidated regimes of 40+ games; split odd/even by chronological order
    regimes = (reg.group_by("team_id", "consolidated_start_game_id")
               .agg(n=pl.len()).filter(pl.col("n") >= 40))
    pairs = {m: ([], []) for m in METRICS}
    for row in regimes.iter_rows(named=True):
        g = (reg.filter((pl.col("team_id") == row["team_id"])
                        & (pl.col("consolidated_start_game_id") == row["consolidated_start_game_id"]))
             .sort("game_id")["game_id"].to_list())
        g = list(dict.fromkeys(g))  # unique preserve order
        odd = g[0::2]; even = g[1::2]
        vo = metric_vector(prim, deploy, odd, row["team_id"])
        ve = metric_vector(prim, deploy, even, row["team_id"])
        for m in METRICS:
            a, b = vo.get(m), ve.get(m)
            if a is not None and b is not None and not (isinstance(a, float) and math.isnan(a)):
                pairs[m][0].append(a); pairs[m][1].append(b)
    out = {}
    for m in METRICS:
        xs, ys = pairs[m]
        out[m] = {"n_regimes": len(xs), "split_half_r": round(_pearson(xs, ys), 3) if len(xs) > 5 else None}
    out["_note_flagged"] = [m for m in METRICS
                            if out[m]["split_half_r"] is not None and out[m]["split_half_r"] < 0.5]
    return out


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs); syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else float("nan")


# ---------------------------------------------------------------- cohort C old/new sets
def cohort_C_changes(tg: pl.DataFrame, min_games=15):
    reg = R.annotate_regimes(tg.filter(pl.col("coach").is_not_null()))
    meta = (reg.group_by("regime_seq").agg(
        team_id=pl.col("team_id").first(), coach=pl.col("coach").first(),
        start_syear=pl.col("season_start_year").first(), start_game_id=pl.col("game_id").min(),
        first_season=pl.col("season_label").first(), last_season=pl.col("season_label").last())
        .sort(["team_id", "start_syear", "start_game_id"]))
    reg_season = reg.group_by("regime_seq", "season_label").agg(games=pl.col("game_id").unique())
    rs = {(r["regime_seq"], r["season_label"]): r["games"] for r in reg_season.to_dicts()}
    meta = meta.with_columns(
        prev_seq=pl.col("regime_seq").shift(1).over("team_id"),
        prev_last_season=pl.col("last_season").shift(1).over("team_id"),
        prev_coach=pl.col("coach").shift(1).over("team_id"))
    changes = []
    for c in meta.filter(pl.col("prev_seq").is_not_null()
                         & (pl.col("prev_last_season") == pl.col("first_season"))).to_dicts():
        S = c["first_season"]
        newg = rs.get((c["regime_seq"], S), []); oldg = rs.get((c["prev_seq"], S), [])
        if len(newg) >= min_games and len(oldg) >= min_games:
            changes.append({"team_id": c["team_id"], "season": S, "old_coach": c["prev_coach"],
                            "new_coach": c["coach"], "old_games": list(oldg), "new_games": list(newg)})
    return changes


def one_regime_team_seasons(reg):
    """No-change team-seasons: exactly one consolidated regime covering the season."""
    per = reg.group_by("team_id", "season_label").agg(
        nreg=pl.col("consolidated_start_game_id").n_unique(),
        games=pl.col("game_id").unique(), n=pl.len())
    return per.filter((pl.col("nreg") == 1) & (pl.col("n") >= 30))


# ---------------------------------------------------------------- discontinuity (2.3)
def discontinuity(tg, reg, prim, deploy) -> dict:
    changes = cohort_C_changes(tg)
    real = {m: [] for m in METRICS}
    for c in changes:
        vo = metric_vector(prim, deploy, c["old_games"], c["team_id"])
        vn = metric_vector(prim, deploy, c["new_games"], c["team_id"])
        for m in METRICS:
            a, b = vo.get(m), vn.get(m)
            if a is not None and b is not None:
                real[m].append(abs(b - a))
    # placebo: random midpoint split of one-regime team-seasons
    placebo = {m: [] for m in METRICS}
    for row in one_regime_team_seasons(reg).iter_rows(named=True):
        g = (reg.filter((pl.col("team_id") == row["team_id"])
                        & (pl.col("season_label") == row["season_label"]))
             .sort("game_id")["game_id"].unique(maintain_order=True).to_list())
        if len(g) < 30:
            continue
        cut = random.randint(len(g) // 3, 2 * len(g) // 3)
        h1, h2 = g[:cut], g[cut:]
        v1 = metric_vector(prim, deploy, h1, row["team_id"])
        v2 = metric_vector(prim, deploy, h2, row["team_id"])
        for m in METRICS:
            a, b = v1.get(m), v2.get(m)
            if a is not None and b is not None:
                placebo[m].append(abs(b - a))
    out = {"n_real_changes": len(changes), "per_metric": {}}
    for m in METRICS:
        rr, pp = real[m], placebo[m]
        if len(rr) < 5 or len(pp) < 5:
            out["per_metric"][m] = {"n_real": len(rr), "n_placebo": len(pp), "insufficient": True}
            continue
        mr, mp = _mean(rr), _mean(pp)
        out["per_metric"][m] = {
            "n_real": len(rr), "n_placebo": len(pp),
            "median_real_abs_shift": round(_median(rr), 5),
            "median_placebo_abs_shift": round(_median(pp), 5),
            "mean_real": round(mr, 5), "mean_placebo": round(mp, 5),
            "ratio_mean": round(mr / mp, 3) if mp else None,
            "perm_p": round(_perm_p(rr, pp), 4),
            "coaching_sensitive": (mr / mp > 1.25 if mp else False) and _perm_p(rr, pp) < 0.05,
        }
    return out


def _mean(x): return sum(x) / len(x)
def _median(x):
    s = sorted(x); n = len(s); return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
def _perm_p(a, b, iters=2000):
    obs = _mean(a) - _mean(b)
    pool = a + b; na = len(a); cnt = 0
    for _ in range(iters):
        random.shuffle(pool)
        if (_mean(pool[:na]) - _mean(pool[na:])) >= obs:
            cnt += 1
    return (cnt + 1) / (iters + 1)


# ---------------------------------------------------------------- runner
def run(seasons=None) -> dict:
    seasons = seasons or config.SEASONS_ALL
    prim = _load(F.PRIM_DIR, seasons)
    deploy = _load(F.DEPLOY_DIR, seasons)
    gc = R.assemble_game_coaches(); tg = R.to_team_games(gc)
    raw = R.build_ledger(tg.filter(pl.col("coach").is_not_null()))
    raw_annot, _ = R.consolidate_ledger(raw, k=4)
    reg = consolidated_regime_games(tg, raw_annot)

    out = {
        "reliability": reliability(reg, prim, deploy),
        "discontinuity": discontinuity(tg, reg, prim, deploy),
        "examples": examples(prim, deploy, tg, reg, raw_annot),
    }
    (config.REPORTS / "phase2_analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def examples(prim, deploy, tg, reg, raw_annot) -> dict:
    def team_season_games(team, season):
        return reg.filter((pl.col("team_id") == team) & (pl.col("season_label") == season)
                          )["game_id"].unique().to_list()
    ex = {}
    ex["CHI_2012-13"] = metric_vector(prim, deploy, team_season_games(16, "2012-13"), 16)
    ex["CAR_2023-24"] = metric_vector(prim, deploy, team_season_games(12, "2023-24"), 12)
    ch = cohort_C_changes(tg)
    # pick an illustrative change: prefer BOS 2024-25 (Montgomery->Sacco) else first
    pick = next((c for c in ch if c["team_id"] == 6 and c["season"] == "2024-25"), ch[0] if ch else None)
    if pick:
        ex["change_old"] = {"team": pick["team_id"], "season": pick["season"],
                            "coach": pick["old_coach"], **metric_vector(prim, deploy, pick["old_games"], pick["team_id"])}
        ex["change_new"] = {"team": pick["team_id"], "season": pick["season"],
                            "coach": pick["new_coach"], **metric_vector(prim, deploy, pick["new_games"], pick["team_id"])}
    return ex


if __name__ == "__main__":
    r = run()
    print("reliability flagged:", r["reliability"]["_note_flagged"], flush=True)
    print("discontinuity sensitive:",
          [m for m, v in r["discontinuity"]["per_metric"].items() if v.get("coaching_sensitive")], flush=True)
