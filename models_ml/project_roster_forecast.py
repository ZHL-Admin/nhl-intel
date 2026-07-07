"""Offseason roster forecast: project how good a team will be next season from its moves.

Each player's next-season WAR is the SHARED projection core (compute_contract_value.blended_war_rate):
a recency/games-weighted blend of his last PROJ_WINDOWS single-season WARs, sample-regressed toward
replacement, then aged one season forward (goalies held flat). Both this tool and the Contract Grader
call it, so a player projects to the same WAR in both. This replaced a per-component shrink-toward-zero
that compressed every established player toward replacement regardless of how stable his record was.

READS ONLY (trains nothing): nhl_models.team_ratings, player_gar, goalie_gar, aging_curves,
player_archetypes; nhl_staging.stg_rosters (base = prior season-end membership) and
int_player_current_team (updated = current membership); and the score_line / score_team_fit
services. Writes nhl_models.roster_forecast (one row per team+transition) and
nhl_models.roster_moves (long, one row per team+transition+player). See
docs/methodology/offseason-forecast.md for the full method and every constant.

The math is in PURE FUNCTIONS at the top (no BigQuery) so the consistency disciplines — the ledger
reconciles, a departed slot is filled at replacement not zero, no-track-record players never get a
point estimate without a wide band, goalie bands exceed skater bands — are unit-tested directly.

Flags (HANDOFF-3): --dry-run (compute, no write + byte estimate), --sample TEAM_OR_TRANSITION,
--resume, --backtest (2024-25 -> 2025-26 calibration). Report:
models_ml/artifacts/reports/project_roster_forecast_<run_id>.md.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from models_ml import config
from models_ml.compute_contract_value import blended_war_rate   # SHARED projection primitive (Tier 0)

CFG = config.ROSTER_FORECAST
GPW = CFG["GOALS_PER_WIN"]
GPS = CFG["GAMES_PER_SEASON"]

# ============================================================================================
# PURE CORE — no BigQuery, no I/O. Everything here is deterministic and unit-tested.
# ============================================================================================


@dataclass
class PlayerProj:
    """A roster player projected forward one season. WAR is value-above-replacement."""
    player_id: int | None
    name: str | None
    position: str          # C/L/R/D/G
    pos_group: str         # F/D/G
    is_goalie: bool
    base_war: float        # this-season realized value (the base_rating already reflects this)
    projected_war: float   # next-season value: skater = blended + aged; goalie = blended flat
    war_sd: float          # band on the projected value (goalie ~3x skater by design)
    no_track_record: bool  # no GAR row at all -> replacement level + a deliberately wide band
    replacement: bool = False   # a filled-but-empty lineup slot (player_id None)
    slot: str | None = None     # which lineup slot it fills/vacates (e.g. "F1".."F12","D1".."D6","G")


def age_multiplier(curve_by_age: dict, age_t, cfg: dict = CFG) -> float:
    """Fractional VALUE multiplier from age_t -> age_t+1 using the production-shaped aging level.

    APPROXIMATION (documented): aging_curves.curve_value is points/82 (production), and we scale a
    VALUE (WAR) number by the curve's level ratio. Clamped so a sparse/extreme segment can't blow up
    or zero out a real player; missing age or non-positive level -> 1.0 (no aging applied).
    """
    if not curve_by_age or age_t is None:
        return 1.0
    a0 = curve_by_age.get(int(age_t))
    a1 = curve_by_age.get(int(age_t) + 1)
    if a0 is None or a1 is None or a0 <= 0:
        return 1.0
    return float(min(cfg["AGE_MULT_CEIL"], max(cfg["AGE_MULT_FLOOR"], a1 / a0)))


def project_skater_war(seasons: list, curve_by_age: dict, age_t, cfg: dict = CFG) -> float:
    """Skater next-season WAR = a recency/games-weighted blend of his last seasons (the SHARED
    blended_war_rate, also used by the Contract Grader), aged one season forward.

    seasons = [(years_ago, war_total, games), ...]; years_ago 0 = current. blended_war_rate is
    sample-regressed toward replacement, so a thin sample shrinks but an established track record is
    kept at its own level — the projection is anchored to the player's OWN production, not pulled
    toward zero. This is what makes a consistently-good player project near his real value (the Byram
    fix) and keeps the two tools consistent. Finishing luck regresses naturally: a one-year shooting
    spike is diluted by his other seasons; a repeatable finishing skill is kept.
    """
    blended, _games = blended_war_rate(seasons)
    return blended * age_multiplier(curve_by_age, age_t, cfg)


def project_goalie_war(seasons: list, cfg: dict = CFG) -> float:
    """Goalie next-season WAR = the same multi-season blend, held FLAT (no skater aging curve)."""
    blended, _games = blended_war_rate(seasons)
    return blended


def build_lineup(players: list[PlayerProj], n_slots: int, value_attr: str,
                 slot_prefix: str, cfg: dict = CFG) -> tuple[list[PlayerProj], float]:
    """Ice a fixed lineup: the best n_slots players by value_attr, summed. Any UNFILLED slot is a
    replacement player at REPLACEMENT_WAR (the slot EXISTS — a hole is never dropped, never zeroed
    out of the lineup count). Returns (slots, total) with exactly n_slots entries.
    """
    ranked = sorted(players, key=lambda p: getattr(p, value_attr), reverse=True)[:n_slots]
    slots: list[PlayerProj] = []
    for i, p in enumerate(ranked):
        p.slot = f"{slot_prefix}{i + 1}"
        slots.append(p)
    total = sum(getattr(p, value_attr) for p in ranked)
    for j in range(len(ranked), n_slots):
        slots.append(PlayerProj(player_id=None, name=None, position=slot_prefix, pos_group=slot_prefix,
                                is_goalie=(slot_prefix == "G"), base_war=cfg["REPLACEMENT_WAR"],
                                projected_war=cfg["REPLACEMENT_WAR"], war_sd=0.0, no_track_record=False,
                                replacement=True, slot=f"{slot_prefix}{j + 1}"))
        total += cfg["REPLACEMENT_WAR"]
    return slots, total


def lineup_value(slots: list[PlayerProj], value_attr: str) -> float:
    return sum(getattr(p, value_attr) for p in slots)


@dataclass
class LineupForecast:
    net_delta_war: float
    base_lineup: list[PlayerProj]
    updated_lineup: list[PlayerProj]
    moves: list[dict] = field(default_factory=list)


def reconcile_ledger(base_lineup: list[PlayerProj], updated_lineup: list[PlayerProj],
                     base_roster_ids: set, updated_roster_ids: set,
                     cfg: dict = CFG) -> tuple[float, list[dict]]:
    """The slot-level delta and a per-player ledger that PARTITIONS it (the consistency discipline).

    delta_contribution is LINEUP-based: (projected_war in the updated lineup) - (projected_war in the
    base lineup); summed it equals net_delta exactly. But move_type is ROSTER-based — whether the
    player is on the base/updated ROSTER, not whether he holds a top-N lineup slot. So a holdover who
    is merely promoted/demoted in the lineup reads as "returning" (he did not join or leave the team),
    and only a genuine roster change reads as "arrival"/"departure".
    """
    base_real = {p.player_id: p for p in base_lineup if p.player_id is not None}
    upd_real = {p.player_id: p for p in updated_lineup if p.player_id is not None}
    n_repl_base = sum(1 for p in base_lineup if p.replacement)
    n_repl_upd = sum(1 for p in updated_lineup if p.replacement)

    # Both lineups are projected forward identically, so a returning player nets to 0 (aging cancels)
    # and a no-move roster nets to 0 — exactly what the deep-offseason "negligible" guard keys on.
    net_delta = lineup_value(updated_lineup, "projected_war") - lineup_value(base_lineup, "projected_war")

    rows: list[dict] = []
    for pid in sorted(set(base_real) | set(upd_real)):
        in_base = pid in base_real
        in_upd = pid in upd_real
        src = upd_real.get(pid) or base_real[pid]
        base_proj = base_real[pid].projected_war if in_base else 0.0   # his base-lineup slot value
        upd_proj = upd_real[pid].projected_war if in_upd else 0.0      # his updated-lineup slot value
        if pid in base_roster_ids and pid in updated_roster_ids:
            move_type = "returning"
        elif pid in updated_roster_ids:
            move_type = "arrival"
        else:
            move_type = "departure"
        rows.append({
            "player_id": pid, "name": src.name, "position": src.position, "pos_group": src.pos_group,
            "is_goalie": src.is_goalie, "move_type": move_type,
            "base_war": round(src.base_war, 4),            # last-season realized value (display)
            "projected_war": round(src.projected_war, 4),  # next-season projected value (display)
            "war_sd": round(src.war_sd, 4), "no_track_record": src.no_track_record,
            "base_slot": base_real[pid].slot if in_base else None,
            "updated_slot": upd_real[pid].slot if in_upd else None,
            "delta_contribution": round(upd_proj - base_proj, 4),
        })
    # Replacement slots are explicit so a vacated slot reads as "filled at replacement", not dropped.
    repl_delta = (n_repl_upd - n_repl_base) * cfg["REPLACEMENT_WAR"]
    if repl_delta != 0:
        rows.append({"player_id": None, "name": None, "position": None, "pos_group": None,
                     "is_goalie": False, "move_type": "replacement_fill", "base_war": 0.0,
                     "projected_war": 0.0, "war_sd": 0.0, "no_track_record": False,
                     "base_slot": None, "updated_slot": None, "delta_contribution": round(repl_delta, 4)})
    return net_delta, rows


def chemistry_adjustment(updated_xgf_share_delta: float | None, cfg: dict = CFG) -> float:
    """Bounded goals/game nudge from the top-units line-fit delta (updated minus base xGF share).

    None (line-fit unavailable for a unit) -> 0.0, never a fabricated chemistry read.
    """
    if updated_xgf_share_delta is None:
        return 0.0
    raw = updated_xgf_share_delta * cfg["CHEMISTRY_XGF_TO_GOALS"]
    cap = cfg["CHEMISTRY_ADJ_CAP"]
    return float(min(cap, max(-cap, raw)))


def forecast_band(updated_lineup: list[PlayerProj], n_moves: int, cfg: dict = CFG) -> float:
    """Honest band in goals/game. Propagates per-slot war_sd in quadrature, then ADDS band for the
    value share from no-track-record players and from goalies, plus a turnover term and a floor.
    The band does NOT include cap, injury, camp battles, coaching, or prospects (model can't see them).
    """
    slot_sd_war = math.sqrt(sum(p.war_sd ** 2 for p in updated_lineup))
    base = slot_sd_war * GPW / GPS                                    # value uncertainty -> goals/game

    total_val = sum(abs(p.projected_war) for p in updated_lineup) or 1.0
    no_track_share = sum(abs(p.projected_war) for p in updated_lineup if p.no_track_record) / total_val
    goalie_share = sum(abs(p.projected_war) for p in updated_lineup if p.is_goalie) / total_val

    band = (base
            + cfg["BAND_NO_TRACK_W"] * no_track_share
            + cfg["BAND_GOALIE_W"] * goalie_share
            + cfg["BAND_TURNOVER_W"] * n_moves)
    return float(max(cfg["BAND_FLOOR"], band))


def inflate_arrival_bands(updated_lineup: list[PlayerProj], base_roster_ids: set, cfg: dict = CFG) -> None:
    """Tier 1 — widen the band for each ARRIVAL (a real player in the updated lineup who was NOT on the
    base roster), in place. A just-acquired player's projection still reflects his OLD-team usage/role
    until he plays for the new club; that uncertainty belongs in the BAND, not in a biased-down point
    estimate. We add ARRIVAL_TRANSLATION_SD in quadrature, so the central projection is untouched and
    the wider sd flows into both his per-player UI band and the team forecast_band. Holdovers (on the
    base roster) and replacement fills are left alone. No-op when the config term is zero.
    """
    add = cfg["ARRIVAL_TRANSLATION_SD"]
    if add <= 0:
        return
    for p in updated_lineup:
        if p.player_id is not None and not p.replacement and p.player_id not in base_roster_ids:
            p.war_sd = math.sqrt(p.war_sd ** 2 + add ** 2)


def is_negligible(net_delta_war: float, n_moves: int, cfg: dict = CFG) -> bool:
    """Quiet-offseason guard: TRUE only when the team has made NO logged lineup move at all (zero
    arrivals or departures among the projected lineups) — next season's roster isn't published yet, or
    the summer has genuinely been silent. The verdict then says so ('check back') instead of a confident
    near-zero forecast. A team that HAS made a move — even a single small one, like losing a third-line
    center — is NOT negligible: its ledger and verdict must show that move, not hide it behind a quiet
    state. (Previously also fired for 1-2 small-net moves, which hid real departures.)"""
    return n_moves == 0


def project_rating(base_rating: float, net_delta_war: float, chemistry_adj: float,
                   cfg: dict = CFG) -> float:
    """Projected next-season rating = base play-driving rating + net lineup-WAR delta on the goals
    scale (GOALS_PER_WIN / games) + a bounded chemistry nudge. Same goals scale as the team rating.
    """
    return base_rating + (net_delta_war * cfg["GOALS_PER_WIN"] / cfg["GAMES_PER_SEASON"]) + chemistry_adj


def rating_to_points(rating: float, cfg: dict = CFG) -> int:
    """Map a team rating (expected goal differential per game, league mean ~0) to projected 82-game
    standings points: P = intercept + slope*rating, clamped to [0, ceiling]. THE single rating->points
    mapping — the forecast row, the serving backfill, and validation all call this (no duplicated fit).
    Constants live in config.ROSTER_FORECAST["FORECAST_POINTS"]; documented in power-ratings.md.
    """
    fp = cfg["FORECAST_POINTS"]
    return int(min(max(round(fp["intercept"] + fp["slope"] * rating), 0), fp["ceiling"]))


def absolute_rating(total_lineup_war: float, chemistry_adj: float = 0.0, cfg: dict = CFG) -> float:
    """ABSOLUTE team rating (goals/game) from a roster's OWN projected value — the Roster Builder's
    one piece the offseason tool lacks. project_rating anchors on a team's MEASURED rating and only
    adds the move-delta; an arbitrary user-built roster has no trustworthy base, so this derives the
    rating from the total iced-lineup WAR directly:

        rating_abs = (total_lineup_war - LEAGUE_AVG_LINEUP_WAR) * WAR_TO_RATING + chemistry_adj

    LEAGUE_AVG_LINEUP_WAR centers an average roster at ~0 (league-average points); WAR_TO_RATING is the
    empirically-calibrated, COMPRESSED WAR->rating slope (NOT the move-scale 6/82 — see config and
    models_ml/calibrate_roster_builder.py). Same goals scale as the measured rating and project_rating,
    so rating_to_points() maps it the same way. This is a forward PROJECTION (carry the band), not a
    measured rating — the value system reconciles with measured ratings, but the season-ahead estimate
    is uncertain (corr ~0.44); the tool is delta-led for that reason.
    """
    return ((total_lineup_war - cfg["LEAGUE_AVG_LINEUP_WAR"]) * cfg["WAR_TO_RATING"]) + chemistry_adj


def forecast_team(base_players: list[PlayerProj], updated_players: list[PlayerProj],
                  base_rating: float, base_components: dict, n_moves: int | None = None,
                  xgf_share_delta: float | None = None, cfg: dict = CFG) -> dict:
    """Assemble one team's forecast from its two projected rosters. Pure: callers supply already
    projected PlayerProj lists (base_war + projected_war filled), the base rating + components, and
    the line-fit xGF share delta. Returns the roster_forecast row payload + ledger.

    n_moves (turnover) is LINEUP-RELEVANT: it is derived from the ledger (arrivals + departures among
    the projected lineups), NOT the symmetric difference of full-season rosters — a season's worth of
    call-ups and injury fills are not offseason moves and must not inflate the band. A caller-supplied
    n_moves is ignored in favor of the ledger count (kept in the signature for back-compat).
    """
    fwd_b = [p for p in base_players if p.pos_group == "F"]
    def_b = [p for p in base_players if p.pos_group == "D"]
    g_b = [p for p in base_players if p.pos_group == "G"]
    fwd_u = [p for p in updated_players if p.pos_group == "F"]
    def_u = [p for p in updated_players if p.pos_group == "D"]
    g_u = [p for p in updated_players if p.pos_group == "G"]

    # Both lineups ranked + summed by projected (next-season) value, so the delta is purely the
    # effect of the MOVES (returning players cancel; aging shows in the per-player ledger).
    base_lineup, _ = _full_lineup(fwd_b, def_b, g_b, "projected_war", cfg)
    upd_lineup, _ = _full_lineup(fwd_u, def_u, g_u, "projected_war", cfg)

    # Roster membership sets classify a move as a real join/leave (vs a lineup promotion/demotion).
    base_roster_ids = {p.player_id for p in base_players if p.player_id is not None}
    updated_roster_ids = {p.player_id for p in updated_players if p.player_id is not None}
    # Tier 1: an arrival carries role/translation uncertainty -> widen his BAND (never his projection)
    # BEFORE the ledger + band are built, so it shows in both the per-player band and the team band.
    inflate_arrival_bands(upd_lineup, base_roster_ids, cfg)
    net_delta, ledger = reconcile_ledger(base_lineup, upd_lineup, base_roster_ids, updated_roster_ids, cfg)
    n_moves = sum(1 for m in ledger if m["move_type"] in ("arrival", "departure"))
    chem = chemistry_adjustment(xgf_share_delta, cfg)
    band_g = forecast_band(upd_lineup, n_moves, cfg)
    proj = project_rating(base_rating, net_delta, chem, cfg)
    negligible = is_negligible(net_delta, n_moves, cfg)

    return {
        "base_rating": round(base_rating, 4),
        "projected_rating": round(proj, 4),
        "delta": round(proj - base_rating, 4),
        "net_delta_war": round(net_delta, 4),
        "chemistry_adj": round(chem, 4),
        "band_low": round(proj - band_g, 4),
        "band_high": round(proj + band_g, 4),
        "band_goals": round(band_g, 4),
        # Projected standings points — a validated linear transform of the rating (rating_to_points),
        # carried with its band; points_delta is the offseason move-impact in points (b * rating delta).
        "base_points": rating_to_points(base_rating, cfg),
        "projected_points": rating_to_points(proj, cfg),
        "points_low": rating_to_points(proj - band_g, cfg),
        "points_high": rating_to_points(proj + band_g, cfg),
        "points_delta": round(cfg["FORECAST_POINTS"]["slope"] * (proj - base_rating), 1),
        "n_moves": n_moves,
        "negligible": negligible,
        "base_play_5v5": round(base_components.get("play_5v5", 0.0), 4),
        "base_finishing": round(base_components.get("finishing", 0.0), 4),
        "base_goaltending": round(base_components.get("goaltending", 0.0), 4),
        "base_special_teams": round(base_components.get("special_teams", 0.0), 4),
        "ledger": ledger,
        "updated_lineup": upd_lineup,
        "base_lineup": base_lineup,
    }


def _full_lineup(fwd, dmen, goalies, value_attr, cfg):
    """Build F/D/G slots and concatenate into one lineup; return (slots, total)."""
    fs, ft = build_lineup(fwd, cfg["N_FWD"], value_attr, "F", cfg)
    ds, dt = build_lineup(dmen, cfg["N_DEF"], value_attr, "D", cfg)
    gs, gt = build_lineup(goalies, cfg["N_GOALIE"], value_attr, "G", cfg)
    return fs + ds + gs, ft + dt + gt


# ============================================================================================
# I/O SHELL — BigQuery loads, service calls, table writes, CLI. Not unit-tested (needs BQ);
# the slice is proven with --sample + --dry-run per HANDOFF-1/3.
# ============================================================================================

GAME_TYPE_FILTER = "substr(cast(game_id as string), 5, 2) in ('01','02','03')"


def _run_id() -> str:
    # Timestamp-based; Date.now is fine here (this is the I/O shell, not a resumable journal).
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def latest_completed_season(bq) -> str:
    """The most recent season with a team_ratings row — the base of the live transition."""
    df = bq.query_df(f"SELECT max(season) AS s FROM {bq.models('team_ratings')}")
    return str(df["s"].iloc[0])


def _is_offseason(bq, min_gap_days: int):
    """Are we between seasons? True iff the most recent NHL game is a PLAYOFF game (type 03) AND it
    was at least `min_gap_days` ago — i.e. the Stanley Cup Final is over. This is robust where a
    days-only test is not: an in-season break (4 Nations, All-Star) ends on a REGULAR-season game
    (type 02), and a between-playoff-round gap is shorter than `min_gap_days`. Once the next season's
    games begin (preseason 01 / regular 02), the most recent game is no longer a playoff game, so it
    flips to False. Returns (is_offseason, days_since_last_game)."""
    df = bq.query_df(f"""
        SELECT game_date, SUBSTR(CAST(game_id AS STRING), 5, 2) AS gtype
        FROM {bq.staging('stg_rosters')}
        WHERE game_date IS NOT NULL AND {GAME_TYPE_FILTER}
        ORDER BY game_id DESC LIMIT 1
    """)
    if df.empty or df["game_date"].iloc[0] is None:
        return False, None
    import pandas as pd
    gap = (datetime.now(timezone.utc).date() - pd.Timestamp(df["game_date"].iloc[0]).date()).days
    return (str(df["gtype"].iloc[0]) == "03" and gap >= min_gap_days), gap


def next_season(season: str) -> str:
    start = int(season[:4]) + 1
    return f"{start}-{str(start + 1)[2:]}"


def _season_str(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[2:]}"


def proj_windows(base_season: str, n_back: int) -> dict:
    """The single-season WAR windows feeding the blend: {season_window: years_ago}, years_ago 0 = the
    base season, then back n_back-1 seasons. All END at or before the base season, so the blend is
    leak-free for both the live forward forecast and the 2024-25 backtest."""
    base_y = _season_year(base_season)
    return {_season_str(base_y - k): k for k in range(n_back)}


# ---- loaders (one BigQuery round-trip each; the joins are documented in the methodology doc) ----

def load_team_ratings(bq, season: str) -> dict:
    """team_id -> {rating, play_5v5, finishing, goaltending, special_teams}, the LAST row that season."""
    sql = f"""
    WITH r AS (
        SELECT team_id, total_rating, play_5v5, finishing, goaltending, special_teams,
               ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY game_date DESC) AS rn
        FROM {bq.models('team_ratings')} WHERE season = '{season}'
    )
    SELECT team_id, total_rating, play_5v5, finishing, goaltending, special_teams FROM r WHERE rn = 1
    """
    out = {}
    for _, x in bq.query_df(sql).iterrows():
        out[int(x.team_id)] = {"rating": float(x.total_rating), "play_5v5": float(x.play_5v5),
                               "finishing": float(x.finishing), "goaltending": float(x.goaltending),
                               "special_teams": float(x.special_teams)}
    return out


def load_skater_war_multi(bq, base_season: str, n_back: int) -> dict:
    """player_id -> {seasons, current_war, war_sd, position} from up to n_back single-season WAR
    windows. seasons = [(years_ago, war_total, games)] feeds the shared blended_war_rate; current_war +
    war_sd are the most-recent-season anchors used for the ledger's base value and the band."""
    windows = proj_windows(base_season, n_back)
    inlist = ",".join(f"'{w}'" for w in windows)
    sql = f"""
    SELECT player_id, season_window, position, war, war_sd, games
    FROM {bq.models('player_gar')} WHERE season_window IN ({inlist})
    """
    out: dict = {}
    for _, x in bq.query_df(sql).iterrows():
        k = windows.get(str(x.season_window))
        if k is None or x.war is None:
            continue
        d = out.setdefault(int(x.player_id),
                           {"seasons": [], "current_war": None, "war_sd": None, "position": None,
                            "_recent": None})
        d["seasons"].append((k, float(x.war), float(x.games or 0)))
        sd = float(x.war_sd) if x.war_sd is not None else None
        if k == 0:
            d["current_war"], d["war_sd"], d["position"] = float(x.war), sd, str(x.position)
        if d["_recent"] is None or k < d["_recent"]:
            d["_recent"], d["_recent_war"], d["_recent_sd"], d["_recent_pos"] = (
                k, float(x.war), sd, str(x.position))
    return _finalize_war_multi(out, ("position",))


def load_goalie_war_multi(bq, base_season: str, n_back: int) -> dict:
    """goalie_id -> {seasons, current_war, war_sd} from up to n_back single-season windows (games_played
    as games). Same multi-season blend as skaters, carried through flat (no skater aging curve)."""
    windows = proj_windows(base_season, n_back)
    inlist = ",".join(f"'{w}'" for w in windows)
    sql = f"""
    SELECT goalie_id, season_window, war, war_sd, games_played AS games
    FROM {bq.models('goalie_gar')} WHERE season_window IN ({inlist})
    """
    out: dict = {}
    for _, x in bq.query_df(sql).iterrows():
        k = windows.get(str(x.season_window))
        if k is None or x.war is None:
            continue
        d = out.setdefault(int(x.goalie_id),
                           {"seasons": [], "current_war": None, "war_sd": None, "_recent": None})
        d["seasons"].append((k, float(x.war), float(x.games or 0)))
        sd = float(x.war_sd) if x.war_sd is not None else None
        if k == 0:
            d["current_war"], d["war_sd"] = float(x.war), sd
        if d["_recent"] is None or k < d["_recent"]:
            d["_recent"], d["_recent_war"], d["_recent_sd"], d["_recent_pos"] = (
                k, float(x.war), sd, None)
    return _finalize_war_multi(out, ())


def _finalize_war_multi(out: dict, extra: tuple) -> dict:
    """If a player has no current-season (years_ago 0) row, fall back to his most-recent season for the
    display/band anchors; then drop the bookkeeping `_recent*` keys."""
    for d in out.values():
        if d["current_war"] is None:
            d["current_war"], d["war_sd"] = d["_recent_war"], d["_recent_sd"]
            for k in extra:
                d[k] = d["_recent_pos"]
        for k in ("_recent", "_recent_war", "_recent_sd", "_recent_pos"):
            d.pop(k, None)
    return out


def load_archetypes(bq, season: str) -> dict:
    sql = f"""
    SELECT player_id, primary_archetype, pos_group FROM {bq.models('player_archetypes')}
    WHERE season = '{season}' AND model_version = 'archetypes_v2'
    """
    return {int(x.player_id): {"archetype": x.primary_archetype, "pos_group": str(x.pos_group)}
            for _, x in bq.query_df(sql).iterrows()}


def load_aging(bq) -> dict:
    sql = f"SELECT archetype, age, curve_value FROM {bq.models('aging_curves')}"
    out: dict = {}
    for _, x in bq.query_df(sql).iterrows():
        out.setdefault(str(x.archetype), {})[int(x.age)] = float(x.curve_value)
    return out


def load_ages(bq, season: str) -> dict:
    """player_id -> age at the season start (season start year minus birth year)."""
    start = int(season[:4])
    sql = f"""
    SELECT player_id, EXTRACT(YEAR FROM CAST(birth_date AS DATE)) AS birth_year
    FROM {bq.staging('stg_player_bio')} WHERE birth_date IS NOT NULL
    """
    return {int(x.player_id): start - int(x.birth_year) for _, x in bq.query_df(sql).iterrows()
            if x.birth_year is not None}


def load_player_names(bq) -> dict:
    """player_id -> 'First Last' from the latest game a player dressed (covers base-roster departures
    and updated players resolved via the game fallback, who carry no live-snapshot name)."""
    sql = f"""
    SELECT player_id, name FROM (
        SELECT player_id, first_name || ' ' || last_name AS name,
               ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY game_id DESC) AS rn
        FROM {bq.staging('stg_rosters')} WHERE {GAME_TYPE_FILTER}
    ) WHERE rn = 1
    """
    return {int(x.player_id): x["name"] for _, x in bq.query_df(sql).iterrows() if x["name"]}


def _season_year(season: str) -> int:
    return int(season[:4])


def prior_season(season: str) -> str:
    """'2025-26' -> '2024-25'."""
    y = _season_year(season) - 1
    return f"{y}-{str(y + 1)[2:]}"


def live_roster_season(bq) -> str:
    """The season the live published roster (stg_roster_current) currently represents."""
    df = bq.query_df(f"SELECT max(season) AS s FROM {bq.staging('stg_roster_current')}")
    return str(df["s"].iloc[0])


def robust_roster_membership(bq, season: str, min_games: int, boundary: str = "end") -> dict:
    """A team's robust roster for `season` at a season BOUNDARY.

    This is an OFFSEASON tool, so the comparison is prior-season-END vs next-season-OPENING — only
    moves made between seasons count, never mid-season trades. So:
      boundary='end'  -> a player's team in his LATEST game that season (season-end roster).
      boundary='open' -> a player's team in his EARLIEST game that season (opening-night roster).
    A mid-season trade therefore does NOT move a player off a team's offseason picture: he was on the
    club at the relevant boundary. A player counts if he played >= `min_games` (filters cup-of-coffee
    call-ups). Returns team_id -> [{player_id, position, name}]. The official 21-man snapshot drops
    regulars later sent to the AHL and the raw dressed list adds 1-game call-ups, so we floor by games;
    a player injured almost the whole season is the one remaining blind spot.
    """
    order = "ASC" if boundary == "open" else "DESC"
    sql = f"""
    WITH g AS (
        SELECT player_id, COUNT(*) AS gp,
               ARRAY_AGG(STRUCT(team_id, position_code, first_name, last_name)
                         ORDER BY game_id {order} LIMIT 1)[OFFSET(0)] AS edge
        FROM {bq.staging('stg_rosters')}
        WHERE season = '{season}' AND {GAME_TYPE_FILTER}
        GROUP BY player_id
    )
    SELECT player_id, edge.team_id AS team_id, edge.position_code AS position_code,
           edge.first_name || ' ' || edge.last_name AS name
    FROM g WHERE gp >= {int(min_games)}
    """
    out: dict = {}
    for _, x in bq.query_df(sql).iterrows():
        if x.team_id is None:
            continue
        out.setdefault(int(x.team_id), []).append({"player_id": int(x.player_id),
                                                    "position": str(x.position_code),
                                                    "name": x["name"]})
    return out


def updated_roster_membership(bq) -> dict:
    """Current membership from the LIVE roster ONLY (stg_roster_current).

    We deliberately do NOT use int_player_current_team here: its latest-game FALLBACK (is_live_roster
    = False) keeps anyone whose last NHL game is in the value window on his old team — retired,
    deceased, sent to the minors/Europe — which would show up as a phantom offseason ARRIVAL on a
    club he is no longer on (e.g. a player who last dressed two seasons ago). The live roster is the
    set of players a club has ACTUALLY rostered, which is exactly the "updated roster" the forecast
    diffs against the prior season-end roster. A real trade/signing is on the new club's live roster;
    a departure is on the prior season-end roster but not the live one — both still resolve correctly.
    """
    sql = f"""
    SELECT player_id, team_id, COALESCE(position_code, '') AS position_code,
           COALESCE(full_name, '') AS name
    FROM {bq.staging('stg_roster_current')} WHERE team_id IS NOT NULL
    """
    out: dict = {}
    for _, x in bq.query_df(sql).iterrows():
        # NB: x["name"] is the COLUMN; x.name would be the Series index label (a classic trap).
        out.setdefault(int(x.team_id), []).append({"player_id": int(x.player_id),
                                                    "position": str(x.position_code) or "F",
                                                    "name": x["name"] or None})
    return out


def offseason_updated_membership(bq, base_season: str, min_games: int) -> dict:
    """The CURRENT offseason roster: each player's team is his LIVE published-roster team if he is on
    one, else his `base_season` END team (a fallback so AHL/unsigned holdovers do not falsely depart).

    The live feed reflects offseason signings/trades as they happen even while it is still LABELLED the
    prior season (NHL rolls the season label later), so we read team membership from it directly rather
    than gating on its label. Universe = live-roster players UNION the base-season robust roster, which
    excludes stale fallback-only players (retired/in-Europe) that would otherwise be phantom arrivals.

    PUBLISHED ROSTER IS AUTHORITATIVE: the base-season team is only a fallback for a club that has NO
    current published roster. Once a team's live roster is published (all 32 are, in the offseason), it
    is the complete statement of that club's membership — so a base-season holdover who is absent from
    his old team's published roster has DEPARTED (released/unsigned UFA), not merely "not yet re-listed".
    Keeping him would leave released players (e.g. a bought-out veteran) phantom-rostered all summer and
    crowd real signings out of the projected lineup. He is dropped here; his vacated slot fills at
    replacement. A player still counts as MOVED only when he is actively on a different club's live roster.
    """
    sql = f"""
    WITH base AS (
        SELECT player_id, e.team_id AS team_id, e.position_code AS position_code,
               e.first_name || ' ' || e.last_name AS name FROM (
            SELECT player_id, COUNT(*) AS gp,
                   ARRAY_AGG(STRUCT(team_id, position_code, first_name, last_name)
                             ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS e
            FROM {bq.staging('stg_rosters')}
            WHERE season = '{base_season}' AND {GAME_TYPE_FILTER}
            GROUP BY player_id
        ) WHERE gp >= {int(min_games)}
    ),
    live AS (
        SELECT player_id, team_id, COALESCE(position_code, '') AS position_code,
               COALESCE(full_name, '') AS name
        FROM {bq.staging('stg_roster_current')} WHERE team_id IS NOT NULL
    ),
    teams_with_live AS (SELECT DISTINCT team_id FROM live)
    SELECT player_id,
           COALESCE(l.team_id, b.team_id) AS team_id,
           COALESCE(NULLIF(l.position_code, ''), b.position_code) AS position_code,
           COALESCE(NULLIF(l.name, ''), b.name) AS name
    FROM live l FULL OUTER JOIN base b USING (player_id)
    -- Keep a player iff he is on a live roster, OR his base team has no published roster at all
    -- (early offseason / a team we could not pull). Otherwise he is a real departure and is dropped.
    WHERE l.team_id IS NOT NULL
       OR b.team_id NOT IN (SELECT team_id FROM teams_with_live)
    """
    out: dict = {}
    for _, x in bq.query_df(sql).iterrows():
        if x.team_id is None:
            continue
        out.setdefault(int(x.team_id), []).append({"player_id": int(x.player_id),
                                                    "position": str(x.position_code) or "F",
                                                    "name": x["name"] or None})
    return out


def _pos_group(position: str) -> str:
    if position == "G":
        return "G"
    return "D" if position == "D" else "F"


def make_player_proj(pid, name, position, skater_data, goalie_data, aging, ages,
                     archetypes, project_value: bool, cfg=CFG) -> PlayerProj:
    """Build a PlayerProj. base_war = the player's most-recent realized WAR (display); project_value
    True -> also fill projected_war from the multi-season blend (skater = blended+aged, goalie = blended
    flat). A player with no WAR window at all is no_track_record: replacement level + a deliberately
    wide band, never a fabricated value. skater_data/goalie_data come from the *_war_multi loaders."""
    pg = _pos_group(position)
    is_g = pg == "G"
    sd_fallback = cfg["WAR_SD_FALLBACK"]
    if is_g:
        d = goalie_data.get(pid)
        if not d or not d["seasons"]:
            return PlayerProj(pid, name, position, "G", True, cfg["REPLACEMENT_WAR"],
                              cfg["REPLACEMENT_WAR"], cfg["NO_TRACK_RECORD_WAR_SD"], no_track_record=True)
        proj = project_goalie_war(d["seasons"], cfg) if project_value else 0.0
        return PlayerProj(pid, name, position, "G", True, d["current_war"], proj,
                          d["war_sd"] if d["war_sd"] is not None else sd_fallback, False)
    d = skater_data.get(pid)
    if not d or not d["seasons"]:
        return PlayerProj(pid, name, position, pg, False, cfg["REPLACEMENT_WAR"],
                          cfg["REPLACEMENT_WAR"], cfg["NO_TRACK_RECORD_WAR_SD"], no_track_record=True)
    proj = 0.0
    if project_value:
        arch = (archetypes.get(pid) or {}).get("archetype") or cfg["AGE_CURVE_FALLBACK"][pg]
        curve = aging.get(arch) or aging.get(cfg["AGE_CURVE_FALLBACK"][pg]) or {}
        proj = project_skater_war(d["seasons"], curve, ages.get(pid), cfg)
    return PlayerProj(pid, name, position, pg, False, d["current_war"], proj,
                      d["war_sd"] if d["war_sd"] is not None else sd_fallback, False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Offseason roster forecast (reads only; trains nothing).")
    ap.add_argument("--dry-run", action="store_true", help="compute but do not write; print byte estimate")
    ap.add_argument("--sample", default=None, help="one team abbrev (e.g. TOR) to prove the slice")
    ap.add_argument("--resume", action="store_true", help="skip team+transition rows already present")
    ap.add_argument("--backtest", action="store_true", help="2024-25 -> 2025-26 calibration (rank corr + MAE)")
    ap.add_argument("--full", action="store_true", help="all 32 teams for the live transition")
    args = ap.parse_args()

    import numpy as np
    np.random.seed(CFG["RANDOM_SEED"])
    from models_ml import bq

    run_id = _run_id()
    floor = CFG["MIN_GAMES_ROSTER"]

    # Offseason-only guard for the live write: the upcoming-season forecast only makes sense between
    # seasons, so a daily DAG run is a no-op once the next season's first game is played (the most
    # recent NHL game becomes recent again). --sample/--dry-run/--backtest are exempt (testing).
    writes_live = args.full or not (args.dry_run or args.sample or args.backtest)
    if writes_live:
        is_off, gap = _is_offseason(bq, CFG["OFFSEASON_MIN_GAP_DAYS"])
        if not is_off:
            print(f"Not in the offseason (last NHL game {gap}d ago, not a finished playoff run); the "
                  f"upcoming-season forecast runs only between seasons. Skipping.")
            return

    latest = latest_completed_season(bq)        # latest season with team_ratings + complete games

    # Transition selection (auto-advancing): if the live roster is a season AHEAD of the latest
    # completed games, that is the real upcoming offseason (base = latest completed, updated = live
    # published roster). Otherwise next-season rosters are not published yet, so the meaningful
    # transition is the most recent COMPLETED one (prior -> latest), both sides from the robust
    # game-derived roster so the diff is real moves, not a dressed-vs-published artifact.
    if args.backtest:
        # Calibration on a COMPLETED offseason: 2024-25 season-END -> 2025-26 OPENING night.
        base_season, updated_season = "2024-25", "2025-26"
        base_mem = robust_roster_membership(bq, base_season, floor, "end")
        upd_mem = robust_roster_membership(bq, updated_season, floor, "open")
    else:
        # Forward-looking: the UPCOMING offseason. BASE = latest completed season-END roster; UPDATED
        # = the CURRENT roster from the live published feed, which reflects offseason signings/trades
        # as they happen (even while still labelled the prior season). A player only moves when he is
        # actively on a different club's live roster; AHL/unsigned holdovers keep their base team. The
        # ledger fills in as moves land — and is empty (all teams negligible) only if none have yet.
        base_season = latest                 # latest completed season (e.g. 2025-26)
        updated_season = next_season(base_season)   # the upcoming season (e.g. 2026-27)
        base_mem = robust_roster_membership(bq, base_season, floor, "end")
        upd_mem = offseason_updated_membership(bq, base_season, floor)
    trans = f"{base_season}->{updated_season}"
    print(f"project_roster_forecast {run_id}: transition {trans} (model_version={CFG['MODEL_VERSION']})")

    if args.dry_run:
        _print_byte_estimate(bq, base_season)

    # Value/aging/ratings are keyed to the BASE season — the realized rating the projection starts
    # from, and the multi-season value each player carries into the next season.
    n_back = CFG["PROJ_WINDOWS"]
    window = f"{n_back} single-season windows ending {base_season}"
    ratings = load_team_ratings(bq, base_season)
    skater_data = load_skater_war_multi(bq, base_season, n_back)
    goalie_data = load_goalie_war_multi(bq, base_season, n_back)
    archetypes = load_archetypes(bq, base_season)
    aging = load_aging(bq)
    ages = load_ages(bq, base_season)

    forecasts, move_rows = _run_all(bq, ratings, base_mem, upd_mem, skater_data, goalie_data,
                                    aging, ages, archetypes, trans, run_id, sample=args.sample)
    _rank_and_finalize(forecasts)
    report = _write_report(forecasts, move_rows, trans, run_id, base_season, window, args)
    print(f"report -> {report}")

    if args.dry_run or args.sample:
        print(f"[{'dry-run' if args.dry_run else 'sample'}] {len(forecasts)} forecasts, "
              f"{len(move_rows)} move rows; not written.")
        return
    _write_tables(bq, forecasts, move_rows)


def _projected_players(team_id, mem, skater_data, goalie_data, aging, ages, archetypes, project_value):
    out = []
    for m in mem.get(team_id, []):
        out.append(make_player_proj(m["player_id"], m.get("name"), m["position"], skater_data,
                                    goalie_data, aging, ages, archetypes, project_value))
    return out


def _top_units(lineup):
    """Top two forward trios (F1..F6) and the top defense pair (D1..D2) as player-id lists."""
    fwd = [p.player_id for p in lineup if p.pos_group == "F" and p.player_id][:6]
    dmen = [p.player_id for p in lineup if p.pos_group == "D" and p.player_id][:2]
    units = []
    if len(fwd) >= 3:
        units.append(fwd[:3])
    if len(fwd) >= 6:
        units.append(fwd[3:6])
    if len(dmen) == 2:
        units.append(dmen)
    return units


def _chemistry_delta(base_lineup, upd_lineup, season):
    """Mean top-unit xGF-share for the updated lineup minus the base lineup, via score_line. Returns
    None if line-fit is unavailable for any unit (never a fabricated chemistry read)."""
    from models_ml.score_line import score_line

    def mean_xgf(units):
        vals = []
        for ids in units:
            try:
                r = score_line(ids, season, blend=False)
            except Exception:  # noqa: BLE001
                return None
            v = r.get("projected_xgf_pct")
            if v is None:
                return None
            vals.append(float(v))
        return sum(vals) / len(vals) if vals else None

    b = mean_xgf(_top_units(base_lineup))
    u = mean_xgf(_top_units(upd_lineup))
    if b is None or u is None:
        return None
    return u - b


def _style_note(bq, team_id, upd_lineup, season):
    """One additive style-fit read: does the biggest arrival match the team's identity? Uses
    score_team_fit's style dimension; returns '' if unavailable (never fabricated)."""
    arrivals = [p for p in upd_lineup if p.player_id and not p.replacement]
    if not arrivals:
        return ""
    top = max(arrivals, key=lambda p: p.projected_war)
    try:
        from models_ml.score_team_fit import score_team_fit
        fit = score_team_fit(top.player_id, team_id, season)
        for d in fit.get("dimensions", []):
            if d.get("key") == "style":
                return f"{d.get('value', '')} style fit for {top.name or top.player_id}: {d.get('note', '')}"
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _run_all(bq, ratings, base_mem, upd_mem, skater_data, goalie_data, aging, ages, archetypes,
             trans, run_id, sample=None):
    scored_at = datetime.now(timezone.utc).isoformat()
    names = load_player_names(bq)
    team_ids = sorted(set(base_mem) | set(upd_mem))
    if sample:
        abbr_to_id = _abbrev_to_team_id(bq)
        if sample.upper() in abbr_to_id:
            team_ids = [abbr_to_id[sample.upper()]]
    forecasts, move_rows = [], []
    for tid in team_ids:
        if tid not in ratings:
            continue
        base_players = _projected_players(tid, base_mem, skater_data, goalie_data, aging, ages,
                                          archetypes, project_value=True)
        upd_players = _projected_players(tid, upd_mem, skater_data, goalie_data, aging, ages,
                                         archetypes, project_value=True)
        rc = ratings[tid]
        # n_moves is derived inside forecast_team from the ledger (lineup-relevant turnover), not the
        # full-roster symmetric difference (a season's call-ups are not offseason moves).
        f = forecast_team(base_players, upd_players, rc["rating"], rc,
                          xgf_share_delta=None)  # chemistry filled next (needs the built lineups)
        # The line-fit / style overlays are only meaningful when the roster actually changed. Skip
        # them for a no-move team (e.g. the whole league before next-season rosters are published),
        # which keeps that run fast and avoids pointless score_line/score_team_fit round-trips.
        has_moves = any(m["move_type"] in ("arrival", "departure") for m in f["ledger"])
        if has_moves:
            chem_delta = _chemistry_delta(f["base_lineup"], f["updated_lineup"], trans.split("->")[0])
            f = forecast_team(base_players, upd_players, rc["rating"], rc, xgf_share_delta=chem_delta)
            f["style_note"] = _style_note(bq, tid, f["updated_lineup"], trans.split("->")[0])
        else:
            chem_delta = None
            f["style_note"] = ""
        f.update({"team_id": tid, "transition": trans, "model_version": CFG["MODEL_VERSION"],
                  "scored_at": scored_at, "xgf_share_delta": None if chem_delta is None else round(chem_delta, 4)})
        for mr in f.pop("ledger"):
            if not mr.get("name") and mr.get("player_id"):
                mr["name"] = names.get(mr["player_id"])
            mr.update({"team_id": tid, "transition": trans, "model_version": CFG["MODEL_VERSION"],
                       "scored_at": scored_at})
            move_rows.append(mr)
        f.pop("updated_lineup"); f.pop("base_lineup")
        forecasts.append(f)
    return forecasts, move_rows


def _rank_and_finalize(forecasts):
    """Projected league rank (1 = best by projected_rating). Base rank from base_rating for the
    rank-delta the backtest scores against."""
    for key, dst in (("projected_rating", "projected_rank"), ("base_rating", "base_rank")):
        order = sorted(forecasts, key=lambda f: f[key], reverse=True)
        for i, f in enumerate(order):
            f[dst] = i + 1
    for f in forecasts:
        f["projected_rank_delta"] = f["base_rank"] - f["projected_rank"]  # +ve = projected to climb


def _abbrev_to_team_id(bq):
    df = bq.query_df(f"SELECT DISTINCT team_id, team_abbrev FROM {bq.mart('mart_team_game_stats')} "
                     f"WHERE team_abbrev IS NOT NULL")
    return {str(x.team_abbrev): int(x.team_id) for _, x in df.iterrows()}


def _print_byte_estimate(bq, base_season):
    """Free-tier guard: dry-run byte estimate of the heaviest scan before any full run (HANDOFF-2)."""
    from google.cloud import bigquery
    sql = f"SELECT * FROM {bq.staging('stg_rosters')} WHERE season = '{base_season}' AND {GAME_TYPE_FILTER}"
    job = bq.client().query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    print(f"[dry-run] heaviest scan (stg_rosters/{base_season}) ~ {job.total_bytes_processed / 1e9:.2f} GB")


def _write_report(forecasts, move_rows, trans, run_id, base_season, window, args):
    d = Path(__file__).parent / "artifacts" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"project_roster_forecast_{run_id}.md"
    risers = sorted(forecasts, key=lambda f: f.get("projected_rank_delta", 0), reverse=True)[:5]
    lines = [f"# project_roster_forecast {run_id}", "",
             f"- transition: `{trans}`  |  base season `{base_season}`  |  value window `{window}`",
             f"- mode: {'backtest' if args.backtest else 'sample ' + args.sample if args.sample else 'full'}",
             f"- teams forecast: {len(forecasts)}  |  move-ledger rows: {len(move_rows)}",
             f"- model_version: `{CFG['MODEL_VERSION']}`  seed: {CFG['RANDOM_SEED']}", "",
             "## Biggest projected risers (rank delta)", ""]
    for f in risers:
        lines.append(f"- team {f['team_id']}: {f['base_rating']:+.2f} -> {f['projected_rating']:+.2f} "
                     f"(band {f['band_low']:+.2f}..{f['band_high']:+.2f}), "
                     f"rank {f.get('base_rank','?')} -> {f.get('projected_rank','?')}, "
                     f"{f['n_moves']} moves{' [negligible]' if f['negligible'] else ''}")
    if args.backtest:
        lines += ["", "## Backtest calibration", "",
                  "Rank correlation + MAE vs actual 2025-26 power-rating rank delta are computed by "
                  "`models_ml/validate_roster_forecast.py` (see methodology doc)."]
    lines += ["", "## Limitations", "",
              "Band excludes cap, injury, training-camp job battles, coaching change, and prospect "
              "uncertainty — the model cannot see them. Membership != performance: a just-arrived "
              "player's value reflects old-team usage until he plays."]
    path.write_text("\n".join(lines))
    return path


def _write_tables(bq, forecasts, move_rows):
    import pandas as pd
    fdf = pd.DataFrame([{k: v for k, v in f.items()} for f in forecasts])
    mdf = pd.DataFrame(move_rows)
    bq.write_df(fdf, "roster_forecast", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["transition", "team_id"])
    bq.write_df(mdf, "roster_moves", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["transition", "team_id"])
    print(f"wrote {len(fdf)} -> nhl_models.roster_forecast, {len(mdf)} -> nhl_models.roster_moves")


if __name__ == "__main__":
    main()
