{{ config(cluster_by=["season", "team_id"]) }}

-- Pairwise shared 5v5 ice per (season, team_id, player_id_a < player_id_b): the raw
-- entanglement / pair-quality input, suitable for a team TOI-matrix view. Skaters only.
-- Each 5v5 segment contributes its duration to every unordered same-team pair on the ice
-- (C(5,2)=10 pairs per team per segment). Stored once per unordered pair; consumers that
-- need a symmetric view union the mirror.

with seg_5v5 as (
    select game_id, segment_index, segment_duration
    from {{ ref('int_segment_5v5_results') }}
),

skaters as (
    select
        s.game_id,
        s.season,
        s.segment_index,
        s.team_id,
        s.player_id,
        r.segment_duration
    from {{ ref('int_shift_segments') }} s
    join seg_5v5 r on r.game_id = s.game_id and r.segment_index = s.segment_index
    where s.is_goalie = 0
),

pairs as (
    select
        a.season,
        a.team_id,
        a.player_id as player_id_a,
        b.player_id as player_id_b,
        a.game_id,
        a.segment_duration
    from skaters a
    join skaters b
        on a.game_id = b.game_id
       and a.segment_index = b.segment_index
       and a.team_id = b.team_id
       and a.player_id < b.player_id
)

select
    season,
    team_id,
    player_id_a,
    player_id_b,
    sum(segment_duration) as toi_together_sec,
    count(distinct game_id) as games_together
from pairs
group by 1, 2, 3, 4
