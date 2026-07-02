-- Sanity: a known welded top-pair defenseman must show high partner concentration. Moritz Seider
-- (DET) played the bulk of his 2025-26 5v5 minutes glued to Simon Edvinsson (724 shared minutes,
-- recorded in docs/PHASE6_FINDINGS.md), so his max_partner_toi_share must land clearly in the
-- entangled range (> 0.55). Returns a row (failing) if he is missing from the mart or his share is
-- not entangled; the test passes when the single check row is empty.

with seider as (
    select distinct player_id
    from {{ ref('stg_rosters') }}
    where last_name = 'Seider' and first_name = 'Moritz'
),

chk as (
    select coalesce(max(e.max_partner_toi_share), -1) as max_share
    from {{ ref('mart_player_entanglement') }} e
    where e.season = '2025-26'
      and e.player_id in (select player_id from seider)
)

select *
from chk
where max_share <= 0.55
