{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "team_id"]
) }}

with team_stats as (
    select
        game_id,
        game_date,
        season,
        team_id,
        team_abbrev,
        cf_pct,
        xgf_pct,
        hdcf_per60,
        hdca_per60
    from {{ ref('mart_team_game_stats') }}
),

with_row_numbers as (
    select
        *,
        row_number() over (partition by team_id, season order by game_date) as game_number
    from team_stats
),

rolling_calcs as (
    select
        game_id,
        game_date,
        season,
        team_id,
        team_abbrev,
        game_number,
        cf_pct,
        xgf_pct,
        hdcf_per60,
        hdca_per60,

        avg(cf_pct) over (
            partition by team_id, season
            order by game_date
            rows between 4 preceding and current row
        ) as rolling_cf_pct_5gp,

        avg(xgf_pct) over (
            partition by team_id, season
            order by game_date
            rows between 4 preceding and current row
        ) as rolling_xgf_pct_5gp,

        avg(hdcf_per60) over (
            partition by team_id, season
            order by game_date
            rows between 4 preceding and current row
        ) as rolling_hdcf_per60_5gp,

        avg(hdca_per60) over (
            partition by team_id, season
            order by game_date
            rows between 4 preceding and current row
        ) as rolling_hdca_per60_5gp

    from with_row_numbers
),

final as (
    select
        game_id,
        game_date,
        season,
        team_id,
        team_abbrev,
        cf_pct as current_cf_pct,
        rolling_cf_pct_5gp,
        xgf_pct as current_xgf_pct,
        rolling_xgf_pct_5gp,
        hdcf_per60 as current_hdcf_per60,
        rolling_hdcf_per60_5gp,
        hdca_per60 as current_hdca_per60,
        rolling_hdca_per60_5gp,

        case
            when game_number >= 5 then true
            else false
        end as has_full_5game_sample

    from rolling_calcs
)

select * from final
