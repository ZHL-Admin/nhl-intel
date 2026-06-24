-- CURRENT-TEAM RESOLUTION — the single source the player-side lookups consult for a player's
-- current team. The LIVE roster (stg_roster_current) is the source of truth for CURRENT
-- affiliation, so an offseason trade shows up before the player dresses. The game-derived
-- latest-NHL-game team is the historical fallback for anyone NOT on a live roster (UFAs,
-- minor-leaguers, between-contract players) so NOBODY is dropped. The game-derived path keeps the
-- 01/02/03 game-type filter (preseason/regular/playoff; excludes international games).
--
-- One row per player. team_source tells consumers which path won, so a UI can distinguish a
-- confirmed live-roster move from a stale last-game inference.
--
-- CAVEAT (membership != performance): this resolves the team LABEL only. Performance models
-- (keyed season, team_id per game) are untouched — a just-traded player shows the new team here
-- while his value/archetype still reflect old-team usage until he plays with the new club.

with latest_game as (  -- game-derived current team: most recent NHL game, intl games excluded
    select player_id, team_id from (
        select s.player_id, s.team_id,
            row_number() over (partition by s.player_id order by s.game_id desc) as rn
        from {{ ref('stg_rosters') }} s
        where substr(cast(s.game_id as string), 5, 2) in ('01', '02', '03')
    )
    where rn = 1
),

live as (  -- live-roster current team (already newest-snapshot-per-player in stg_roster_current)
    select player_id, team_id, team_abbrev
    from {{ ref('stg_roster_current') }}
    where team_id is not null
),

-- Full player universe = everyone known from games, plus anyone present only on a live roster.
universe as (
    select player_id from latest_game
    union distinct
    select player_id from live
),

resolved as (
    select
        u.player_id,
        coalesce(live.team_id, lg.team_id) as current_team_id,
        live.team_id is not null as is_live_roster,
        case when live.team_id is not null then 'live_roster' else 'latest_game' end as team_source
    from universe u
    left join live on live.player_id = u.player_id
    left join latest_game lg on lg.player_id = u.player_id
)

select * from resolved
