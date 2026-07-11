"""Phase 1 runner — ledger validation (1.3) and experiment cohorts (1.4).

Reproducible from cache: reads the assembled coach table + frozen Atlas stints,
writes reports/phase1_analysis.json. The prose report is reports/phase1.md.
"""
from __future__ import annotations

import json

import polars as pl

from . import config, regime_ledger as R

MIN_5V5_MIN = 100.0          # cohort C: skater qualification per coach
MIN_GAMES_EACH = 15          # cohort C: games under each coach in the change season


# ---------------------------------------------------------------- 5v5 TOI attribution
def player_game_5v5_min(game_ids: set[int]) -> pl.DataFrame:
    """Per (game_id, player_id, side) 5v5 minutes from frozen stints.
    Excludes quarantined stints and playoffs (standing rules)."""
    lf = pl.scan_parquet(config.ATLAS_PARQUET / "stints.parquet").filter(
        (pl.col("strength_state") == "5v5")
        & (~pl.col("is_quarantined"))
        & (~pl.col("is_playoffs"))
        & (pl.col("game_id").is_in(list(game_ids)))
    )
    home = (lf.select("game_id", "duration_seconds",
                      pl.col("home_skater_ids").alias("pid"))
              .explode("pid").with_columns(side=pl.lit("home")))
    away = (lf.select("game_id", "duration_seconds",
                      pl.col("away_skater_ids").alias("pid"))
              .explode("pid").with_columns(side=pl.lit("away")))
    both = pl.concat([home, away])
    return (both.group_by("game_id", "pid", "side")
                .agg(sec=pl.col("duration_seconds").sum())
                .with_columns(min5v5=pl.col("sec") / 60.0)
                .collect())


# ---------------------------------------------------------------- validation (1.3)
def validate(ledger: pl.DataFrame, tg: pl.DataFrame) -> dict:
    res: dict = {}

    # (a) internal consistency: coach coverage + game-count identity.
    total_team_games = tg.filter(pl.col("coach").is_not_null()).height
    null_team_games = tg.filter(pl.col("coach").is_null()).height
    sum_regime_games = int(ledger["games_in_regime"].sum())
    res["a_consistency"] = {
        "team_games_with_coach": total_team_games,
        "team_games_null_coach": null_team_games,     # reported as a product (gaps)
        "sum_games_in_regime": sum_regime_games,
        "identity_holds": total_team_games == sum_regime_games,
    }

    # (b) plausibility. Regimes-per-team-season = regimes with >=1 game in the season.
    reg = R.annotate_regimes(tg.filter(pl.col("coach").is_not_null()))
    rts = (reg.group_by("team_id", "season_label", "regime_seq").len()
              .group_by("team_id", "season_label").agg(n_regimes=pl.len()))
    res["b_regimes_per_team_season_hist"] = (
        rts.group_by("n_regimes").agg(team_seasons=pl.len())
           .sort("n_regimes").to_dicts())
    # mid-season changes per season (season of the change = new regime's start_season)
    msc = (ledger.filter(pl.col("is_mid_season_change"))
                 .group_by("start_season").agg(changes=pl.len()).sort("start_season"))
    res["b_mid_season_changes_per_season"] = msc.to_dicts()
    res["b_flags"] = [r["start_season"] for r in msc.to_dicts()
                      if r["changes"] < 3 or r["changes"] > 20]

    # (c) eyeball lists: 10 longest, 10 shortest regimes.
    cols = ["team_id", "coach_name", "seasons_spanned", "games_in_regime",
            "start_game_id", "end_game_id", "start_date", "end_date",
            "predecessor_coach", "is_mid_season_change"]
    res["c_longest"] = (ledger.sort("games_in_regime", descending=True)
                              .head(10).select(cols).to_dicts())
    res["c_shortest"] = (ledger.sort(["games_in_regime", "start_game_id"])
                               .head(10).select(cols).to_dicts())

    # name-normalization audit: distinct coaches + near-duplicate pairs for eyeball.
    coaches = sorted(c for c in ledger["coach_name"].unique().to_list() if c)
    res["n_distinct_coaches"] = len(coaches)
    dupes = []
    for i, a in enumerate(coaches):
        la = a.split()[-1].lower()
        for b in coaches[i + 1:]:
            lb = b.split()[-1].lower()
            if la == lb or _lev(a.lower(), b.lower()) <= 2:
                dupes.append([a, b])
    res["name_near_duplicates"] = dupes
    return res


def _lev(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------- cohorts (1.4)
def cohort_C(tg: pl.DataFrame) -> dict:
    """Mid-season changes with >=15 games under BOTH coaches in the same season;
    per change, skaters with >=100 5v5 min under both."""
    reg = R.annotate_regimes(tg.filter(pl.col("coach").is_not_null()))
    # per-regime meta + per (regime, season) game counts
    meta = (reg.group_by("regime_seq").agg(
        team_id=pl.col("team_id").first(),
        coach=pl.col("coach").first(),
        start_syear=pl.col("season_start_year").first(),
        start_game_id=pl.col("game_id").min(),
        first_season=pl.col("season_label").first(),
        last_season=pl.col("season_label").last(),
    ).sort(["team_id", "start_syear", "start_game_id"]))
    reg_season = reg.group_by("regime_seq", "season_label").agg(games=pl.len())
    meta = meta.with_columns(
        prev_seq=pl.col("regime_seq").shift(1).over("team_id"),
        prev_last_season=pl.col("last_season").shift(1).over("team_id"),
        prev_coach=pl.col("coach").shift(1).over("team_id"),
    )
    changes = meta.filter(
        pl.col("prev_seq").is_not_null()
        & (pl.col("prev_last_season") == pl.col("first_season"))
    )
    rs = {(r["regime_seq"], r["season_label"]): r["games"]
          for r in reg_season.to_dicts()}
    qualifying = []
    for c in changes.to_dicts():
        S = c["first_season"]
        new_games = rs.get((c["regime_seq"], S), 0)
        old_games = rs.get((c["prev_seq"], S), 0)
        if new_games >= MIN_GAMES_EACH and old_games >= MIN_GAMES_EACH:
            qualifying.append({**c, "season": S,
                               "old_games": old_games, "new_games": new_games})

    # gather game ids for the qualifying team-seasons and compute 5v5 minutes/coach
    seq_by_change = []
    all_gids: set[int] = set()
    reg_games = reg.select("regime_seq", "game_id", "team_id", "coach", "season_label")
    for q in qualifying:
        for seq in (q["prev_seq"], q["regime_seq"]):
            gids = reg_games.filter((pl.col("regime_seq") == seq)
                                    & (pl.col("season_label") == q["season"]))["game_id"].to_list()
            all_gids.update(gids)
        seq_by_change.append(q)

    skater_counts = []
    if all_gids:
        toi = player_game_5v5_min(all_gids)
        # attach team_id + coach per (game, side) from reg_games (game->team,coach)
        gt = reg_games.rename({"game_id": "game_id"}).unique(subset=["game_id", "team_id"])
        # map side->team: home side player is on that game's home team; we resolve via
        # the team_games rows (each game has 2 teams). Build (game_id, is_home->team).
        gc = R.assemble_game_coaches().select("game_id", "home_team_id", "away_team_id")
        toi = toi.join(gc, on="game_id", how="left").with_columns(
            team_id=pl.when(pl.col("side") == "home").then(pl.col("home_team_id"))
                     .otherwise(pl.col("away_team_id"))
        )
        # per (season not needed; restrict per change): join coach via reg_games
        rgg = reg_games.select("game_id", "team_id", "coach")
        toi = toi.join(rgg, on=["game_id", "team_id"], how="inner")
        agg = (toi.group_by("team_id", "coach", "pid")
                  .agg(mins=pl.col("min5v5").sum()))
        for q in seq_by_change:
            T = q["team_id"]
            new_c, old_c = q["coach"], q["prev_coach"]
            under_new = set(agg.filter((pl.col("team_id") == T) & (pl.col("coach") == new_c)
                                       & (pl.col("mins") >= MIN_5V5_MIN))["pid"].to_list())
            under_old = set(agg.filter((pl.col("team_id") == T) & (pl.col("coach") == old_c)
                                       & (pl.col("mins") >= MIN_5V5_MIN))["pid"].to_list())
            q["n_skaters_both"] = len(under_new & under_old)
            skater_counts.append(q)

    per_season: dict = {}
    for q in skater_counts:
        d = per_season.setdefault(q["season"], {"changes": 0, "skaters_total": 0, "detail": []})
        d["changes"] += 1
        d["skaters_total"] += q.get("n_skaters_both", 0)
        d["detail"].append({
            "team_id": q["team_id"], "old_coach": q["prev_coach"], "new_coach": q["coach"],
            "old_games": q["old_games"], "new_games": q["new_games"],
            "skaters_both_100min": q.get("n_skaters_both", 0),
        })
    return {"n_changes": len(skater_counts),
            "per_season": {k: per_season[k] for k in sorted(per_season)}}


def cohort_M() -> dict:
    m = pl.read_parquet(config.ATLAS_PARQUET / "movers_eval.parquet")
    by = m.group_by("pair").agg(movers=pl.len()).sort("pair")
    return {"n_movers": m.height, "per_pair": by.to_dicts()}


def run() -> dict:
    gc = R.assemble_game_coaches()
    tg = R.to_team_games(gc)
    ledger = R.build_ledger(tg.filter(pl.col("coach").is_not_null()))
    R.OUT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_parquet(R.OUT_LEDGER)
    out = {
        "n_regimes": ledger.height,
        "coach_null_products": {
            "game_team_rows_null_coach": tg.filter(pl.col("coach").is_null()).height,
            "games_missing_any_coach": gc.filter(
                pl.col("home_head_coach").is_null() | pl.col("away_head_coach").is_null()
            ).height,
        },
        "validation": validate(ledger, tg),
        "cohort_C": cohort_C(tg),
        "cohort_M": cohort_M(),
    }
    (config.REPORTS / "phase1_analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != "validation"}, indent=2, default=str)[:2000])
