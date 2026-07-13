"""Link A (GATE) — does a player's behavior change by partner, measurably (beyond deployment)?

A.2 within-player across-partner test: for focal players with 3+ qualifying partners, is A's
    partner-specific deviation d(A,B) = x(A,B) − mean_B x(A,B) a REAL, repeating thing? Split each
    (A,B) into odd/even shared games; the reliability of the deviation = TOI-weighted corr(d_odd,
    d_even). If A genuinely behaves differently with B, the odd- and even-game deviations agree; if
    it is sampling noise, they don't. Placebo = shuffle partner labels within player-season.
A.3 deployment control: residualize each axis on the shared-minutes deployment context (OZ-start
    share, score-state mix) and re-run A.2 on the residual. Movement that vanishes is deployment.
A.4 verdict (pre-stated): PASS if >=2 axes show real across-partner movement beating placebo at
    p<0.05 AND retaining material movement after the deployment control (retained reliability >=
    half the raw AND still > 0.10). If only shooting-deference survives -> proceed scoped to it.
    If nothing survives the deployment control -> dependency is deployment in disguise; STOP.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import config
from . import behavior as B

FLOOR = 6000                 # 100 shared 5v5 minutes (primary; A.1 sensitivity 75/150 reported)
MIN_PARTNERS = 3
N_PERM = 500                 # scoped placebo count (reported)
RETAIN_FRAC = 0.5            # deployment-controlled reliability must keep >= half the raw
RETAIN_MIN = 0.10           # ...and still exceed 0.10
AXES = B.AXES
CTX = ["oz_start_share", "share_lead", "share_trail"]


def _load(floor: int = FLOOR) -> pl.DataFrame:
    d = pl.concat([pl.read_parquet(p) for p in sorted(B.BEHAV_DIR.glob("*.parquet"))],
                  how="vertical_relaxed").filter(pl.col("shared_toi") >= floor)
    # restrict to focal players with >= MIN_PARTNERS qualifying partners (per season)
    keep = d.group_by("A", "season_label").len().filter(pl.col("len") >= MIN_PARTNERS)
    return d.join(keep.select("A", "season_label"), on=["A", "season_label"], how="inner")


def _pair_context() -> pl.DataFrame:
    """Deployment context per unordered pair-season (from the validated Chemistry pairs corpus)."""
    p = pl.read_parquet(config.CHEM_ROOT / "data" / "parquet" / "frozen" / "pairs_corpus.parquet")
    return (p.group_by("season_label", "a", "b").agg(
        oz_start_share=(pl.col("oz_start_share") * pl.col("toi")).sum() / pl.col("toi").sum(),
        share_lead=(pl.col("share_lead") * pl.col("toi")).sum() / pl.col("toi").sum(),
        share_trail=(pl.col("share_trail") * pl.col("toi")).sum() / pl.col("toi").sum()))


def _attach_context(d: pl.DataFrame) -> pl.DataFrame:
    ctx = _pair_context()
    d = d.with_columns(lo=pl.min_horizontal("A", "B"), hi=pl.max_horizontal("A", "B"))
    return d.join(ctx.rename({"a": "lo", "b": "hi"}), on=["season_label", "lo", "hi"], how="left")


def _wcorr(x, y, w):
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    vx, vy = np.average((x - mx) ** 2, weights=w), np.average((y - my) ** 2, weights=w)
    return float(cov / np.sqrt(vx * vy)) if vx > 0 and vy > 0 else float("nan")


def _deviation_reliability(d: pl.DataFrame, odd_col: str, even_col: str) -> dict:
    """Demean odd/even within (A,season), then TOI-weighted corr of the partner deviations, with a
    within-player partner-label-shuffle placebo."""
    s = d.drop_nulls([odd_col, even_col])
    s = s.with_columns(
        d_odd=pl.col(odd_col) - pl.col(odd_col).mean().over("A", "season_label"),
        d_even=pl.col(even_col) - pl.col(even_col).mean().over("A", "season_label"))
    x, y = s["d_odd"].to_numpy(), s["d_even"].to_numpy()
    w = s["shared_toi"].to_numpy().astype(float)
    r = _wcorr(x, y, w)
    # placebo: within each (A,season) permute the even-deviation across partners (vectorized)
    cell = s.select(pl.concat_str([pl.col("A").cast(pl.Utf8), pl.lit("|"), pl.col("season_label")]))
    _, cid = np.unique(cell.to_series().to_numpy(), return_inverse=True)
    rng = np.random.default_rng(config.SEED)
    n = len(y)
    slot = np.lexsort((np.arange(n), cid))
    perms = np.empty(N_PERM)
    for k in range(N_PERM):
        src = np.lexsort((rng.random(n), cid))
        p = np.empty(n, dtype=np.int64); p[slot] = src
        perms[k] = _wcorr(x, y[p], w)
    return {"n": s.height, "reliability": r, "placebo_mean": float(np.mean(perms)),
            "p": float((np.sum(perms >= r) + 1) / (N_PERM + 1)),
            "across_partner_sd_median": float(
                s.group_by("A", "season_label").agg(sd=pl.col(odd_col).std()).drop_nulls()["sd"].median())}


def run(floor: int = FLOOR) -> dict:
    d = _attach_context(_load(floor))
    out = {"seed": config.SEED_TAG, "floor_min": floor // 60, "min_partners": MIN_PARTNERS,
           "n_perm": N_PERM, "n_focal_partner_rows": d.height,
           "n_focal_players": d.select("A", "season_label").unique().height, "axes": {}}
    for ax in AXES:
        raw = _deviation_reliability(d, f"{ax}_odd", f"{ax}_even")
        # deployment control: residualize the axis, re-split isn't possible per-half from one OLS, so
        # residualize odd and even on the SAME full-season context OLS (context is pair-level).
        dr = _residualize_halves(d, ax)
        ctrl = _deviation_reliability(dr, f"{ax}_odd_rax", f"{ax}_even_rax")
        retained = ctrl["reliability"] / raw["reliability"] if raw["reliability"] > 0 else None
        moves = raw["reliability"] > 0 and raw["p"] < 0.05
        survives = (moves and retained is not None and retained >= RETAIN_FRAC
                    and ctrl["reliability"] >= RETAIN_MIN and ctrl["p"] < 0.05)
        out["axes"][ax] = {"raw": raw, "deployment_controlled": ctrl,
                           "retained_frac": retained, "moves_by_partner": moves,
                           "survives_deployment": survives}
    out["verdict"] = _verdict(out["axes"])
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "linkA_analysis.json", "w") as f:
        json.dump(out, f, indent=2)
    return out


def _residualize_halves(d: pl.DataFrame, ax: str) -> pl.DataFrame:
    """Residualize the odd and even axis on the shared full-season deployment context (one OLS on the
    full axis; context is pair-level so it applies to both halves)."""
    sub = d.drop_nulls([f"{ax}_odd", f"{ax}_even"] + CTX)
    X = np.column_stack([np.ones(sub.height)] + [sub[c].to_numpy() for c in CTX])
    out = sub
    for half in ("odd", "even"):
        y = sub[f"{ax}_{half}"].to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        out = out.with_columns(pl.Series(f"{ax}_{half}_rax", y - X @ beta))
    return out


def _verdict(axes: dict) -> dict:
    survivors = [a for a, v in axes.items() if v["survives_deployment"]]
    movers = [a for a, v in axes.items() if v["moves_by_partner"]]
    shooting = {"A_sh60", "A_shot_share"}
    if len(survivors) >= 2:
        outcome = "PASS"
    elif survivors and set(survivors) <= shooting:
        outcome = "PASS_SHOOTING_ONLY"                 # the owner's specific interest; proceed scoped
    elif len(survivors) == 1:
        outcome = "PASS_SCOPED"                         # one non-shooting axis survives
    else:
        outcome = "FAIL_DEPLOYMENT_IN_DISGUISE"
    return {"movers_beating_placebo": movers, "survivors_after_deployment": survivors,
            "n_survivors": len(survivors), "outcome": outcome}


if __name__ == "__main__":
    r = run()
    print(f"focal players: {r['n_focal_players']}  (A,B) rows: {r['n_focal_partner_rows']}")
    for ax, v in r["axes"].items():
        raw, ctrl = v["raw"], v["deployment_controlled"]
        print(f"  {ax:13s} raw rel={raw['reliability']:+.3f}(p={raw['p']:.3f}) "
              f"-> deploy-ctrl={ctrl['reliability']:+.3f}(p={ctrl['p']:.3f}) retained={v['retained_frac']} "
              f"survives={v['survives_deployment']}  [across-partner SD~{raw['across_partner_sd_median']:.2f}]")
    print("VERDICT:", r["verdict"]["outcome"], "survivors:", r["verdict"]["survivors_after_deployment"])
