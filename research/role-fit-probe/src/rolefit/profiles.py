"""Role/action profile per player-season (Link 1.1), 5v5, from the Step-0 usable primitives.

USABLE PRIMITIVES (Step 0): only shot-family events carry an individual player (shooter/scorer/assist).
Hits, takeaways, giveaways, faceoffs, and blocks-as-blocker have NO player attribution in the frozen
events table. The role proxy is therefore SHOT/OFFENSE-BASED — a documented ceiling (see probe.md §0).
Standing caveat: this is an on-puck proxy; it cannot see off-puck movement or defense.

Axes (all as 5v5 rates or shares; unblocked = Fenwick used for location/danger, all attempts = Corsi
for volume; distance folds to one end via |x|):
  cf60          shot attempts / 60   (volume)
  xg60          xG / 60              (shot-generation value)
  xg_per_shot   mean xG per unblocked shot (danger/selection)
  mean_dist     mean shot distance from net, ft (unblocked)
  slot_share    share of unblocked shots <= 25 ft (net-front)
  point_share   share of unblocked shots >= 55 ft (point)
  tip_share     tip-in/deflected share of unblocked shots (net-front finishing)
  slap_share    slap-shot share of unblocked shots (point one-timer)
  goals60       goals / 60           (finishing)
  assists60     (assist1+assist2 on goals) / 60  (on-goal playmaking; sparse)

Rates are z-scored WITHIN (position, season) so a D and an F are on their own scales (Link 1.1).
Profiles are built at (player, game) grain so odd/even split-halves reuse the same code.
"""
from __future__ import annotations

import polars as pl

from . import config              # importing config first puts CHEM_SRC/ATLAS_SRC on sys.path
import chem.corpus as cc          # reuse the validated stint-expansion machinery (1497=1497)

PROFILE_DIR = config.PARQUET / "profiles"
RICH_DIR = config.PARQUET / "profiles_rich"
ENRICH_DIR = config.PARQUET / "enriched"          # UL-P1 re-projection output (enrich.py)
SHOTS = ["shot-on-goal", "missed-shot", "blocked-shot", "goal"]
UNBLOCKED = ["shot-on-goal", "missed-shot", "goal"]
# shot-only role axes (Link 1 §1)
AXES = ["cf60", "xg60", "xg_per_shot", "mean_dist", "slot_share", "point_share",
        "tip_share", "slap_share", "goals60", "assists60"]
# recovered INDIVIDUAL two-way axes (UL-P1 enrichment): possession / defense / discipline
INDIV_NEW = ["tk60", "gv60", "block60", "hit60", "hittaken60", "pentake60", "pendrawn60"]
# UNIT-LEVEL opponent-mirror suppression (on-ice against; entangled at the individual level)
UNIT_AXES = ["ca60", "xga60"]
# the full rich role-space axes fed to PCA are INDIVIDUAL only (shot + two-way); unit axes are
# reported separately (their player-vs-team split is the point). Faceoffs are season-grain (below).
RICH_INDIV_AXES = AXES + INDIV_NEW


# ---------------------------------------------------------------- per (player, game) 5v5 TOI
def player_game_toi(season: str, st: pl.DataFrame | None = None) -> pl.DataFrame:
    if st is None:
        st = cc._stints(season)     # 5v5, RS, exactly-5, quarantine-excluded, rid present

    def side(ids, team):
        return st.select(game_id="game_id", pid=pl.col(ids), team_id=pl.col(team),
                         dur="duration_seconds").explode("pid")
    tg = pl.concat([side("home_skater_ids", "home_team_id"), side("away_skater_ids", "away_team_id")])
    return tg.group_by("pid", "game_id").agg(toi=pl.col("dur").sum(),
                                             team_id=pl.col("team_id").first())


# ---------------------------------------------------------------- per (player, game) shot features
def _shot_events(season: str) -> pl.DataFrame:
    ev = (pl.scan_parquet(config.ATLAS_PARQUET / "events.parquet")
          .filter((pl.col("season_label") == season) & pl.col("is_primary_scope")
                  & (pl.col("situation_code") == "1551")
                  & pl.col("type_desc_key").is_in(SHOTS))
          .select("game_id", "event_id", "type_desc_key", "x_coord", "y_coord", "shot_type",
                  "shooting_player_id", "scoring_player_id", "assist1_player_id", "assist2_player_id")
          .collect())
    xg = pl.read_parquet(config.ATLAS_PARQUET / "shot_xg.parquet", columns=["game_id", "event_id", "xg"])
    ev = ev.join(xg, on=["game_id", "event_id"], how="left").with_columns(
        pid=pl.when(pl.col("type_desc_key") == "goal").then(pl.col("scoring_player_id"))
        .otherwise(pl.col("shooting_player_id")),
        is_goal=(pl.col("type_desc_key") == "goal").cast(pl.Int32),
        unblocked=(pl.col("type_desc_key") != "blocked-shot"),
        dist=((89 - pl.col("x_coord").abs()) ** 2 + pl.col("y_coord") ** 2).sqrt(),
        is_tip=pl.col("shot_type").is_in(["tip-in", "deflected"]).cast(pl.Int32),
        is_slap=(pl.col("shot_type") == "slap").cast(pl.Int32),
        xg=pl.col("xg").fill_null(0.0))
    return ev


def shot_features_by_game(season: str) -> pl.DataFrame:
    ev = _shot_events(season)
    # shooter-attributed shot aggregates per (pid, game)
    shooter = ev.group_by("pid", "game_id").agg(
        cf=pl.len(),
        goals=pl.col("is_goal").sum(),
        xg=pl.col("xg").filter(pl.col("unblocked")).sum(),
        n_unb=pl.col("unblocked").sum(),
        sum_dist=pl.col("dist").filter(pl.col("unblocked")).sum(),
        n_slot=(pl.col("unblocked") & (pl.col("dist") <= 25)).sum(),
        n_point=(pl.col("unblocked") & (pl.col("dist") >= 55)).sum(),
        n_tip=pl.col("is_tip").filter(pl.col("unblocked")).sum(),
        n_slap=pl.col("is_slap").filter(pl.col("unblocked")).sum(),
        sum_xg_unb=pl.col("xg").filter(pl.col("unblocked")).sum())
    # assists (playmaking): assist1 + assist2 on goals -> credit each assister per game
    a1 = ev.filter(pl.col("assist1_player_id").is_not_null()).select(
        pid="assist1_player_id", game_id="game_id")
    a2 = ev.filter(pl.col("assist2_player_id").is_not_null()).select(
        pid="assist2_player_id", game_id="game_id")
    assists = pl.concat([a1, a2]).group_by("pid", "game_id").agg(assists=pl.len())
    return shooter.join(assists, on=["pid", "game_id"], how="left").with_columns(
        assists=pl.col("assists").fill_null(0))


# ---------------------------------------------------------------- assemble player-(season|half) profiles
def _rates_from_counts(df: pl.DataFrame) -> pl.DataFrame:
    """Given per-player summed counts + toi, produce the AXES as rates/shares."""
    per60 = 3600.0
    return df.with_columns(
        cf60=pl.col("cf") / pl.col("toi") * per60,
        xg60=pl.col("xg") / pl.col("toi") * per60,
        goals60=pl.col("goals") / pl.col("toi") * per60,
        assists60=pl.col("assists") / pl.col("toi") * per60,
        xg_per_shot=pl.when(pl.col("n_unb") > 0).then(pl.col("sum_xg_unb") / pl.col("n_unb")).otherwise(None),
        mean_dist=pl.when(pl.col("n_unb") > 0).then(pl.col("sum_dist") / pl.col("n_unb")).otherwise(None),
        slot_share=pl.when(pl.col("n_unb") > 0).then(pl.col("n_slot") / pl.col("n_unb")).otherwise(None),
        point_share=pl.when(pl.col("n_unb") > 0).then(pl.col("n_point") / pl.col("n_unb")).otherwise(None),
        tip_share=pl.when(pl.col("n_unb") > 0).then(pl.col("n_tip") / pl.col("n_unb")).otherwise(None),
        slap_share=pl.when(pl.col("n_unb") > 0).then(pl.col("n_slap") / pl.col("n_unb")).otherwise(None))


def build_profiles(season: str, write: bool = True) -> pl.DataFrame:
    """Per (player, season): full-season + odd/even-half role axes (rates), position, games, toi.
    Half = game rank parity within the player-season (matches the Chemistry split-half convention)."""
    st = cc._stints(season)
    toi = player_game_toi(season, st)
    feats = shot_features_by_game(season)
    pg = toi.join(feats, on=["pid", "game_id"], how="left").with_columns(
        [pl.col(c).fill_null(0) for c in ("cf", "goals", "xg", "n_unb", "sum_dist", "n_slot",
                                          "n_point", "n_tip", "n_slap", "sum_xg_unb", "assists")])
    # half assignment: dense game rank within player, parity
    pg = pg.with_columns(rank=pl.col("game_id").rank("dense").over("pid")).with_columns(
        half=(pl.col("rank") % 2))

    cnt_cols = ["toi", "cf", "goals", "xg", "n_unb", "sum_dist", "n_slot", "n_point", "n_tip",
                "n_slap", "sum_xg_unb", "assists"]

    def agg(df, suffix):
        a = df.group_by("pid").agg([pl.col(c).sum() for c in cnt_cols]
                                   + [pl.col("game_id").n_unique().alias("games")])
        a = _rates_from_counts(a)
        keep = ["pid", "games", "toi"] + AXES
        return a.select(keep).rename({c: f"{c}{suffix}" for c in ["games", "toi"] + AXES})

    full = agg(pg, "")
    odd = agg(pg.filter(pl.col("half") == 1), "_odd")
    even = agg(pg.filter(pl.col("half") == 0), "_even")
    prof = full.join(odd, on="pid", how="left").join(even, on="pid", how="left")

    # position (modal F/D) + primary team (most 5v5 TOI) this season
    pf = cc._pos_frame().rename({"player_id": "pid"})
    team = (pg.group_by("pid", "team_id").agg(t=pl.col("toi").sum())
            .sort("t", descending=True).unique("pid", keep="first").select("pid", "team_id"))
    prof = (prof.join(pf, on="pid", how="left").with_columns(pg=pl.col("pg").fill_null("F"))
            .join(team, on="pid", how="left").with_columns(season_label=pl.lit(season)))
    if write:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        prof.write_parquet(PROFILE_DIR / f"{season.replace('-', '_')}.parquet")
    return prof


# ---------------------------------------------------------------- RICH (UL-P1 enrichment) builders
_ACTIONS = ["hit", "blocked-shot", "takeaway", "giveaway", "penalty"]


def enriched_actions_by_game(season: str) -> pl.DataFrame:
    """Per (player, game): counts of the recovered INDIVIDUAL two-way actions, 5v5. Routes the
    enriched event-player columns by event type (UL-P1)."""
    ev = (pl.scan_parquet(config.ATLAS_PARQUET / "events.parquet")
          .filter((pl.col("season_label") == season) & pl.col("is_primary_scope")
                  & (pl.col("situation_code") == "1551") & pl.col("type_desc_key").is_in(_ACTIONS))
          .select("game_id", "event_id", "type_desc_key").collect())
    epl = pl.read_parquet(ENRICH_DIR / "event_players.parquet")
    ev = ev.join(epl, on=["game_id", "event_id"], how="left")

    def cnt(mask, pid_col, name):
        return (ev.filter(mask & pl.col(pid_col).is_not_null())
                .group_by(pl.col(pid_col).alias("pid"), "game_id").agg(pl.len().alias(name)))
    tk = cnt(pl.col("type_desc_key") == "takeaway", "generic_player_id", "tk")
    gv = cnt(pl.col("type_desc_key") == "giveaway", "generic_player_id", "gv")
    bl = cnt(pl.col("type_desc_key") == "blocked-shot", "blocking_player_id", "block")
    hi = cnt(pl.col("type_desc_key") == "hit", "hitting_player_id", "hit")
    ht = cnt(pl.col("type_desc_key") == "hit", "hittee_player_id", "hittaken")
    pt = cnt(pl.col("type_desc_key") == "penalty", "committed_by_player_id", "pentake")
    pd = cnt(pl.col("type_desc_key") == "penalty", "drawn_by_player_id", "pendrawn")
    out = tk
    for d in (gv, bl, hi, ht, pt, pd):
        out = out.join(d, on=["pid", "game_id"], how="full", coalesce=True)
    return out.with_columns([pl.col(c).fill_null(0) for c in
                             ("tk", "gv", "block", "hit", "hittaken", "pentake", "pendrawn")])


def player_game_onice(season: str, st: pl.DataFrame | None = None) -> pl.DataFrame:
    """Per (player, game) 5v5 on-ice for/against (toi, cf, ca, xgf, xga) — the unit-suppression base."""
    if st is None:
        st = cc._stints(season)

    def side(ids, team, cf, ca, xgf, xga):
        return st.select(game_id="game_id", pid=pl.col(ids), team_id=pl.col(team),
                         dur="duration_seconds", cf=pl.col(cf), ca=pl.col(ca),
                         xgf=pl.col(xgf), xga=pl.col(xga)).explode("pid")
    home = side("home_skater_ids", "home_team_id", "home_corsi", "away_corsi", "home_xg", "away_xg")
    away = side("away_skater_ids", "away_team_id", "away_corsi", "home_corsi", "away_xg", "home_xg")
    return pl.concat([home, away]).group_by("pid", "game_id").agg(
        toi=pl.col("dur").sum(), cf=pl.col("cf").sum(), ca=pl.col("ca").sum(),
        xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(), team_id=pl.col("team_id").first())


def _rich_rates(df: pl.DataFrame) -> pl.DataFrame:
    per60 = 3600.0
    return df.with_columns(
        tk60=pl.col("tk") / pl.col("toi") * per60, gv60=pl.col("gv") / pl.col("toi") * per60,
        block60=pl.col("block") / pl.col("toi") * per60, hit60=pl.col("hit") / pl.col("toi") * per60,
        hittaken60=pl.col("hittaken") / pl.col("toi") * per60,
        pentake60=pl.col("pentake") / pl.col("toi") * per60,
        pendrawn60=pl.col("pendrawn") / pl.col("toi") * per60,
        ca60=pl.col("ca") / pl.col("toi") * per60, xga60=pl.col("xga") / pl.col("toi") * per60)


def build_profiles_rich(season: str, write: bool = True) -> pl.DataFrame:
    """Shot axes + recovered two-way individual axes + unit-level suppression, full + odd/even halves.
    Faceoff win% (season grain, all-strength) joined as a season-only axis (excluded from split-half)."""
    st = cc._stints(season)
    onice = player_game_onice(season, st)                        # toi, cf, ca, xgf, xga, team
    shots = shot_features_by_game(season)
    acts = enriched_actions_by_game(season)
    pg = (onice.join(shots, on=["pid", "game_id"], how="left")
          .join(acts, on=["pid", "game_id"], how="left"))
    fill0 = ["cf_right", "goals", "xg", "n_unb", "sum_dist", "n_slot", "n_point", "n_tip", "n_slap",
             "sum_xg_unb", "assists", "tk", "gv", "block", "hit", "hittaken", "pentake", "pendrawn"]
    pg = pg.rename({"cf": "cf_onice"}).rename({"cf_right": "cf"}) if "cf_right" in pg.columns else pg
    pg = pg.with_columns([pl.col(c).fill_null(0) for c in pg.columns if c in
                          {"goals", "xg", "n_unb", "sum_dist", "n_slot", "n_point", "n_tip", "n_slap",
                           "sum_xg_unb", "assists", "tk", "gv", "block", "hit", "hittaken",
                           "pentake", "pendrawn", "cf"}])
    pg = pg.with_columns(rank=pl.col("game_id").rank("dense").over("pid")).with_columns(
        half=(pl.col("rank") % 2))

    sum_cols = ["toi", "cf", "ca", "xgf", "xga", "goals", "xg", "n_unb", "sum_dist", "n_slot",
                "n_point", "n_tip", "n_slap", "sum_xg_unb", "assists", "tk", "gv", "block", "hit",
                "hittaken", "pentake", "pendrawn"]

    def agg(df, suffix):
        a = df.group_by("pid").agg([pl.col(c).sum() for c in sum_cols]
                                   + [pl.col("game_id").n_unique().alias("games")])
        a = _rates_from_counts(a)              # cf60, xg60, ... (shot axes; uses 'cf' as attempts)
        a = _rich_rates(a)                     # tk60, gv60, block60, hit60, ..., ca60, xga60
        keep = ["pid", "games", "toi"] + RICH_INDIV_AXES + UNIT_AXES
        return a.select(keep).rename({c: f"{c}{suffix}" for c in ["games", "toi"] + RICH_INDIV_AXES + UNIT_AXES})

    full = agg(pg, "")
    odd = agg(pg.filter(pl.col("half") == 1), "_odd")
    even = agg(pg.filter(pl.col("half") == 0), "_even")
    prof = full.join(odd, on="pid", how="left").join(even, on="pid", how="left")

    pf = cc._pos_frame().rename({"player_id": "pid"})
    team = (pg.group_by("pid", "team_id").agg(t=pl.col("toi").sum())
            .sort("t", descending=True).unique("pid", keep="first").select("pid", "team_id"))
    prof = (prof.join(pf, on="pid", how="left").with_columns(pg=pl.col("pg").fill_null("F"))
            .join(team, on="pid", how="left").with_columns(season_label=pl.lit(season)))
    # faceoffs (season grain, all-strength): win% + involvement; joined by (pid, season)
    sid = int(season[:4]) * 10000 + int(season[:4]) + 1     # e.g. 2024-25 -> 20242025
    fo = (pl.read_parquet(ENRICH_DIR / "faceoffs.parquet").filter(pl.col("season_id") == sid)
          .with_columns(fo_winpct=pl.col("total_faceoff_wins") /
                        pl.when(pl.col("total_faceoffs") > 0).then(pl.col("total_faceoffs")).otherwise(None),
                        fo_total=pl.col("total_faceoffs"))
          .select(pid="player_id", fo_winpct="fo_winpct", fo_total="fo_total"))
    prof = prof.join(fo, on="pid", how="left")
    if write:
        RICH_DIR.mkdir(parents=True, exist_ok=True)
        prof.write_parquet(RICH_DIR / f"{season.replace('-', '_')}.parquet")
    return prof


if __name__ == "__main__":
    import sys
    rich = "--rich" in sys.argv
    # PRIMARY window only: pre-2015 events carry is_primary_scope=False (Atlas modeling floor 2015-16,
    # integrity-pending), so their 5v5 shot features are empty. The role probe is scoped to the
    # integrity-validated window and breaks out pre-2015 by exclusion (see probe.md §1 scope note).
    seasons = [a for a in sys.argv[1:] if not a.startswith("--")] or config.SEASONS_PRIMARY
    for s in seasons:
        p = build_profiles_rich(s) if rich else build_profiles(s)
        print(f"{s}: player-seasons={p.height:,}  F={p.filter(pl.col('pg')=='F').height}  D={p.filter(pl.col('pg')=='D').height}",
              flush=True)
