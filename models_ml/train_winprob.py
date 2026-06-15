"""
Train the win-probability model (Phase 2.4).

Logistic regression on a (seconds-remaining x score-diff) one-hot interaction plus
strength differential, goalie-pulled flags, OT state, and a pregame team-strength prior.
Target: the home team won (OT/SO wins count as wins). Interpretable and near-monotone.

Splits: train 2012-13 .. 2024-25, holdout 2025-26 (reported only). A 30-second training
grid keeps the fit fast; scoring (score_winprob.py) uses a finer 10-second grid.

Run:  python -m models_ml.train_winprob [--sample-frac 0.5] [--dry-run]
Outputs: models_ml/artifacts/winprob_v1.joblib + manifest, docs/methodology/win-probability.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

from models_ml import bq, config
from models_ml.winprob_features import (
    add_state_features, build_pull_sql, make_design,
)

MODEL_VERSION = "winprob_v1"
ARTIFACT_DIR = Path(__file__).parent / "artifacts"
METHODOLOGY = Path(__file__).parent.parent / "docs" / "methodology" / "win-probability.md"

TRAIN_MAX_SEASON = "2024-25"
HOLDOUT_SEASON = "2025-26"
TRAIN_STEP = 30   # seconds between training-grid samples
GAME_SAMPLE = 4   # keep 1-in-N games for training (download is the bottleneck)


def decile_calibration(y: np.ndarray, p: np.ndarray) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, 11))
    edges[0], edges[-1] = -np.inf, np.inf
    idx = np.digitize(p, edges[1:-1])
    rows = []
    for b in range(10):
        m = idx == b
        if m.any():
            rows.append({"decile": b + 1, "n": int(m.sum()),
                         "pred": float(p[m].mean()), "actual": float(y[m].mean())})
    return rows


def market_comparison(client, our_pregame: pd.DataFrame) -> dict | None:
    """Join our pregame WP to de-vigged market implied probabilities (stg_partner_odds);
    report both log-losses (blueprint 13.2: internal calibration only)."""
    try:
        mkt = bq.query_df(f"""
            select game_id, home_win_prob_devig as home_implied_prob
            from `{bq.project()}.nhl_staging.stg_partner_odds`
            where home_win_prob_devig is not null
        """, client)
    except Exception:
        return None
    if mkt.empty:
        return None
    merged = our_pregame.merge(mkt, on="game_id", how="inner").dropna(
        subset=["home_implied_prob", "home_won", "home_wp"])
    if len(merged) < 30:
        return None
    return {
        "n": int(len(merged)),
        "ours": float(log_loss(merged["home_won"], merged["home_wp"])),
        "market": float(log_loss(merged["home_won"], merged["home_implied_prob"])),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-frac", type=float, default=1.0,
                    help="fraction of training rows to keep (speed)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        print(build_pull_sql(bq.project(), where="and c.season >= '2012-13'", step=TRAIN_STEP))
        return

    client = bq.client()
    print("Pulling training grid...")
    # Sample 1-in-GAME_SAMPLE games at the SQL layer (the full grid is ~4.5M rows and the
    # download dominates; a quarter of games is ample for a 216-feature logistic model).
    where = (f"and c.season >= '2012-13' "
             f"and mod(abs(farm_fingerprint(cast(c.game_id as string))), {GAME_SAMPLE}) = 0")
    df = bq.query_df(build_pull_sql(bq.project(), where=where, step=TRAIN_STEP), client)
    df = add_state_features(df)
    print(f"rows: {len(df):,}")

    tr = df[df.season <= TRAIN_MAX_SEASON]
    ho = df[df.season == HOLDOUT_SEASON]
    if 0 < args.sample_frac < 1.0:
        tr = tr.sample(frac=args.sample_frac, random_state=0)
    print(f"train={len(tr):,} holdout={len(ho):,} | train home-win rate={tr.home_won.mean():.4f}")

    Xtr, ytr = make_design(tr), tr["home_won"].to_numpy()
    # lbfgs converges far faster than saga on this well-conditioned 216-feature problem.
    model = LogisticRegression(max_iter=1000, C=1.0, solver="lbfgs")
    model.fit(Xtr, ytr)

    metrics = {}
    for name, part in [("train", tr), ("holdout", ho)]:
        if len(part) == 0:
            continue
        p = model.predict_proba(make_design(part))[:, 1]
        metrics[name] = {"n": int(len(part)), "log_loss": float(log_loss(part["home_won"], p)),
                         "calibration": decile_calibration(part["home_won"].to_numpy(), p)}

    # pregame WP per game (elapsed minimum row) for the market comparison
    pregame_idx = df.sort_values("elapsed").groupby("game_id").head(1).index
    pregame = df.loc[pregame_idx].copy()
    pregame["home_wp"] = model.predict_proba(make_design(pregame))[:, 1]
    market = market_comparison(client, pregame[["game_id", "home_won", "home_wp"]])

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, ARTIFACT_DIR / f"{MODEL_VERSION}.joblib")
    manifest = {
        "model_version": MODEL_VERSION,
        "rating_source": config.RATING_SOURCE,
        "train_max_season": TRAIN_MAX_SEASON, "holdout_season": HOLDOUT_SEASON,
        "train_step_seconds": TRAIN_STEP, "n_train": int(len(tr)),
        "metrics": {k: {"n": v["n"], "log_loss": v["log_loss"]} for k, v in metrics.items()},
        "market": market,
    }
    (ARTIFACT_DIR / f"{MODEL_VERSION}_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_methodology(metrics, market)

    for name, m in metrics.items():
        print(f"  {name}: logloss={m['log_loss']:.5f} n={m['n']:,}")
    if market:
        print(f"  market: ours={market['ours']:.5f} vs market={market['market']:.5f} (n={market['n']})")
    else:
        print("  market: no in-season partner-odds snapshot available yet")
    print(f"Saved {MODEL_VERSION}.joblib + manifest; wrote {METHODOLOGY}")


def write_methodology(metrics, market) -> None:
    lines = [
        "# Win-probability model (Phase 2.4)", "",
        "Logistic regression on a (regulation seconds-remaining x score-diff) one-hot",
        "interaction plus strength differential, goalie-pulled flags, OT state, and a",
        "pregame team-strength prior. Target: the home team won (OT/SO wins count as wins).",
        "State backbone is int_segment_context expanded to a time grid.",
        "",
        f"Pregame prior source: `{config.RATING_SOURCE}` (interim season-to-date score-adjusted",
        "xGF% difference; swapped to the Phase 3 power rating via the RATING_SOURCE constant).",
        "",
        "## Metrics", "",
        "| split | n | log-loss |", "|---|---|---|",
    ]
    for name, m in metrics.items():
        lines.append(f"| {name} | {m['n']:,} | {m['log_loss']:.5f} |")
    lines += ["", "## Calibration by decile (holdout 2025-26)", "",
              "| decile | n | predicted | actual |", "|---|---|---|---|"]
    for r in metrics.get("holdout", metrics.get("train"))["calibration"]:
        lines.append(f"| {r['decile']} | {r['n']:,} | {r['pred']:.4f} | {r['actual']:.4f} |")
    lines += ["", "## Pregame vs market (internal calibration only, blueprint 13.2)", ""]
    if market:
        lines.append(f"On {market['n']} games with a market snapshot, our pregame log-loss is "
                     f"**{market['ours']:.5f}** vs the market's **{market['market']:.5f}**.")
    else:
        lines.append("No in-season partner-odds snapshot was available at training time; the "
                     "comparison runs automatically once `stg_partner_odds` has rows.")
    lines += ["", "## Leverage", "",
              "leverage(t) = WP(one more home goal) - WP(one more away goal) at the same state,",
              "stored per game in `nhl_models.win_probability`. It peaks late in one-goal games.", ""]
    METHODOLOGY.parent.mkdir(parents=True, exist_ok=True)
    METHODOLOGY.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
