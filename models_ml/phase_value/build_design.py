"""Stage 3 — stint-level directional design for the phase-value fits (spec Section 7.1).

Starts from the EXACT RAPM 5v5 stint universe (int_segment_context + int_shift_segments, strength='5v5',
segment_duration >= MIN_EXPOSURE_SECONDS) and attaches, per segment and per attacking direction, the PV
exposures + targets by intersecting the segment with the frozen state engine:
  outside_exposure_sec  — attacker possession in P_OWN_D / P_NZ (from int_phase_spells)
  inzone_sec            — attacker possession in P_OZ_* (= defender in-zone-against)
  episode_starts_nonfo  — episodes (attacker attacking) whose START falls in the segment, start_type != oz_faceoff
  episode_starts_rush   — subset with start_type='rush' (diagnostic sub-fit; event-space category, see PV-D014)
  xg_inzone             — attacker 5v5 unblocked xG for shots inside BOTH the segment AND an episode
  favorable_ends        — episodes (attacker) whose END falls in the segment with end_reason in {exit, flip_sustained}
Plus the zero-duration-episode capture counters (PV-D011).

expand_rows() turns each segment into two direction rows (home attacking, away attacking), mirroring
train_rapm.expand_rows exactly (same controls: score state, zone start, home, back-to-back, season FE,
game-time bucket). MIN_EXPOSURE_SECONDS = 5 (PV-D002, mirrors RAPM MIN_SEGMENT_SECONDS). PV-D011: the
inzone_sec / outside_exposure_sec floors are applied by train_phase_value on STINT TOTALS, never per-episode,
so zero-duration goal episodes keep their start (Fit A) and goal xG (Fit B).
"""
from __future__ import annotations

import pandas as pd

from models_ml import config, bq

CFG = config.PHASE_VALUE_CONFIG
MINSEC = CFG["MIN_EXPOSURE_SECONDS"]   # 5

# per-segment PV measures for BOTH directions (home/away as attacker) + RAPM controls + the two 5-skater sets.
DESIGN_SQL = """
with seg as (
  select sc.game_id, sc.segment_index, sc.season, sc.segment_duration as dur,
         sc.segment_start_seconds as sstart, sc.segment_end_seconds as send,
         sc.home_team_id, sc.away_team_id, sc.home_score_state, sc.zone_start_code
  from `{p}.nhl_staging.int_segment_context` sc
  where sc.strength_state = '5v5' and sc.segment_duration >= {minsec}
    and sc.season in ({seasons})
),
sk as (
  select s.game_id, s.segment_index,
    array_agg(if(s.team_id = seg.home_team_id, s.player_id, null) ignore nulls) as home_sk,
    array_agg(if(s.team_id = seg.away_team_id, s.player_id, null) ignore nulls) as away_sk
  from `{p}.nhl_staging.int_shift_segments` s
  join seg on s.game_id = seg.game_id and s.segment_index = seg.segment_index
  where s.is_goalie = 0
  group by 1, 2
),
expo as (
  select sp.game_id, sp.segment_index,
    sum(if(sp.poss_team_id = s.home_team_id and sp.state_rel in ('P_OWN_D','P_NZ'), sp.duration_seconds, 0)) as home_outside_sec,
    sum(if(sp.poss_team_id = s.home_team_id and sp.state_rel = 'P_OZ', sp.duration_seconds, 0)) as home_inzone_sec,
    sum(if(sp.poss_team_id = s.away_team_id and sp.state_rel in ('P_OWN_D','P_NZ'), sp.duration_seconds, 0)) as away_outside_sec,
    sum(if(sp.poss_team_id = s.away_team_id and sp.state_rel = 'P_OZ', sp.duration_seconds, 0)) as away_inzone_sec
  from `{p}.nhl_staging.int_phase_spells` sp
  join seg s using (game_id, segment_index)
  where sp.is_5v5 and sp.is_live and sp.poss_team_id is not null and sp.state_rel is not null
  group by 1, 2
),
epstart as (  -- episodes whose START instant falls in the segment (per attacker side)
  select s.game_id, s.segment_index,
    countif(e.attacker_team_id = s.home_team_id and e.start_type != 'oz_faceoff') as home_ep_nonfo,
    countif(e.attacker_team_id = s.home_team_id and e.start_type = 'rush') as home_ep_rush,
    countif(e.attacker_team_id = s.home_team_id and e.start_type != 'oz_faceoff' and e.duration_seconds = 0) as home_ep_nonfo_zerodur,
    countif(e.attacker_team_id = s.away_team_id and e.start_type != 'oz_faceoff') as away_ep_nonfo,
    countif(e.attacker_team_id = s.away_team_id and e.start_type = 'rush') as away_ep_rush,
    countif(e.attacker_team_id = s.away_team_id and e.start_type != 'oz_faceoff' and e.duration_seconds = 0) as away_ep_nonfo_zerodur
  from seg s
  join `{p}.nhl_staging.int_zone_episodes` e
    on e.game_id = s.game_id and e.start_elapsed >= s.sstart and e.start_elapsed < s.send
  group by 1, 2
),
epend as (  -- favorable ends (exit / flip_sustained) whose END instant falls in the segment
  select s.game_id, s.segment_index,
    countif(e.attacker_team_id = s.home_team_id and e.end_reason in ('exit','flip_sustained')) as home_fav_ends,
    countif(e.attacker_team_id = s.away_team_id and e.end_reason in ('exit','flip_sustained')) as away_fav_ends
  from seg s
  join `{p}.nhl_staging.int_zone_episodes` e
    on e.game_id = s.game_id and e.end_elapsed >= s.sstart and e.end_elapsed < s.send
  group by 1, 2
),
shots as (
  select ss.game_id, ss.team_id, ss.elapsed_seconds, coalesce(x.xg, 0.0) as xg
  from `{p}.nhl_staging.int_shot_sequence` ss
  left join `{p}.nhl_models.shot_xg` x using (game_id, event_id)
  where ss.strength = '5v5'
),
shots_in_ep as (  -- attacker 5v5 shots that fall inside an episode (flag zero-duration-episode membership)
  select sh.game_id, sh.team_id, sh.elapsed_seconds, sh.xg,
         logical_or(e.duration_seconds = 0) as zerodur
  from shots sh
  join `{p}.nhl_staging.int_zone_episodes` e
    on e.game_id = sh.game_id and e.attacker_team_id = sh.team_id
   and sh.elapsed_seconds between e.start_elapsed and e.end_elapsed
  group by sh.game_id, sh.team_id, sh.elapsed_seconds, sh.xg
),
xginzone as (
  select s.game_id, s.segment_index,
    sum(if(sh.team_id = s.home_team_id, sh.xg, 0.0)) as home_xg_inzone,
    sum(if(sh.team_id = s.away_team_id, sh.xg, 0.0)) as away_xg_inzone,
    sum(if(sh.team_id = s.home_team_id and sh.zerodur, sh.xg, 0.0)) as home_xg_inzone_zerodur,
    sum(if(sh.team_id = s.away_team_id and sh.zerodur, sh.xg, 0.0)) as away_xg_inzone_zerodur
  from seg s
  join shots_in_ep sh on sh.game_id = s.game_id and sh.elapsed_seconds >= s.sstart and sh.elapsed_seconds < s.send
  group by 1, 2
)
select seg.game_id, seg.season, seg.dur, seg.sstart as segment_start_seconds,
       seg.home_team_id, seg.away_team_id, seg.home_score_state, seg.zone_start_code,
       sk.home_sk, sk.away_sk,
       coalesce(expo.home_outside_sec,0.0) home_outside_sec, coalesce(expo.home_inzone_sec,0.0) home_inzone_sec,
       coalesce(expo.away_outside_sec,0.0) away_outside_sec, coalesce(expo.away_inzone_sec,0.0) away_inzone_sec,
       coalesce(epstart.home_ep_nonfo,0) home_ep_nonfo, coalesce(epstart.home_ep_rush,0) home_ep_rush,
       coalesce(epstart.home_ep_nonfo_zerodur,0) home_ep_nonfo_zerodur,
       coalesce(epstart.away_ep_nonfo,0) away_ep_nonfo, coalesce(epstart.away_ep_rush,0) away_ep_rush,
       coalesce(epstart.away_ep_nonfo_zerodur,0) away_ep_nonfo_zerodur,
       coalesce(epend.home_fav_ends,0) home_fav_ends, coalesce(epend.away_fav_ends,0) away_fav_ends,
       coalesce(xginzone.home_xg_inzone,0.0) home_xg_inzone, coalesce(xginzone.away_xg_inzone,0.0) away_xg_inzone,
       coalesce(xginzone.home_xg_inzone_zerodur,0.0) home_xg_inzone_zerodur,
       coalesce(xginzone.away_xg_inzone_zerodur,0.0) away_xg_inzone_zerodur
from seg
join sk using (game_id, segment_index)
left join expo using (game_id, segment_index)
left join epstart using (game_id, segment_index)
left join epend using (game_id, segment_index)
left join xginzone using (game_id, segment_index)
"""

FLIP = {"leading": "trailing", "trailing": "leading", "tied": "tied"}
ZONE_CATS = ("O", "D", "N")


def pull(seasons: list[str]) -> pd.DataFrame:
    sql = DESIGN_SQL.format(p=bq.project(), minsec=MINSEC,
                            seasons=", ".join(f"'{s}'" for s in seasons))
    return bq.query_df(sql, bq.client())


def expand_rows(df: pd.DataFrame, b2b: dict, season_weights: dict | None):
    """Two direction rows per segment (home attacking, away attacking), mirroring train_rapm.expand_rows.
    Each row carries the PV exposures/targets for that attacker + the RAPM controls + game_id (bootstrap)."""
    rows = []
    for r in df.itertuples():
        home_sk, away_sk = list(r.home_sk), list(r.away_sk)
        if len(home_sk) != 5 or len(away_sk) != 5:
            continue  # data noise — documented exclusion (matches RAPM)
        sw = 1.0 if season_weights is None else season_weights.get(r.season, 1.0)
        zone = r.zone_start_code if r.zone_start_code in ZONE_CATS else None
        gt = min(int(r.segment_start_seconds) // 1200, 3)
        rows.append(dict(game_id=r.game_id, off=home_sk, deff=away_sk, season=r.season, sw=sw,
                         score_state=r.home_score_state, zone=zone, home=1.0, gt=gt,
                         b2b=b2b.get((int(r.game_id), int(r.home_team_id)), 0.0),
                         outside_sec=r.home_outside_sec, inzone_sec=r.home_inzone_sec,
                         ep_nonfo=r.home_ep_nonfo, ep_rush=r.home_ep_rush, ep_nonfo_zerodur=r.home_ep_nonfo_zerodur,
                         fav_ends=r.home_fav_ends, xg_inzone=r.home_xg_inzone, xg_inzone_zerodur=r.home_xg_inzone_zerodur))
        rows.append(dict(game_id=r.game_id, off=away_sk, deff=home_sk, season=r.season, sw=sw,
                         score_state=FLIP[r.home_score_state], zone=zone, home=0.0, gt=gt,
                         b2b=b2b.get((int(r.game_id), int(r.away_team_id)), 0.0),
                         outside_sec=r.away_outside_sec, inzone_sec=r.away_inzone_sec,
                         ep_nonfo=r.away_ep_nonfo, ep_rush=r.away_ep_rush, ep_nonfo_zerodur=r.away_ep_nonfo_zerodur,
                         fav_ends=r.away_fav_ends, xg_inzone=r.away_xg_inzone, xg_inzone_zerodur=r.away_xg_inzone_zerodur))
    return rows


def main() -> None:
    import sys
    seasons = list(getattr(config, "SEASONS", ["2023-24", "2024-25", "2025-26"]))
    df = pull(seasons)
    print(f"[build_design] segments={len(df):,}  (MIN_EXPOSURE_SECONDS={MINSEC})", file=sys.stderr)
    cols = ["home_outside_sec", "home_inzone_sec", "home_ep_nonfo", "home_ep_rush",
            "home_ep_nonfo_zerodur", "home_fav_ends", "home_xg_inzone", "home_xg_inzone_zerodur"]
    print(df[cols].astype(float).sum().to_string())


if __name__ == "__main__":
    main()
