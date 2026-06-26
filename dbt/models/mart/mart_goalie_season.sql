{{ config(cluster_by=["season", "goalie_id"]) }}

-- Goalie season aggregates on the in-house xG layer (Phase 2.5): season GSAx (total and by
-- danger/strength), save percentages, last-10 rolling GSAx, and an INDEPENDENT second
-- opinion from NHL Edge (blueprint 12.3). Edge exposes only an overall last-10 save pct for
-- goalies (no high-danger split), so the two sources are named distinctly: our_hd_gsax is
-- ours (high-danger), edge_last10_save_pct is Edge's. Cross-validation lives in
-- docs/methodology/goaltending.md.
-- The traditional line (W-L-OTL, GAA, SO, TOI) comes from the OFFICIAL boxscore goalie lines
-- (stg_goalie_starts: real TOI + decision), not the shift charts, which miss some games.

with games as (
    select * from {{ ref('mart_goalie_game_stats') }}
),

ranked as (
    select *,
        row_number() over (partition by goalie_id, season order by game_date desc) as rn
    from games
),

season_agg as (
    select
        goalie_id,
        season,
        any_value(team_id) as team_id,
        count(*) as games_played,
        sum(shots_faced) as shots_faced,
        sum(saves) as saves,
        sum(goals_against) as goals_against,
        sum(xga) as xga,
        sum(gsax) as gsax,
        safe_divide(sum(saves), sum(shots_faced)) as save_pct,
        -- high danger
        sum(high_shots) as high_shots,
        sum(high_saves) as high_saves,
        sum(high_xga) as high_xga,
        sum(high_gsax) as our_hd_gsax,
        safe_divide(sum(high_saves), sum(high_shots)) as our_hd_save_pct,
        -- strength
        sum(ev_gsax) as ev_gsax,
        sum(special_gsax) as special_gsax
    from games
    group by goalie_id, season
),

last10 as (
    select goalie_id, season,
        sum(gsax) as last10_gsax,
        sum(high_gsax) as last10_hd_gsax,
        count(*) as last10_games
    from ranked
    where rn <= 10
    group by goalie_id, season
),

-- Traditional record/rate line from the official boxscore goalie lines. decision is 'W'/'L'/'O'
-- (O = overtime/shootout loss); shutout = a win with zero goals against over essentially a full
-- game (>= 58:00 in net). GAA = goals against per 60 minutes of real time on ice.
starts_agg as (
    select
        goalie_id,
        season,
        sum(case when decision = 'W' then 1 else 0 end) as wins,
        sum(case when decision = 'L' then 1 else 0 end) as losses,
        sum(case when decision = 'O' then 1 else 0 end) as otl,
        sum(case when decision = 'W' and goals_against = 0 and toi_seconds >= 3480 then 1 else 0 end) as shutouts,
        sum(toi_seconds) as toi_seconds,
        safe_divide(sum(goals_against) * 3600.0, sum(toi_seconds)) as gaa
    from {{ ref('stg_goalie_starts') }}
    group by goalie_id, season
),

edge as (
    select
        player_id as goalie_id,
        season_id,
        last10_avg_save_pct,
        games_above_900
    from {{ ref('stg_edge_goalies') }}
)

select
    sa.*,
    -- traditional record / rate line (boxscore)
    st.wins,
    st.losses,
    st.otl,
    st.shutouts,
    st.toi_seconds,
    st.gaa,
    l.last10_gsax,
    l.last10_hd_gsax,
    l.last10_games,
    -- NHL Edge second opinion (overall last-10 save pct; no HD split available from Edge)
    e.last10_avg_save_pct as edge_last10_save_pct,
    e.games_above_900 as edge_games_above_900
from season_agg sa
left join starts_agg st on sa.goalie_id = st.goalie_id and sa.season = st.season
left join last10 l on sa.goalie_id = l.goalie_id and sa.season = l.season
left join edge e
    on sa.goalie_id = e.goalie_id
   and cast(concat(substr(sa.season, 1, 4), '20', substr(sa.season, 6, 2)) as int64) = e.season_id
