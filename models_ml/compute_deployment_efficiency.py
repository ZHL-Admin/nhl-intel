"""
Deployment efficiency — the Divergence Board rework (replaces `trust_z − composite_z`).

For each SITUATION lens (all / 5v5 / pp / pk / key_moments) it compares a player's ACTUAL
usage against the usage his situation-appropriate VALUE justifies, within position:

    divergence (gap) = actual_usage_pctile − justified_usage_pctile
    positive = OVER-used (deployed beyond his value), negative = UNDER-used.

The fixes over the old board:
  1. Situation-appropriate value pairing — PK usage is judged against DEFENSIVE impact, PP usage
     against PP impact, etc. (the old board judged everything against composite + a defense-weighted
     trust score, which mechanically dumped every offensive star onto the under-used side).
  2. A realistic USAGE CEILING — justified usage is capped at the observed top-usage level within
     position+situation, so a maxed-out star (whose value would predict impossible minutes) does
     NOT read as under-used. His actual ≈ capped-justified ⇒ gap ≈ 0.

"Key moments" is leverage-defined: the most pivotal `KEY_MOMENT_LEVERAGE_PCTILE` of game time by
the win-probability leverage distribution — principled, not a hand-listed situation set.

RAPM / composite / GAR / win-probability are READ-ONLY here.
Output: nhl_models.deployment_efficiency (one row per player-season_window-situation).

Run:  python -m models_ml.compute_deployment_efficiency [--dry-run]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

WINDOW_SEASONS = ["2023-24", "2024-25", "2025-26"]
WINDOW_LABEL = "2023-24_2025-26"
WINDOW_YEARS = (2023, 2024, 2025)
D = config.DEPLOYMENT


def leverage_threshold() -> float:
    """The leverage value at KEY_MOMENT_LEVERAGE_PCTILE of the window's WP distribution."""
    off = int(round(D["KEY_MOMENT_LEVERAGE_PCTILE"] * 100))
    yrs = ", ".join(str(y) for y in WINDOW_YEARS)
    q = f"""
        SELECT APPROX_QUANTILES(leverage, 100)[OFFSET({off})] AS thr
        FROM `{bq.project()}.nhl_models.win_probability`
        WHERE CAST(SUBSTR(CAST(game_id AS STRING), 1, 4) AS INT64) IN ({yrs})
          AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
    """
    return float(bq.query_df(q)["thr"].iloc[0])


def pull_usage(lev_thr: float) -> pd.DataFrame:
    seasons = ", ".join(f"'{s}'" for s in WINDOW_SEASONS)
    yrs = ", ".join(str(y) for y in WINDOW_YEARS)
    q = f"""
        WITH seg AS (
            SELECT s.player_id, s.position_code, s.game_id, s.segment_index, s.team_id,
                   s.segment_duration, s.segment_start_seconds, s.segment_end_seconds,
                   c.strength_state, c.home_team_id, c.home_skaters, c.away_skaters
            FROM `{bq.project()}.nhl_staging.int_shift_segments` s
            JOIN `{bq.project()}.nhl_staging.int_segment_context` c USING (game_id, segment_index)
            WHERE s.is_goalie = 0 AND s.season IN ({seasons})
              AND SUBSTR(CAST(s.game_id AS STRING), 5, 2) IN ('02', '03')
        ),
        hl_wp AS (
            SELECT game_id, elapsed_seconds
            FROM `{bq.project()}.nhl_models.win_probability`
            WHERE leverage >= {lev_thr}
              AND CAST(SUBSTR(CAST(game_id AS STRING), 1, 4) AS INT64) IN ({yrs})
              AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
        ),
        seg_hl AS (   -- segments overlapping a high-leverage WP sample (counted once)
            SELECT seg.player_id, seg.game_id, seg.segment_index,
                   ANY_VALUE(seg.segment_duration) AS dur
            FROM seg JOIN hl_wp
              ON hl_wp.game_id = seg.game_id
             AND hl_wp.elapsed_seconds >= seg.segment_start_seconds
             AND hl_wp.elapsed_seconds <  seg.segment_end_seconds
            GROUP BY 1, 2, 3
        ),
        hilev AS (SELECT player_id, SUM(dur) / 60.0 AS hilev_min FROM seg_hl GROUP BY 1),
        usage AS (
            SELECT seg.player_id,
                   ANY_VALUE(seg.position_code) AS position_code,
                   COUNT(DISTINCT seg.game_id) AS games,
                   SUM(seg.segment_duration) / 60.0 AS total_min,
                   SUM(IF(seg.strength_state = '5v5', seg.segment_duration, 0)) / 60.0 AS ev_min,
                   SUM(IF((seg.team_id = seg.home_team_id AND seg.home_skaters > seg.away_skaters)
                       OR (seg.team_id <> seg.home_team_id AND seg.away_skaters > seg.home_skaters),
                       seg.segment_duration, 0)) / 60.0 AS pp_min,
                   SUM(IF((seg.team_id = seg.home_team_id AND seg.home_skaters < seg.away_skaters)
                       OR (seg.team_id <> seg.home_team_id AND seg.away_skaters < seg.home_skaters),
                       seg.segment_duration, 0)) / 60.0 AS pk_min
            FROM seg GROUP BY 1
        )
        SELECT u.*, COALESCE(h.hilev_min, 0.0) AS hilev_min
        FROM usage u LEFT JOIN hilev h USING (player_id)
    """
    df = bq.query_df(q)
    for c in ["games", "total_min", "ev_min", "pp_min", "pk_min", "hilev_min"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    return df


def pull_value() -> pd.DataFrame:
    q = f"""
        SELECT i.player_id, i.off_impact, i.off_sd, i.def_impact, i.def_sd,
               i.pp_impact, i.pp_sd, i.pk_impact, i.pk_sd,
               co.total AS composite, co.total_sd AS composite_sd, co.position
        FROM `{bq.project()}.nhl_models.player_impact` i
        JOIN `{bq.project()}.nhl_models.player_composite` co
          USING (player_id, season_window)
        WHERE i.season_window = '{WINDOW_LABEL}'
    """
    df = bq.query_df(q)
    for c in ["off_impact", "off_sd", "def_impact", "def_sd", "pp_impact", "pp_sd",
              "pk_impact", "pk_sd", "composite", "composite_sd"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    return df


# usage column + (value, value_sd) per situation, resolved from the merged frame
USAGE_COL = {"total": "total_min", "ev": "ev_min", "pp": "pp_min", "pk": "pk_min", "hilev": "hilev_min"}


def _value_cols(df: pd.DataFrame, key: str):
    if key == "composite":
        return df["composite"], df["composite_sd"]
    if key == "ev_impact":
        return df["off_impact"] + df["def_impact"], np.sqrt(df["off_sd"] ** 2 + df["def_sd"] ** 2)
    if key == "pp_impact":
        return df["pp_impact"], df["pp_sd"]
    if key == "def_impact":
        return df["def_impact"], df["def_sd"]
    if key == "pk_blend":
        w = D["PK_BLEND_W"]
        sd_pk = df["pk_impact"].std() or 1.0
        sd_def = df["def_impact"].std() or 1.0
        val = w * (df["pk_impact"] / sd_pk) + (1 - w) * (df["def_impact"] / sd_def)
        val_sd = np.sqrt((w * df["pk_sd"] / sd_pk) ** 2 + ((1 - w) * df["def_sd"] / sd_def) ** 2)
        return val, val_sd
    raise ValueError(key)


def compute(usage: pd.DataFrame, value: pd.DataFrame):
    df = usage.merge(value, on="player_id", how="inner")
    df["pos_group"] = np.where(df["position"].fillna(df["position_code"]) == "D", "D", "F")
    df = df[(df["total_min"] >= D["MIN_TOTAL_TOI"]) & (df["games"] >= D["MIN_GAMES"])
            & (df["ev_min"] >= D["MIN_EV_TOI"])].copy()

    ceil_p = D["USAGE_CEILING_PCTILE"]
    rows, diagnostics = [], []
    for sit, cfg in D["SITUATIONS"].items():
        umin = USAGE_COL[cfg["usage"]]
        val, val_sd = _value_cols(df, cfg["value"])
        d = df.copy()
        d["actual"] = d[umin] / d["games"]          # minutes per game played
        d["value"] = val.values
        d["value_sd"] = val_sd.values
        d = d[d["value"].notna() & d["actual"].notna()]

        for pos in ["F", "D"]:
            g = d[d["pos_group"] == pos].copy()
            if len(g) < 20:
                continue
            a = g["actual"].to_numpy(float)
            v = g["value"].to_numpy(float)
            vsd = g["value_sd"].fillna(0).to_numpy(float)
            n = len(a)
            value_sd_pctile = pd.Series(vsd).rank(pct=True).to_numpy()   # reliability (lower = better)

            # Justified usage = the usage a player of this VALUE rank should get, i.e. his value
            # percentile mapped onto the usage distribution — CAPPED at the realistic ceiling so a
            # maxed-out star (value 99th) isn't "owed" impossible minutes and so reads as ~fairly
            # used rather than under-used. (A weak value->usage regression collapses to the mean and
            # turns the board into a usage ranking; the direct percentile mapping does not.)
            actual_pctile = pd.Series(a).rank(pct=True).to_numpy()
            value_pctile = pd.Series(v).rank(pct=True).to_numpy()
            justified_pctile = np.minimum(value_pctile, ceil_p)
            gap = actual_pctile - justified_pctile
            justified = np.quantile(a, justified_pctile)   # minutes, for display
            ceiling = float(np.quantile(a, ceil_p))

            # uncertainty: value ± sd -> a value-percentile band -> a gap band
            sorted_v = np.sort(v)
            def vcdf(x):
                return np.searchsorted(sorted_v, x, side="right") / n
            gap_sd = np.abs(np.minimum(vcdf(v + vsd), ceil_p) - np.minimum(vcdf(v - vsd), ceil_p)) / 2.0

            # confidence-adjusted gap: shrink the point estimate toward 0 by K·sd (the SORT key)
            conf_gap = np.sign(gap) * np.maximum(0.0, np.abs(gap) - D["CONFIDENCE_K"] * gap_sd)
            actual_rank = (pd.Series(-a).rank(method="min")).to_numpy(int)
            value_rank = (pd.Series(-v).rank(method="min")).to_numpy(int)
            slope, _ = np.polyfit(v, a, 1)
            r = np.corrcoef(v, a)[0, 1]
            diagnostics.append((sit, pos, n, slope, r, ceiling))

            for i, (_, row) in enumerate(g.reset_index(drop=True).iterrows()):
                rows.append({
                    "player_id": int(row["player_id"]), "season_window": WINDOW_LABEL,
                    "situation": sit, "pos_group": pos, "position": row["position"],
                    "games": int(row["games"]), "value_label": cfg["label"],
                    "actual_usage": float(a[i]), "actual_pctile": float(actual_pctile[i]),
                    "justified_usage": float(justified[i]), "justified_pctile": float(justified_pctile[i]),
                    "value_used": float(v[i]), "value_pctile": float(value_pctile[i]),
                    "gap": float(gap[i]), "gap_sd": float(gap_sd[i]), "conf_gap": float(conf_gap[i]),
                    "actual_rank": int(actual_rank[i]), "value_rank": int(value_rank[i]),
                    "value_sd_pctile": float(value_sd_pctile[i]),
                    "n_pool": int(n), "ceiling": ceiling,
                })
    return pd.DataFrame(rows), diagnostics


def _names(ids):
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    df = bq.query_df(f"""SELECT player_id, ANY_VALUE(first_name||' '||last_name) AS name
                         FROM `{bq.project()}.nhl_staging.stg_rosters`
                         WHERE player_id IN ({", ".join(str(i) for i in ids)}) GROUP BY 1""")
    return dict(zip(df["player_id"], df["name"]))


def _print_board(out: pd.DataFrame, sit: str, names: dict, pos: str | None = None):
    b = out[out["situation"] == sit]
    if pos:
        b = b[b["pos_group"] == pos]
    print(f"\n===== {sit.upper()}{' · ' + pos if pos else ''} "
          f"({b['value_label'].iloc[0] if len(b) else '—'}) =====")
    usage_type = D["SITUATIONS"][sit]["usage"]
    floor = D["MIN_UNDERUSED_ACTUAL_PCTILE"] if usage_type in D["FLOORED_USAGE_TYPES"] else 0.0
    for side, asc in [("OVER-USED", False), ("UNDER-USED", True)]:
        print(f"  --- {side} (by confidence-adjusted gap) ---")
        if side == "OVER-USED":
            sub = b[b["conf_gap"] > 0]
        else:
            sub = b[(b["conf_gap"] < 0) & (b["actual_pctile"] >= floor)]
            if sit == "pk":   # reliability gate: only trust under-used PK where value is well-estimated
                sub = sub[sub["value_sd_pctile"] <= D["DEF_SD_GATE_PCTILE"]]
        for _, r in sub.sort_values("conf_gap", ascending=asc).head(8).iterrows():
            nm = names.get(r["player_id"], r["player_id"])
            print(f"    {str(nm):22s} {r['pos_group']}  usage {r['actual_pctile']*100:3.0f}p "
                  f"vs justified {r['justified_pctile']*100:3.0f}p  gap {r['gap']*100:+4.0f} "
                  f"(±{r['gap_sd']*100:.0f}) · {r['value_label']} rank {r['value_rank']}/{r['n_pool']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    thr = leverage_threshold()
    print(f"Leverage threshold (key moments = top {(1-D['KEY_MOMENT_LEVERAGE_PCTILE'])*100:.0f}% "
          f"of game time): leverage >= {thr:.4f}")
    usage = pull_usage(thr)
    value = pull_value()
    out, diag = compute(usage, value)

    print("\nPer-situation fit (value -> usage), within position:")
    for sit, pos, n, slope, r, ceiling in diag:
        print(f"  {sit:11s} {pos}  n={n:4d}  slope={slope:+.3f}  r={r:+.2f}  "
              f"ceiling={ceiling:.1f} min/gm")

    names = _names(out["player_id"].unique().tolist())
    # the prompt asks to print ALL and KEY MOMENTS (both sides) + PK before any UI
    _print_board(out, "all", names)
    _print_board(out, "key_moments", names)
    _print_board(out, "pk", names)

    if args.dry_run:
        print(f"\n[dry-run] {len(out):,} rows not written")
        return
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = D["MODEL_VERSION"]
    bq.write_df(out, "deployment_efficiency", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "situation", "player_id"])
    print(f"\nWrote {len(out):,} rows to nhl_models.deployment_efficiency.")


if __name__ == "__main__":
    main()
