"""Marcel baselines for player WAR (Workstream 0, spec 5.1).

Marcel is the dumb-but-honest baseline the assessment must beat (ship gate G1). It estimates
TRUE TALENT AS OF a season (no aging) from up to three prior single seasons, regressed toward
the position-group mean rate by sample size. Skaters and goalies are handled separately.

Expressed as a WAR **rate** so the validation harness can multiply by realized next-season TOI
and de-confound TOI forecasting (spec 5.2 T1):
  * skater rate = WAR per 5v5 hour   (war / (toi_5v5 / 60))
  * goalie rate = WAR per shot faced (war / shots_total)

Reads only single-season rows of nhl_models.player_gar / goalie_gar. Pure pandas given the
panels, so it is unit-testable without BigQuery.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from models_ml import config

# Newest -> oldest season weights (spec D6). Regression constants K in DENOMINATOR units.
SEASON_WEIGHTS = [5.0, 4.0, 3.0]
K_SKATER_MIN = 1800.0      # 5v5 minutes
K_GOALIE_SHOTS = 1500.0    # shots faced
GPW = config.GAR_CONFIG["GOALS_PER_WIN"]

_SINGLE = re.compile(r"^\d{4}-\d{2}$")


def season_year(s: str) -> int:
    """'2024-25' -> 2024."""
    return int(str(s)[:4])


def season_label(year: int) -> str:
    """2024 -> '2024-25'."""
    return f"{year}-{str(year + 1)[-2:]}"


def _pos_group(pos: str) -> str:
    return "D" if pos == "D" else "F"


def skater_panel(gar: pd.DataFrame) -> pd.DataFrame:
    """Single-season player_gar rows + yr / pos_group / war_rate (WAR per 5v5 hour)."""
    df = gar[gar["season_window"].map(lambda s: bool(_SINGLE.match(str(s))))].copy()
    df["yr"] = df["season_window"].map(season_year)
    df["pos_group"] = df["position"].map(_pos_group)
    df["toi_h"] = df["toi_5v5"] / 60.0
    df["war_rate"] = np.where(df["toi_h"] > 0, df["war"] / df["toi_h"], np.nan)
    return df


def goalie_panel(ggar: pd.DataFrame) -> pd.DataFrame:
    """Single-season goalie_gar rows + yr / war_rate (WAR per shot faced)."""
    df = ggar[ggar["season_window"].map(lambda s: bool(_SINGLE.match(str(s))))].copy()
    df["player_id"] = df["goalie_id"]           # so the shared _marcel keys uniformly
    df["yr"] = df["season_window"].map(season_year)
    df["pos_group"] = "G"
    df["war_rate"] = np.where(df["shots_total"] > 0, df["war"] / df["shots_total"], np.nan)
    return df


def _pos_mean_rate(train: pd.DataFrame, weight_col: str) -> dict:
    """Denominator-weighted mean war_rate per position group over the training rows."""
    out = {}
    for pg, sub in train.groupby("pos_group"):
        w = sub[weight_col].clip(lower=0.0)
        r = sub["war_rate"]
        ok = np.isfinite(r) & (w > 0)
        out[pg] = float(np.average(r[ok], weights=w[ok])) if ok.any() else 0.0
    return out


def _marcel(panel: pd.DataFrame, target_season: str, weight_col: str, k: float) -> pd.DataFrame:
    """Generic Marcel: {player_id -> marcel_rate} as of the season BEFORE target_season.

    Uses up to 3 seasons in [ty-3, ty-1] with weights [5,4,3]*denom; regresses the blend toward
    the position-group mean rate with shrink = k / (k + Σ wᵢ·denomᵢ)  (spec 5.1)."""
    ty = season_year(target_season)
    train = panel[(panel["yr"] < ty) & (panel["yr"] >= ty - 3)].copy()
    means = _pos_mean_rate(train, weight_col)
    rows = []
    for pid, g in train.groupby("player_id"):
        g = g.sort_values("yr", ascending=False).head(3).reset_index(drop=True)
        pg = g.iloc[0]["pos_group"]
        num = den = 0.0
        for i, r in g.iterrows():
            denom = float(r[weight_col])
            if not np.isfinite(r["war_rate"]) or denom <= 0:
                continue
            w = SEASON_WEIGHTS[i] * denom
            num += w * float(r["war_rate"])
            den += w
        if den <= 0:
            continue
        obs = num / den
        shrink = k / (k + den)                       # weight on the position-mean prior
        rate = shrink * means.get(pg, 0.0) + (1.0 - shrink) * obs
        rows.append({"player_id": int(pid), "pos_group": pg, "marcel_rate": rate, "w": den})
    return pd.DataFrame(rows).set_index("player_id") if rows else pd.DataFrame(
        columns=["pos_group", "marcel_rate", "w"]).rename_axis("player_id")


def marcel_skaters(panel: pd.DataFrame, target_season: str) -> pd.DataFrame:
    return _marcel(panel, target_season, "toi_5v5", K_SKATER_MIN)


def marcel_goalies(panel: pd.DataFrame, target_season: str) -> pd.DataFrame:
    return _marcel(panel, target_season, "shots_total", K_GOALIE_SHOTS)
