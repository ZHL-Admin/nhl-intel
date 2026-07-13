"""Link A.1 — behavioral axes per (focal player A, season, partner B), 5v5.

For focal A given teammate B, over their SHARED ice (both on the same side of a stint), A's own
recorded behavior: shot-attempt rate & A's share of the pair's combined attempts (shooting
deference/assertion); hit rate (physicality); takeaway/giveaway rates (possession risk); offensive-
zone shot rate (D-pair activation proxy); and the shot-adjacent FEEDING proxies (A's event immediately
precedes a B shot within N s, and the mirror). Everything is A's INDIVIDUAL behavior conditioned on B
— not a pair residual (F17) or a unit over-performance (F18).

Machinery reuses the Chemistry stint expansion; events are attributed to their actor via the role-fit
enriched event_players (recovered six-column attribution) and located in their stint by an as-of time
join (validated 99.8% match). Proxy honesty: FEEDING is shot-adjacent sequence inference, NOT true
passing (off-puck / non-shot passes are invisible — Tier iii).
"""
from __future__ import annotations

import polars as pl

from . import config
import chem.corpus as cc

BEHAV_DIR = config.PARQUET / "behavior"
FEED_WINDOW_S = 4                 # shot-adjacent feed window (sensitivity reported in Link A)
SHOT_TYPES = ["shot-on-goal", "missed-shot", "goal", "blocked-shot"]
ACTION_TYPES = SHOT_TYPES + ["hit", "takeaway", "giveaway"]


def _stints(season: str) -> pl.DataFrame:
    """5v5 RS stints with rid + start/end seconds + on-ice lists + OZ flag + score."""
    st = (pl.scan_parquet(config.ATLAS_PARQUET / "stints.parquet")
          .filter((pl.col("season_label") == season) & (~pl.col("is_quarantined"))
                  & (~pl.col("is_playoffs")) & (pl.col("strength_state") == "5v5")
                  & (pl.col("home_skater_ids").list.len() == 5)
                  & (pl.col("away_skater_ids").list.len() == 5))
          .select("game_id", "start_seconds", "end_seconds", "duration_seconds",
                  "home_skater_ids", "away_skater_ids", "start_type", "score_state")
          .collect().with_row_index("rid"))
    return st


# count columns aggregated at (A,B,game) then rolled to full / odd / even
_CNT = ["dur", "n_shot", "n_hit", "n_tk", "n_gv", "n_oz_shot", "feed"]


def _actor_events(season: str) -> pl.DataFrame:
    """Per event: actor pid, family, game_id, event_second, zone (5v5, primary scope, action types)."""
    ev = (pl.scan_parquet(config.ATLAS_PARQUET / "events.parquet")
          .filter((pl.col("season_label") == season) & pl.col("is_primary_scope")
                  & (pl.col("situation_code") == "1551") & pl.col("type_desc_key").is_in(ACTION_TYPES))
          .select("game_id", "event_id", "event_second", "type_desc_key", "zone_code",
                  "shooting_player_id", "scoring_player_id").collect())
    epl = pl.read_parquet(config.ENRICH_DIR / "event_players.parquet",
                          columns=["game_id", "event_id", "hitting_player_id", "generic_player_id"])
    ev = ev.join(epl, on=["game_id", "event_id"], how="left").with_columns(
        actor=pl.when(pl.col("type_desc_key") == "goal").then(pl.col("scoring_player_id"))
        .when(pl.col("type_desc_key") == "hit").then(pl.col("hitting_player_id"))
        .when(pl.col("type_desc_key").is_in(["takeaway", "giveaway"])).then(pl.col("generic_player_id"))
        .otherwise(pl.col("shooting_player_id")),
        is_shot=pl.col("type_desc_key").is_in(SHOT_TYPES),
        is_oz_shot=(pl.col("type_desc_key").is_in(SHOT_TYPES) & (pl.col("zone_code") == "O")))
    return ev.filter(pl.col("actor").is_not_null())


def _locate_in_stint(ev: pl.DataFrame, st: pl.DataFrame) -> pl.DataFrame:
    """As-of join each event to its containing stint (rid)."""
    stv = st.select("game_id", "rid", "start_seconds", "end_seconds").sort("game_id", "start_seconds")
    j = (ev.sort("game_id", "event_second")
         .join_asof(stv, left_on="event_second", right_on="start_seconds", by="game_id",
                    strategy="backward")
         .filter((pl.col("event_second") >= pl.col("start_seconds"))
                 & (pl.col("event_second") < pl.col("end_seconds"))))
    return j


def _onice(st: pl.DataFrame) -> pl.DataFrame:
    """Per (rid, game_id, side, pid) with the stint duration."""
    def side(ids, sname):
        return st.select("rid", "game_id", pid=pl.col(ids), dur="duration_seconds",
                         side=pl.lit(sname)).explode("pid")
    return pl.concat([side("home_skater_ids", "H"), side("away_skater_ids", "A")])


def _rates(df: pl.DataFrame, suffix: str) -> pl.DataFrame:
    per60 = 3600.0
    return df.with_columns(
        **{f"A_sh60{suffix}": pl.col(f"n_shot{suffix}") / pl.col(f"dur{suffix}") * per60,
           f"A_hit60{suffix}": pl.col(f"n_hit{suffix}") / pl.col(f"dur{suffix}") * per60,
           f"A_tk60{suffix}": pl.col(f"n_tk{suffix}") / pl.col(f"dur{suffix}") * per60,
           f"A_gv60{suffix}": pl.col(f"n_gv{suffix}") / pl.col(f"dur{suffix}") * per60,
           f"A_ozsh60{suffix}": pl.col(f"n_oz_shot{suffix}") / pl.col(f"dur{suffix}") * per60,
           f"A_feed60{suffix}": pl.col(f"feed{suffix}") / pl.col(f"dur{suffix}") * per60})


def build_behavior(season: str, write: bool = True) -> pl.DataFrame:
    st = _stints(season)
    ev = _locate_in_stint(_actor_events(season), st)   # located events carry rid + game_id
    onice = _onice(st)

    pse = ev.group_by("rid", pl.col("actor").alias("pid")).agg(
        n_shot=pl.col("is_shot").sum(), n_hit=(pl.col("type_desc_key") == "hit").sum(),
        n_tk=(pl.col("type_desc_key") == "takeaway").sum(),
        n_gv=(pl.col("type_desc_key") == "giveaway").sum(),
        n_oz_shot=pl.col("is_oz_shot").sum())
    af = (onice.join(pse, on=["rid", "pid"], how="left")
          .with_columns([pl.col(c).fill_null(0) for c in ("n_shot", "n_hit", "n_tk", "n_gv", "n_oz_shot")])
          .rename({"pid": "A"}))
    partners = onice.select("rid", "side", B="pid")
    dp = af.join(partners, on=["rid", "side"], how="inner").filter(pl.col("A") != pl.col("B"))
    feed = _feeding(ev, onice)                        # per (A, B, game_id)
    # directed (A, B, game) counts
    g = dp.group_by("A", "B", "game_id").agg(
        dur=pl.col("dur").sum(), n_shot=pl.col("n_shot").sum(), n_hit=pl.col("n_hit").sum(),
        n_tk=pl.col("n_tk").sum(), n_gv=pl.col("n_gv").sum(), n_oz_shot=pl.col("n_oz_shot").sum())
    g = g.join(feed, on=["A", "B", "game_id"], how="left").with_columns(feed=pl.col("feed").fill_null(0))
    # half = parity of game rank within (A,B)
    g = g.with_columns(half=(pl.col("game_id").rank("dense").over("A", "B") % 2))

    def roll(df, suffix):
        a = df.group_by("A", "B").agg([pl.col(c).sum().alias(f"{c}{suffix}") for c in _CNT])
        return _rates(a, suffix)
    full = roll(g, "")
    odd = roll(g.filter(pl.col("half") == 1), "_odd")
    even = roll(g.filter(pl.col("half") == 0), "_even")
    agg = (full.join(odd, on=["A", "B"], how="left").join(even, on=["A", "B"], how="left")
           .rename({"dur": "shared_toi"}).with_columns(season_label=pl.lit(season)))
    # shot-share (full + odd/even) from the swapped (B,A) row; game ranks match so parities align
    swp = agg.select(A="B", B="A", B_shot="n_shot", B_shot_odd="n_shot_odd", B_shot_even="n_shot_even")
    agg = agg.join(swp, on=["A", "B"], how="left")
    for sfx in ("", "_odd", "_even"):
        num = pl.col(f"n_shot{sfx}"); den = num + pl.col(f"B_shot{sfx}")
        agg = agg.with_columns(**{f"A_shot_share{sfx}":
                                  pl.when(den > 0).then(num / den).otherwise(None)})
    if write:
        BEHAV_DIR.mkdir(parents=True, exist_ok=True)
        agg.write_parquet(BEHAV_DIR / f"{season.replace('-', '_')}.parquet")
    return agg


def _feeding(ev: pl.DataFrame, onice: pl.DataFrame) -> pl.DataFrame:
    """Shot-adjacent A->B feed per (A,B,game): within a stint-side, order same-team events; for each
    B shot whose immediately-preceding same-team event (<=FEED_WINDOW_S) was by A, credit (A->B)."""
    side_map = onice.select("rid", pid="pid", side="side")
    e = (ev.join(side_map, left_on=["rid", "actor"], right_on=["rid", "pid"], how="inner")
         .sort("rid", "side", "event_second"))
    e = e.with_columns(prev_actor=pl.col("actor").shift(1).over("rid", "side"),
                       prev_sec=pl.col("event_second").shift(1).over("rid", "side"))
    feeds = e.filter(pl.col("is_shot") & pl.col("prev_actor").is_not_null()
                     & (pl.col("prev_actor") != pl.col("actor"))
                     & ((pl.col("event_second") - pl.col("prev_sec")) <= FEED_WINDOW_S))
    return feeds.group_by(A="prev_actor", B="actor", game_id="game_id").agg(feed=pl.len())


AXES = ["A_sh60", "A_shot_share", "A_hit60", "A_tk60", "A_gv60", "A_ozsh60", "A_feed60"]


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or config.SEASONS_PRIMARY:
        b = build_behavior(s)
        print(f"{s}: directed (A,B) pairs={b.height:,}", flush=True)
