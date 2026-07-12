"""Typed query interface for System Effects (Phase 4.3).

Mirrors the Deployment Atlas `atlas.api` pattern: every accessor returns a polars DataFrame or a
plain dict, reads the frozen research-layer tables under data/parquet/, and touches no production.
Two product surfaces are exposed — both COMPUTED, not yet published (promotion is Phase 7 only):

  portability / predicted_delta   — the INTERNAL/deployment track (Phase 3 gate: ALIVE)
  schedule_adjustment             — the OPPONENT-track survivor (strength-only, DESCRIPTIVE)

Per the Phase 3 gate ruling, `zone_start_polarization` is the PRIMARY portability axis and
`top6_fwd_toi_share` carries a stability caveat; the opponent style-matchup interactions were
KILLED and are NOT exposed.

Build the backing tables first:  `make phase4`  (or `python -m syseff.phase4`).
"""
from __future__ import annotations

import polars as pl

from . import config, portability as _port, opponent as _opp

PORT_PARQUET = config.PARQUET / "portability.parquet"
SCHED_PARQUET = config.PARQUET / "schedule_adjustment.parquet"


def portability(player_id: int, season: str) -> pl.DataFrame:
    """Portability of a player-season: the share of the player's on-ice value that is
    SYSTEM-DEPENDENT (deployment-system + type-by-deployment) vs SKILL (frozen RAPM). Columns:
    system_dependence (in [0,1], + 90% CI), portability (= 1 - system_dependence), sys_contrib
    (absolute xG-share-pt contribution of the current system, + 90% CI), type_id, skill_dev.

    Higher system_dependence = more of the number is a property of the current deployment system
    and would NOT travel; higher portability = value is skill and travels. The ratio is
    undefined-in-spirit for players near league-average skill; rank by absolute contribution
    (sys, xG-share pts) — the surface's primary framing (amendment 4.1a) — and read the
    `material` flag (sys CI excludes 0 AND |sys| >= 0.004) before calling a player system-dependent.

    F14 (thin mediation): a coach change's on-ice result effect is small (+0.004 score-close
    on-ice xG-share DiD, t=1.73) and only ~4% of the within-player result change is mediated by
    the measured deployment change (mediation R^2=0.04). Portability quantifies the
    deployment-system share of a player's CURRENT number; it is not a guarantee of result change
    on a move.

    Example:
        >>> from syseff import api
        >>> api.portability(8481556, "2024-25").select("system_dependence", "portability", "sys_contrib")
    """
    return pl.read_parquet(PORT_PARQUET).filter(
        (pl.col("player_id") == player_id) & (pl.col("season_label") == season))


def predicted_delta(player_id: int, season: str, dest_team_id: int, dest_season: str) -> dict:
    """Expected on-ice 5v5 xG-share shift if `player_id` (their `season` type/role) moved into the
    destination team-season's deployment fingerprint, with a 90% bootstrap CI. Role is held at the
    player's type. Returns a dict incl. `predicted_xg_share_delta`, `ci90`, `primary_axis_shift_z`
    (the zone-start-polarization shift, the primary axis), and the F14 caveat verbatim.

    Example:
        >>> from syseff import api
        >>> api.predicted_delta(8481556, "2024-25", 12, "2023-24")["predicted_xg_share_delta"]
    """
    return _port.predicted_delta(player_id, season, dest_team_id, dest_season)


def schedule_adjustment(player_id: int, season: str) -> pl.DataFrame:
    """The OPPONENT-track survivor: a STRENGTH-ONLY opponent-schedule adjustment for a
    player-season (xG-share points the number is shifted by facing an easier/harder opponent set
    than league-average). DESCRIPTIVE ACCOUNTING ONLY — the style-matchup interactions were killed
    at the Phase 3 gate, so there is NO predictive claim and NO validation bar. Typical magnitude
    is small (|adj| mean ~0.003, p90 ~0.0065).

    Example:
        >>> from syseff import api
        >>> api.schedule_adjustment(8478402, "2024-25").select("schedule_adjustment")
    """
    return pl.read_parquet(SCHED_PARQUET).filter(
        (pl.col("player_id") == player_id) & (pl.col("season_label") == season))


def portability_leaderboard(season: str = "2024-25", min_toi_min: float = 700.0,
                            system_dependent: bool = True, material_only: bool = True,
                            n: int = 15) -> pl.DataFrame:
    """Notable players of a season ranked by ABSOLUTE system contribution |sys| (amendment 4.1a),
    most system-dependent (default) or most system-independent. `material_only=True` restricts the
    system-dependent end to players carrying the material label (sys CI excludes 0 AND
    |sys| >= 0.004). system_dependence is returned as a secondary column.

    Example:
        >>> from syseff import api
        >>> api.portability_leaderboard("2024-25", system_dependent=False).head(5)
    """
    d = pl.read_parquet(PORT_PARQUET).filter(
        (pl.col("season_label") == season) & (pl.col("toi_min") >= min_toi_min))
    if system_dependent:
        d = d.filter(pl.col("material") if material_only else pl.col("sys_ci_excludes_zero"))
    d = d.sort("abs_sys", descending=system_dependent).head(n)
    return d.select("player_id", "team_id", "type_id", "toi_min", "sys_contrib",
                    "sys_ci_lo", "sys_ci_hi", "material", "system_dependence", "portability")


def schedule_extremes(season: str = "2024-25", n: int = 10) -> dict:
    """The most schedule-flattered / -punished player-seasons (descriptive exhibit).

    Example:
        >>> from syseff import api
        >>> api.schedule_extremes("2024-25")["most_flattered_top10"][0]
    """
    return _opp.schedule_exhibit(season, n)
