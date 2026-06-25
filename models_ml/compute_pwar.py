"""Apply the pWAR anchor to every player-season 2010-11..2025-26 (Handoff 5, Phase B).

Produces nhl_models.player_pwar — realized production value in the SAME WAR units as player_gar,
available across the whole 2010+ window even though real WAR only exists 2021-22..2025-26. Pre-overlap
seasons are BACK-CAST (estimated from box production via fit_pwar_anchor) and carry a wider band and
an is_backcast flag. This is the realized-value currency the draft-value curve and theory test sum
over each drafted player's 7-year window.

Per player-season: pwar_hat (anchor estimate), war_real (where the GAR overlap exists), is_backcast,
pwar_sd (anchor residual sd, inflated for back-cast seasons), games_played, pos_group, is_goalie.

NHL game-type filter (regular 02 + playoff 03) applied to skater aggregation — the player mart
includes preseason/international games that the WAR target excludes.

Run:
    python -m models_ml.compute_pwar --dry-run
    python -m models_ml.compute_pwar                  # writes nhl_models.player_pwar
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config
from models_ml import fit_pwar_anchor as A

D = config.DRAFT_VALUE
FIRST_OVERLAP = min(D["ANCHOR_SEASONS"])   # seasons before this are back-cast


def skater_sql() -> str:
    P = bq.project()
    return f"""
    with prod as (
        select player_id, season,
               count(distinct game_id) as games_played,
               sum(individual_goals + first_assists + second_assists) as points,
               sum(ixg) as ixg,
               sum(toi_5v5) as toi_5v5_total,
               safe_divide(sum(on_ice_xgf_pct * toi_5v5), nullif(sum(toi_5v5), 0)) as on_ice_xgf_pct,
               -- modal position over the season (for F/D)
               approx_top_count(position_code, 1)[offset(0)].value as position
        from `{P}.nhl_mart.mart_player_game_stats`
        where {A._nhl_game_filter()}
        group by 1, 2
    )
    select p.player_id, p.season, p.position, p.games_played, p.points, p.ixg,
           p.toi_5v5_total, p.on_ice_xgf_pct, b.birth_date,
           g.war as war_real
    from prod p
    left join `{P}.nhl_staging.stg_player_bio` b on b.player_id = p.player_id
    left join `{P}.nhl_models.player_gar` g
           on g.player_id = p.player_id and g.season_window = p.season
    """


def goalie_sql() -> str:
    P = bq.project()
    return f"""
    select s.goalie_id as player_id, s.season, s.games_played, s.shots_faced, s.save_pct,
           g.war as war_real
    from `{P}.nhl_mart.mart_goalie_season` s
    left join `{P}.nhl_models.goalie_gar` g
           on g.goalie_id = s.goalie_id and g.season_window = s.season
    where s.shots_faced > 0
    """


def _build_skaters(art: dict) -> pd.DataFrame:
    raw = bq.query_df(skater_sql())
    df = A._prep_skaters(raw)                       # reuse the exact feature construction
    df["pwar_hat"] = A.predict_skater(art, df)
    df["pos_group"] = np.where(df["is_forward"] == 1, "F", "D")
    df["is_goalie"] = False
    df["war_real"] = pd.to_numeric(df["war_real"], errors="coerce")
    return df[["player_id", "season", "pos_group", "is_goalie", "pwar_hat",
               "war_real", "games_played"]]


def _build_goalies(art: dict) -> pd.DataFrame:
    raw = bq.query_df(goalie_sql())
    df = A._prep_goalies(raw)                       # builds save_pct_vs_league
    df["pwar_hat"] = A.predict_goalie(art, df)
    df["pos_group"] = "G"
    df["is_goalie"] = True
    df["war_real"] = pd.to_numeric(df["war_real"], errors="coerce")
    return df[["player_id", "season", "pos_group", "is_goalie", "pwar_hat",
               "war_real", "games_played"]]


def _finalize(df: pd.DataFrame, art: dict) -> pd.DataFrame:
    df = df.copy()
    df["is_backcast"] = df["season"] < FIRST_OVERLAP
    # band: anchor residual sd by group, inflated for back-cast seasons (estimated, not measured)
    sd_sk = art["skater"]["resid_sd"]
    sd_go = art["goalie"]["resid_sd"]
    base_sd = np.where(df["is_goalie"], sd_go, sd_sk)
    df["pwar_sd"] = base_sd * np.where(df["is_backcast"], D["BACKCAST_SD_MULT"], 1.0)
    # clamp tiny negatives from the monotone model at the replacement floor (WAR can be slightly <0)
    df["pwar_hat"] = df["pwar_hat"].astype(float).round(3)
    df["pwar_sd"] = df["pwar_sd"].astype(float).round(3)
    df["games_played"] = pd.to_numeric(df["games_played"], errors="coerce").astype(int)
    df["model_version"] = D["PWAR_VERSION"]
    return df


def _report(df: pd.DataFrame) -> None:
    print(f"\nplayer_pwar: {len(df)} player-seasons "
          f"({df.is_backcast.sum()} back-cast, {(~df.is_backcast).sum()} overlap; "
          f"{df.is_goalie.sum()} goalie)")
    print(f"  null pwar_hat: {df.pwar_hat.isna().sum()} (must be 0)")
    print(f"  back-cast pwar_sd / overlap pwar_sd (skater): "
          f"{df[df.is_backcast & ~df.is_goalie].pwar_sd.mean():.2f} / "
          f"{df[~df.is_backcast & ~df.is_goalie].pwar_sd.mean():.2f} (back-cast must be wider)")
    ov = df[~df.is_backcast & df.war_real.notna()]
    if len(ov):
        from scipy.stats import spearmanr
        print(f"  overlap pwar_hat vs war_real Spearman: "
              f"{spearmanr(ov.pwar_hat, ov.war_real).statistic:.3f} (n={len(ov)})")
    print("\n  Top back-cast (pre-2021) skater-seasons by pwar_hat (smell test):")
    bc = df[df.is_backcast & ~df.is_goalie].sort_values("pwar_hat", ascending=False).head(6)
    for _, r in bc.iterrows():
        print(f"    {int(r.player_id)} {r.season} {r.pos_group}: pwar_hat={r.pwar_hat:.1f} gp={r.games_played}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    art = A.load_artifact()
    df = _finalize(pd.concat([_build_skaters(art), _build_goalies(art)], ignore_index=True), art)
    _report(df)

    if args.dry_run:
        print("\n[dry-run] not written")
        return
    bq.write_df(df, "player_pwar", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season", "pos_group"])
    print(f"\nWrote {len(df)} rows to nhl_models.player_pwar.")


if __name__ == "__main__":
    main()
