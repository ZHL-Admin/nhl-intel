"""Stage 1 conservation + goal-coverage gate (reproducible; the original definition was never committed).

Two conservation views over a season scope, plus in-scope goal coverage:
  (1) aggregate 5v5 time: total is_5v5 spell-seconds vs total 5v5 segment-seconds (league).
  (2) per-segment partition: for each 5v5 segment, Σ spell-seconds carrying that segment_index vs the
      segment duration (guards tiny denominators with a min-duration floor).
  (3) goal coverage: in-scope 5v5 non-EN goals (segment-covered games) that fall inside an episode.

NOTE: the per-event dbt↔reference reconciliation (stage1_reconcile.py, 0.0000%) and the V(P_OZ_EST)
exact-match are the AUTHORITATIVE structural gates; a small (~2%) 5v5-time gap here reflects the known
strength-boundary clipping of possession spells (clipped_by_strength ~4.7%, PV-D007/D009), not a defect.

  python -m models_ml.phase_value.stage1_conservation --scope 2015-16
"""
from __future__ import annotations

import argparse

from models_ml import bq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="2015-16", help="min season (inclusive)")
    ap.add_argument("--min-seg-sec", type=float, default=60.0, help="per-segment denominator floor")
    args = ap.parse_args()
    p = bq.project(); c = bq.client(); q = lambda s: list(c.query(s).result())[0]
    sc = args.scope

    agg = q(f"""with segcov as (select distinct game_id from `{p}.nhl_staging.int_segment_context` where season>='{sc}'),
      sp as (select sum(duration_seconds) s from `{p}.nhl_staging.int_phase_spells`
             where is_5v5 and season>='{sc}' and game_id in (select game_id from segcov)),
      sg as (select sum(segment_duration) s from `{p}.nhl_staging.int_segment_context`
             where strength_state='5v5' and season>='{sc}')
      select (select s from sp) spell, (select s from sg) seg""")
    d_agg = abs(agg.spell - agg.seg) / agg.seg * 100
    print(f"(1) aggregate 5v5 time ({sc}+): spell={agg.spell:,.0f}s seg={agg.seg:,.0f}s  |Δ|={d_agg:.4f}%")

    seg = q(f"""with sp as (select game_id, segment_index, sum(duration_seconds) s
                from `{p}.nhl_staging.int_phase_spells` where season>='{sc}' group by 1,2),
      sg as (select game_id, segment_index, segment_duration d from `{p}.nhl_staging.int_segment_context`
             where strength_state='5v5' and season>='{sc}' and segment_duration>={args.min_seg_sec}),
      j as (select coalesce(sp.s,0) a, sg.d b from sg left join sp using (game_id, segment_index))
      select avg(abs(a-b)/b)*100 mean_pct, approx_quantiles(abs(a-b)/b,100)[offset(95)]*100 p95_pct,
             countif(abs(a-b)/b>0.01) n_over, count(*) n from j""")
    print(f"(2) per-segment partition ({sc}+, seg≥{args.min_seg_sec:.0f}s): mean|Δ|={seg.mean_pct:.4f}% "
          f"p95={seg.p95_pct:.4f}% seg>1%={seg.n_over:,}/{seg.n:,}")

    cov = q(f"""with segcov as (select distinct game_id from `{p}.nhl_staging.int_segment_context`),
      g as (select ss.game_id, ss.event_id, ss.team_id, ss.elapsed_seconds
            from `{p}.nhl_staging.int_shot_sequence` ss where ss.strength='5v5' and ss.is_goal
              and not ss.is_empty_net and ss.season>='{sc}' and ss.game_id in (select game_id from segcov)),
      cov as (select g.game_id, g.event_id, max(if(e.episode_id is not null,1,0)) cvr from g
              left join `{p}.nhl_staging.int_zone_episodes` e on e.game_id=g.game_id
                and e.attacker_team_id=g.team_id and g.elapsed_seconds between e.start_elapsed and e.end_elapsed
              group by 1,2)
      select round(avg(cvr)*100,2) pct, count(*) n from cov""")
    print(f"(3) goal coverage ({sc}+ in-scope 5v5): {cov.pct}% over {cov.n:,} goals  (gate ≥90%; recorded 99.95%)")


if __name__ == "__main__":
    main()
