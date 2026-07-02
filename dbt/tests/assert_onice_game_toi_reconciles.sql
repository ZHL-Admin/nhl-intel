-- int_player_onice_game.toi_5v5_sec must equal an INDEPENDENT recompute of the player's 5v5
-- on-ice time: int_shift_segments skaters joined DIRECTLY to int_segment_context 5v5 segments
-- (regular season + playoffs), a separate path that does not route through
-- int_segment_5v5_results. This cross-checks the 5v5 segment-filter and membership join.
--
-- Note: NHL boxscores (stg_boxscores) are team-grain and carry no per-player strength TOI, so
-- shift-derived 5v5 time is the reconciliation truth-source (documented in PHASE6_FINDINGS.md).
-- Both sides sum the same integer int_segment_context.segment_duration, so an exact match is
-- expected; a tolerance of 2 seconds guards only against boundary rounding. Returns offending
-- player-games; the test passes when none.

with independent as (
    select
        s.game_id,
        s.player_id,
        sum(c.segment_duration) as indep_toi_5v5_sec
    from {{ ref('int_shift_segments') }} s
    join {{ ref('int_segment_context') }} c
        on c.game_id = s.game_id and c.segment_index = s.segment_index
    where s.is_goalie = 0
      and c.strength_state = '5v5'
      and substr(cast(s.game_id as string), 5, 2) in ('02', '03')
    group by 1, 2
),

recon as (
    select
        o.game_id,
        o.player_id,
        o.toi_5v5_sec,
        i.indep_toi_5v5_sec,
        abs(o.toi_5v5_sec - i.indep_toi_5v5_sec) as diff_sec
    from {{ ref('int_player_onice_game') }} o
    join independent i
        on i.game_id = o.game_id and i.player_id = o.player_id
)

select *
from recon
where diff_sec > 2
