{{ config(
    materialized='table',
    partition_by={"field": "game_date", "data_type": "date", "granularity": "day"},
    cluster_by=["season", "game_id"]
) }}

-- Phase Value (phase_value_v1) — event-level possession-state assignment (spec Section 5.2).
-- One row per PBP event: possession, absolute puck zone, and liveness AFTER the event, as a
-- right-continuous step function carried forward within a period. THE PYTHON REFERENCE
-- (tests/phase_value/reference_state_machine.py) IS THE SPEC; this SQL conforms to it and is
-- reconciled by models_ml/phase_value/stage1_reconcile.py.
--
-- zone_abs is ABSOLUTE (D_home / N / D_away), derived from the owner-relative zone_code + owner
-- home/away side. Because it is absolute, blocked-shots need no explicit "normalize to shooter"
-- flip: derive from the actual owner (= the BLOCKING team, recon PV-D005) and send possession to
-- the opponent (the shooter, who retains the puck under PV-A1).
--
-- Mapping (top-to-bottom, exactly one applies): see spec §5.2. Liveness is set definitely per
-- event; possession/zone are "set" (else NULL = keep previous, forward-filled within the period);
-- period boundaries reset state to NULL.

{% set mapped_types = "('faceoff','shot-on-goal','missed-shot','goal','blocked-shot','giveaway',"
                      "'takeaway','hit','penalty','stoppage','period-start','period-end','game-end',"
                      "'delayed-penalty','shootout-complete')" %}

with pbp as (
    select
        game_id, season, game_date, event_id, sort_order, period_number,
        type_desc_key, event_owner_team_id, zone_code,
        (period_number - 1) * 1200
            + cast(split(time_in_period, ':')[offset(0)] as int64) * 60
            + cast(split(time_in_period, ':')[offset(1)] as int64) as elapsed_seconds
    from {{ ref('stg_play_by_play') }}
    where time_in_period is not null
    {% if var('phase_dev_seasons') | length > 0 %}
      and season in ({{ "'" + var('phase_dev_seasons') | join("','") + "'" }})
    {% endif %}
),

box as (
    select game_id, home_team_id, away_team_id from {{ ref('stg_boxscores') }}
),

ev as (
    select
        p.*,
        b.home_team_id, b.away_team_id,
        (p.event_owner_team_id = b.home_team_id) as owner_is_home,
        if(p.event_owner_team_id = b.home_team_id, b.away_team_id, b.home_team_id) as owner_opp
    from pbp p
    join box b using (game_id)
),

-- 5v5 flag from the RAPM segment strength (same source int_shot_sequence uses).
ice as (
    select e.game_id, e.event_id, c.strength_state
    from {{ ref('int_on_ice_events') }} e
    join {{ ref('int_segment_context') }} c using (game_id, segment_index)
),

mapped as (
    select
        ev.*,
        -- absolute zone this event SETS (NULL => keep previous). Uses the actual owner's home/away
        -- side; correct for blocked-shots too since zone_abs is absolute.
        case
            when zone_code is null then null
            -- penalty keeps the previous zone (spec §5.2: zone_abs unchanged), even though penalties carry
            -- a zone_code ~99% of the time; only the zone-updating types below set zone_abs.
            when type_desc_key = 'penalty' then null
            when owner_is_home then case zone_code when 'O' then 'D_away' when 'D' then 'D_home' when 'N' then 'N' end
            else                     case zone_code when 'O' then 'D_home' when 'D' then 'D_away' when 'N' then 'N' end
        end as zone_set,
        -- possession this event SETS (NULL => keep previous); reset handled below
        case type_desc_key
            when 'faceoff'      then event_owner_team_id
            when 'shot-on-goal' then event_owner_team_id
            when 'missed-shot'  then event_owner_team_id
            when 'goal'         then event_owner_team_id
            -- PV-D005: possession = the shooting/attacking team = opponent of the (blocking) owner.
            -- §9.3 sensitivity: blocked_shot_possession='owner' uses the naive owner-as-shooter reading.
            when 'blocked-shot' then {% if var('blocked_shot_possession', 'opp') == 'owner' %}event_owner_team_id{% else %}owner_opp{% endif %}
            when 'giveaway'     then owner_opp
            when 'takeaway'     then event_owner_team_id
            else null                                          -- hit/penalty/stoppage/delayed/fallback keep
        end as poss_set,
        -- liveness AFTER this event (definite per type)
        case
            when type_desc_key in ('goal','penalty','stoppage','period-start','period-end','game-end','shootout-complete')
                then false
            else true
        end as is_live,
        (type_desc_key in ('period-start','period-end','game-end')) as is_reset,
        (type_desc_key not in {{ mapped_types }}) as is_unmapped
    from ev
),

filled as (
    select
        *,
        last_value(poss_set ignore nulls) over w as poss_ff,
        last_value(zone_set ignore nulls) over w as zone_ff
    from mapped
    window w as (
        partition by game_id, period_number order by sort_order
        rows between unbounded preceding and current row
    )
)

select
    game_id, season, game_date, period_number, event_id, sort_order, elapsed_seconds,
    type_desc_key, event_owner_team_id, home_team_id, away_team_id, zone_code,
    if(is_reset, null, poss_ff) as poss_after,
    if(is_reset, null, zone_ff) as zone_abs,
    is_live,
    coalesce(ice.strength_state = '5v5', false) as is_5v5,
    is_unmapped
from filled
left join ice using (game_id, event_id)
