{{ config(
    materialized='table',
    partition_by={"field": "game_date", "data_type": "date", "granularity": "day"},
    cluster_by=["season", "defending_team_id"]
) }}

-- Phase Value (phase_value_v1) — DZ episodes (spec Section 5.4). A threatening sequence against
-- defending team d: a maximal set of state spells where the opponent possesses in d's D zone, merging
-- brief interruptions (defender touches) that stay in-zone, live, and total <= phase_episode_gap_seconds.
-- Grain: one row per episode. Conforms to tests/phase_value/reference_state_machine.py (reconciled by
-- stage1_reconcile.py). start_type precedence oz_faceoff > rush > forecheck > carry_other; end_reason
-- goal > stoppage > exit > flip_sustained. Outcomes (unblocked attempts / xG / goals) join int_shot_sequence
-- + shot_xg (5v5). v1 keeps only episodes fully inside 5v5; episodes clipped by a strength change end as
-- 'stoppage' at the boundary with clipped_by_strength = true.

{% set gap = var('phase_episode_gap_seconds') %}
{% set rush_w = var('rush_window_seconds') %}
{% set ozfo_link = var('phase_oz_faceoff_link_seconds') %}

with ev as (
    select game_id, season, game_date, period_number, sort_order, elapsed_seconds,
           type_desc_key, event_owner_team_id, zone_code,
           home_team_id, away_team_id, poss_after, zone_abs, is_live, is_5v5
    from {{ ref('int_phase_events') }}
),

-- rebuild STATE spells (maximal constant (poss,zone,live)); carry the start event's sort_order/type/owner
marked as (
    select *,
        case
            when lag(elapsed_seconds) over w is null then 1
            when coalesce(cast(poss_after as string), '~') != coalesce(cast(lag(poss_after) over w as string), '~')
              or coalesce(zone_abs, '~') != coalesce(lag(zone_abs) over w, '~')
              or is_live != lag(is_live) over w then 1
            else 0
        end as is_change
    from ev
    window w as (partition by game_id, period_number order by sort_order)
),
seq as (
    select *, sum(is_change) over (partition by game_id, period_number order by sort_order
                                   rows between unbounded preceding and current row) as spell_seq
    from marked
),
state_spells as (
    select
        game_id, season, game_date, period_number, spell_seq,
        min(elapsed_seconds) as start_elapsed,
        min(sort_order)      as start_sort,
        any_value(home_team_id) as home_team_id,
        any_value(away_team_id) as away_team_id,
        any_value(poss_after)   as poss_team_id,
        any_value(zone_abs)     as zone_abs,
        any_value(is_live)      as is_live,
        -- first event of the spell (the transition trigger), by min sort_order
        array_agg(struct(type_desc_key, event_owner_team_id, zone_code) order by sort_order limit 1)[offset(0)] as first_ev
    from seq
    group by game_id, season, game_date, period_number, spell_seq
),
spells as (
    select *,
        coalesce(lead(start_elapsed) over w, start_elapsed) as end_elapsed,
        lead(poss_team_id) over w as next_poss,
        lead(zone_abs)     over w as next_zone,
        lead(is_live)      over w as next_live,
        lead(start_elapsed) over w as next_start,
        lead(first_ev)     over w as next_ev
    from state_spells
    window w as (partition by game_id, period_number order by spell_seq)
),

-- expand to both defending sides; compute per-side flags
sided as (
    select
        s.*,
        d.side,
        if(d.side = 'home', s.home_team_id, s.away_team_id) as defending_team_id,
        if(d.side = 'home', s.away_team_id, s.home_team_id) as attacker_team_id,
        if(d.side = 'home', 'D_home', 'D_away') as d_dzone,
        -- in-zone / dz_ok include a terminating attacker goal (live=false) so rush/quick goals anchor an
        -- episode (spec §5.4 raw-interval condition is possession+zone; goal is the attacker culminating).
        (s.zone_abs = if(d.side = 'home', 'D_home', 'D_away')
         and (s.is_live or s.first_ev.type_desc_key = 'goal')) as dz_ok,
        (s.poss_team_id = if(d.side = 'home', s.away_team_id, s.home_team_id)
         and s.zone_abs = if(d.side = 'home', 'D_home', 'D_away')
         and (s.is_live or s.first_ev.type_desc_key = 'goal')) as in_zone
    from spells s
    cross join unnest([struct('home' as side), struct('away' as side)]) d
),

-- running count of "bad" (not dz_ok) spells, to test whether a gap kept the puck in-zone & live
badcum as (
    select *,
        sum(if(dz_ok, 0, 1)) over (partition by game_id, period_number, side order by spell_seq
                                   rows between unbounded preceding and current row) as bad_cum
    from sided
),

-- island detection over in_zone spells only
inzone as (
    select *,
        lag(end_elapsed) over w as prev_end,
        lag(bad_cum)     over w as prev_badcum
    from badcum
    where in_zone
    window w as (partition by game_id, period_number, side order by spell_seq)
),
episode_marks as (
    select *,
        case
            when prev_end is null then 1
            when (start_elapsed - prev_end) > {{ gap }} then 1     -- gap too long
            when (bad_cum - prev_badcum) > 0 then 1                -- puck left zone / went dead in the gap
            else 0
        end as new_ep
    from inzone
),
episode_ids as (
    select *,
        sum(new_ep) over (partition by game_id, period_number, side order by spell_seq
                          rows between unbounded preceding and current row) as episode_seq
    from episode_marks
),

-- collapse in_zone spells into episodes
episodes as (
    select
        game_id, season, game_date, period_number, side, defending_team_id, attacker_team_id, d_dzone,
        episode_seq,
        min(start_elapsed) as start_elapsed,
        min(start_sort)    as start_sort,
        max(end_elapsed)   as end_elapsed,
        -- terminating spell (right after the last in_zone spell) + the last in_zone spell's own event
        array_agg(struct(next_poss, next_zone, next_live, next_ev, next_start) order by spell_seq desc limit 1)[offset(0)] as term,
        array_agg(first_ev order by spell_seq desc limit 1)[offset(0)] as last_ev
    from episode_ids
    group by game_id, season, game_date, period_number, side, defending_team_id, attacker_team_id, d_dzone, episode_seq
),

-- START EVENT (the transition trigger at start_sort) + rush-window prior events
start_ev as (
    select e.game_id, e.season, e.game_date, e.period_number, e.sort_order as start_sort,
           e.type_desc_key as s_type, e.event_owner_team_id as s_owner, e.zone_abs as s_zone,
           e.elapsed_seconds as s_elapsed, e.is_5v5 as s_5v5
    from ev e
),
-- rush flag: any event within rush_w before start, zone-rel-attacker in (D,N), after every faceoff in window
rush_prior as (
    select
        ep.game_id, ep.period_number, ep.start_sort,
        logical_or(
            case
                when e.event_owner_team_id = ep.attacker_team_id then e.zone_code
                when e.zone_code = 'O' then 'D' when e.zone_code = 'D' then 'O' else 'N'
            end in ('D', 'N')
            and (fo.fo_sort is null or e.sort_order > fo.fo_sort)
        ) as is_rush
    from episodes ep
    join ev e
      on e.game_id = ep.game_id and e.period_number = ep.period_number
     and e.sort_order < ep.start_sort
     and (ep.start_elapsed - e.elapsed_seconds) between 0 and {{ rush_w }}
    left join (
        select ep2.game_id, ep2.start_sort, max(f.sort_order) as fo_sort
        from episodes ep2
        join ev f on f.game_id = ep2.game_id and f.period_number = ep2.period_number
         and f.type_desc_key = 'faceoff'
         and f.sort_order < ep2.start_sort
         and (ep2.start_elapsed - f.elapsed_seconds) between 0 and {{ rush_w }}
        group by ep2.game_id, ep2.start_sort
    ) fo on fo.game_id = ep.game_id and fo.start_sort = ep.start_sort
    group by ep.game_id, ep.period_number, ep.start_sort
),
-- oz_faceoff: an attacker-won faceoff in d's D zone at/just-before start (<= link seconds)
ozfo_prior as (
    select ep.game_id, ep.period_number, ep.start_sort,
        logical_or(f.event_owner_team_id = ep.attacker_team_id and f.zone_abs = ep.d_dzone
                   and (ep.start_elapsed - f.elapsed_seconds) between 0 and {{ ozfo_link }}) as is_ozfo
    from episodes ep
    join ev f on f.game_id = ep.game_id and f.period_number = ep.period_number
       and f.type_desc_key = 'faceoff' and f.sort_order <= ep.start_sort
       and (ep.start_elapsed - f.elapsed_seconds) between 0 and {{ ozfo_link }}
    group by ep.game_id, ep.period_number, ep.start_sort
),

-- OUTCOMES: unblocked 5v5 attempts by the attacker inside [start,end]
shots as (
    select ss.game_id, ss.event_id, ss.team_id, ss.elapsed_seconds, ss.is_goal, ss.period_number,
           coalesce(x.xg, 0.0) as xg
    from {{ ref('int_shot_sequence') }} ss
    left join {{ source('nhl_models', 'shot_xg') }} x using (game_id, event_id)
    where ss.strength = '5v5'
),
outcomes as (
    select ep.game_id, ep.period_number, ep.start_sort,
           count(sh.event_id) as n_unblocked,
           sum(sh.xg) as xg_against,
           countif(sh.is_goal) as goals
    from episodes ep
    left join shots sh
      on sh.game_id = ep.game_id and sh.period_number = ep.period_number
     and sh.team_id = ep.attacker_team_id
     and sh.elapsed_seconds between ep.start_elapsed and ep.end_elapsed
    group by ep.game_id, ep.period_number, ep.start_sort
),

-- 5v5 scoping: is the whole [start,end] inside a single 5v5 stretch? (any non-5v5 overlap -> clipped)
strength_ov as (
    select ep.game_id, ep.period_number, ep.start_sort,
           sum(if(g.strength_state = '5v5', least(ep.end_elapsed, g.segment_end_seconds) - greatest(ep.start_elapsed, g.segment_start_seconds), 0)) as sec_5v5,
           (ep.end_elapsed - ep.start_elapsed) as dur
    from episodes ep
    join {{ ref('int_segment_context') }} g
      on g.game_id = ep.game_id and g.segment_start_seconds < ep.end_elapsed and g.segment_end_seconds > ep.start_elapsed
    group by ep.game_id, ep.period_number, ep.start_sort, ep.end_elapsed, ep.start_elapsed
)

select
    ep.game_id, ep.season, ep.game_date, ep.period_number,
    ep.defending_team_id, ep.attacker_team_id,
    ep.start_elapsed, ep.end_elapsed, (ep.end_elapsed - ep.start_elapsed) as duration_seconds,
    -- start_type
    case
        when coalesce(oz.is_ozfo, false) then 'oz_faceoff'
        when coalesce(r.is_rush, false) then 'rush'
        when se.s_zone = ep.d_dzone
             and ((se.s_type = 'takeaway' and se.s_owner = ep.attacker_team_id)
               or (se.s_type = 'giveaway' and se.s_owner = ep.defending_team_id)) then 'forecheck'
        else 'carry_other'
    end as start_type,
    -- end_reason (goal > stoppage > exit > flip_sustained); term = spell after the last in_zone spell
    case
        when ep.last_ev.type_desc_key = 'goal' then 'goal'   -- last in_zone spell is the attacker goal
        when ep.term.next_ev.type_desc_key = 'goal' and ep.term.next_ev.event_owner_team_id = ep.attacker_team_id then 'goal'
        when ep.term.next_live is distinct from true then 'stoppage'
        when ep.term.next_zone is distinct from ep.d_dzone then 'exit'
        else 'flip_sustained'
    end as end_reason,
    coalesce(o.n_unblocked, 0) as n_unblocked,
    coalesce(o.xg_against, 0.0) as xg_against,
    coalesce(o.goals, 0) as goals,
    -- clipped: the episode crosses out of 5v5 (some non-5v5 time in its span). 0-duration point episodes
    -- (rush goals at a whistle) are never clipped. (PV-D007: v1 keeps clipped episodes flagged, does not
    -- truncate their end to the strength boundary.)
    coalesce((ep.end_elapsed - ep.start_elapsed) - coalesce(st.sec_5v5, 0) > 0.001, false) as clipped_by_strength
from episodes ep
left join start_ev se on se.game_id = ep.game_id and se.start_sort = ep.start_sort
left join rush_prior r on r.game_id = ep.game_id and r.period_number = ep.period_number and r.start_sort = ep.start_sort
left join ozfo_prior oz on oz.game_id = ep.game_id and oz.period_number = ep.period_number and oz.start_sort = ep.start_sort
left join outcomes o on o.game_id = ep.game_id and o.period_number = ep.period_number and o.start_sort = ep.start_sort
left join strength_ov st on st.game_id = ep.game_id and st.period_number = ep.period_number and st.start_sort = ep.start_sort
-- v1: 5v5 scope keyed on the episode START event's strength (robust for 0-duration point episodes)
where coalesce(se.s_5v5, false)
