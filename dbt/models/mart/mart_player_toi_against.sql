{{ config(cluster_by=["season"]) }}

-- AGAINST matrix (NEW in the P1 rebuild): pairwise shared 5v5 ice as OPPONENTS per
-- (season, player_id_a < player_id_b). Sibling to mart_player_toi_matrix, which is
-- teammates only; the AGAINST relation cannot share that mart's (season, team_id, a, b)
-- grain because opponents span two teams, so it lives here with no team_id.
-- Each 5v5 segment contributes its duration to every cross-team pair on the ice
-- (5x5 = 25 opponent pairs per segment). Stored once per unordered pair. Skaters only.

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
        a.player_id as player_id_a,
        b.player_id as player_id_b,
        a.game_id,
        a.segment_duration
    from skaters a
    join skaters b
        on a.game_id = b.game_id
       and a.segment_index = b.segment_index
       and a.team_id != b.team_id       -- OPPONENTS
       and a.player_id < b.player_id     -- each unordered cross-team pair once
)

select
    season,
    player_id_a,
    player_id_b,
    sum(segment_duration) as toi_against_sec,
    count(distinct game_id) as games_against
from pairs
group by 1, 2, 3
