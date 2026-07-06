"""
Player Verdict — deterministic evidence payload (Workstream B).

Assembles a per-player, two-horizon JSON payload that Gemini narrates into the composed scouting
read (it narrates only; it never computes). The payload carries:

  identity   durable, multi-year (anchored on player_impact's 3-year window + archetype stability);
             confidence scales with career sample (shrinkage: short sample -> hedged language).
  current    this season (overall value, top traits / watch-outs from the radar, finishing vs
             expected, consistency, deployment).
  deltas     how current diverges from the multi-year baseline (powers "previously a strength,
             down this year").

ZONE USAGE GATE: zone deployment enters the payload ONLY as the NHL Edge OZ-start percentile,
labeled "NHL Edge" (official, all situations, neutral included) — never the team faceoff proxy and
never a 50%-threshold lean. Live hot/cold and PDO are intentionally excluded.

Pure data assembly; no LLM here. Missing blocks are omitted (never fabricated).

Run (inspect a payload):  python -m models_ml.build_verdict_payload --player 8478402 --season 2025-26
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Optional

import numpy as np
import pandas as pd

from models_ml import bq, config

_NAME_FAMILY = {config.ARCHETYPE_NAMES_V2[k]: config.ARCHETYPE_FAMILY_V2[k] for k in config.ARCHETYPE_NAMES_V2}
_NAME_DESCRIPTOR = {config.ARCHETYPE_NAMES_V2[k]: config.ARCHETYPE_DESCRIPTORS_V2[k]
                    for k in config.ARCHETYPE_NAMES_V2}
# off/def are even-strength impact (more characterizing of identity); pp/pk are special teams.
_IMPACT_TRAITS = [
    ("off_impact", "EV offensive impact", "ev_offensive_impact", True),
    ("def_impact", "EV defensive impact", "ev_defensive_impact", True),
    ("pp_impact", "Power-play impact", "pp_impact", False),
    ("pk_impact", "Penalty-kill impact", "pk_impact", False),
]


def _style_phrase(cluster_label: Optional[str]) -> Optional[str]:
    """The archetype cluster as a STYLE descriptor (how a player plays), with any tier/quality tail
    stripped — the cluster name is never the identity noun (a style cluster can carry a tier word like
    'secondary' that it does not actually mean). Keep only the concrete style clause."""
    if not cluster_label:
        return None
    desc = _NAME_DESCRIPTOR.get(cluster_label)
    if not desc:
        return None
    # descriptors are "concrete style; summary noun-phrase" — drop the trailing summary clause
    return desc.split(";")[0].strip() or None
_SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def _season_id(season: str) -> int:
    y = int(season[:4])
    return y * 10000 + (y + 1)


def _round(v: Any, n: int = 1) -> Optional[float]:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), n)


def _assessment_row(player_id: int, season: str) -> Optional[dict]:
    """The player's ASSESSMENT for the current season — the identity noun anchors on tier_label (D15).
    Replaces the retired percentile-to-noun value tier. dependence_* are carried when the columns exist
    (spec 7.3; currently absent -> None). Returns None if the player has no assessment row this season."""
    p = bq.project()
    df = bq.query_df(f"""
        select tier, tier_label, tier_confidence, tier_prob_within_one, confidence_label,
               stability_grade, qualified, disqualify_reason, last_played_season,
               dependence_index, dependence_n_partners
        from `{p}.nhl_models.player_assessment`
        where player_id = {player_id} and season_window = '{season}' limit 1
    """)
    if df.empty:
        return None
    r = df.iloc[0]

    def v(k):
        val = r.get(k)
        return None if val is None or (isinstance(val, float) and np.isnan(val)) else val

    return {
        "tier": v("tier"), "tier_label": v("tier_label"),
        "tier_confidence": _round(float(v("tier_confidence")), 3) if v("tier_confidence") is not None else None,
        "tier_prob_within_one": _round(float(v("tier_prob_within_one")), 3) if v("tier_prob_within_one") is not None else None,
        "confidence_label": v("confidence_label"), "stability_grade": v("stability_grade"),
        "qualified": (bool(v("qualified")) if v("qualified") is not None else None),
        "disqualify_reason": v("disqualify_reason"), "last_played_season": v("last_played_season"),
        "dependence_index": _round(float(v("dependence_index")), 4) if v("dependence_index") is not None else None,
        "dependence_n_partners": int(v("dependence_n_partners")) if v("dependence_n_partners") is not None else None,
        "within_one_range_copy": config.ASSESSMENT["WITHIN_ONE_RANGE_COPY"],
    }


# --- league frame for durable-trait percentiles (3yr impact within position), pulled once ----------
_FRAME: dict[str, pd.DataFrame] = {}


def _impact_frame(window: str) -> pd.DataFrame:
    if window in _FRAME:
        return _FRAME[window]
    p = bq.project()
    df = bq.query_df(f"""
        select i.player_id, g.position,
               i.off_impact, i.def_impact, i.pp_impact, i.pk_impact
        from `{p}.nhl_models.player_impact` i
        join (select player_id, any_value(position) as position
              from `{p}.nhl_models.player_gar` where season_window = '{window}' group by player_id) g
          using (player_id)
        where i.season_window = '{window}'
    """)
    if not df.empty:
        df["pos_group"] = np.where(df["position"] == "D", "D", "F")
        for col, _, _, _ in _IMPACT_TRAITS:
            df[f"{col}_pctile"] = df.groupby("pos_group")[col].rank(pct=True)
    _FRAME[window] = df
    return df


def _identity(player_id: int, season: str) -> dict:
    p = bq.project()
    window = config.VERDICT["IDENTITY_WINDOW"]

    # archetype now + family stability over the last 3 single seasons
    arch = bq.query_df(f"""
        select season, primary_archetype
        from `{p}.nhl_models.player_archetypes`
        where player_id = {player_id} and season in ({", ".join(f"'{s}'" for s in _SINGLE_SEASONS)})
        order by season desc
    """)
    primary = None
    family = None
    season_sensitive = False
    if not arch.empty:
        # DURABLE label, not the latest season: the modal archetype across the identity window
        # (last 3 seasons). Ties break toward the more recent. season_sensitive flags label-level
        # instability (the earlier bug only checked family, so a within-family flip read as stable).
        last3 = list(arch.head(3)["primary_archetype"])
        counts: dict[str, int] = {}
        for a in last3:
            if a:
                counts[a] = counts.get(a, 0) + 1
        if counts:
            top = max(counts.values())
            # most-recent among the labels tied for the top count (last3 is newest-first)
            primary = next(a for a in last3 if a and counts.get(a) == top)
            family = _NAME_FAMILY.get(primary)
            # sensitive only when no label holds a strict majority of the window (or family flips),
            # so a single off-season blip doesn't read as an identity that has shifted.
            n = len([a for a in last3 if a])
            fams = {_NAME_FAMILY.get(a) for a in last3 if a}
            season_sensitive = (top * 2 <= n) or (len(fams) > 1)

    # durable traits: 3yr impact percentiles within position. BAND, not a hard top-N: keep every dim
    # within DURABLE_BAND of the top dim (>= DURABLE_FLOOR), so a spread of mid-high traits is described
    # as a spread and a characterizing trait is not dropped by a one-point edge. EV impact (off/def)
    # gets a small ordering bonus so the lead trait characterizes rather than merely ranks.
    fr = _impact_frame(window)
    durable = []
    if not fr.empty and (fr["player_id"] == player_id).any():
        row = fr.loc[fr["player_id"] == player_id].iloc[0]
        cand = []
        for col, label, key, is_ev in _IMPACT_TRAITS:
            pc = row.get(f"{col}_pctile")
            if pc is not None and not np.isnan(pc):
                cand.append({"spoke": key, "label": label, "pctile_3yr": int(round(pc * 100)),
                             "_ev": is_ev})
        if cand:
            anchor = max(c["pctile_3yr"] for c in cand)
            cutoff = max(anchor - config.VERDICT["DURABLE_BAND"], config.VERDICT["DURABLE_FLOOR"])
            kept = [c for c in cand if c["pctile_3yr"] >= cutoff]
            bonus = config.VERDICT["DURABLE_EV_BONUS"]
            kept.sort(key=lambda d: -(d["pctile_3yr"] + (bonus if d["_ev"] else 0)))
            durable = [{k: v for k, v in c.items() if k != "_ev"}
                       for c in kept[:config.VERDICT["DURABLE_MAX"]]]

    # career sample (single-season GAR rows) -> confidence
    car = bq.query_df(f"""
        select count(distinct season_window) as seasons, sum(games) as games
        from `{p}.nhl_models.player_gar`
        where player_id = {player_id} and season_window in ({", ".join(f"'{s}'" for s in _SINGLE_SEASONS)})
    """)
    seasons = int(car.iloc[0]["seasons"]) if not car.empty and car.iloc[0]["seasons"] else 0
    games = int(car.iloc[0]["games"]) if not car.empty and car.iloc[0]["games"] else 0
    conf = ("high" if games >= config.VERDICT["CONF_HIGH_GAMES"]
            else "medium" if games >= config.VERDICT["CONF_MED_GAMES"] else "low")

    out: dict[str, Any] = {
        "window": window, "career_seasons": seasons, "career_games": games, "confidence": conf,
        "durable_traits": durable,
    }
    if primary:
        # The cluster is STYLE, not tier. `style` (how the player plays) and `family` feed the read;
        # `cluster_label` is kept only for traceability and must NOT be used as the identity noun (a
        # style cluster can carry a tier word like "secondary" it does not actually mean).
        out["archetype"] = {
            "family": family, "style": _style_phrase(primary), "season_sensitive": season_sensitive,
            "cluster_label": primary,
        }
    return out


def _display_name(player_id: int, season: str) -> Optional[str]:
    p = bq.project()
    df = bq.query_df(f"""
        select first_name, last_name
        from `{p}.nhl_mart.mart_player_game_stats`
        where player_id = {player_id} and season = '{season}'
        order by game_id desc limit 1
    """)
    if df.empty:
        df = bq.query_df(f"""
            select first_name, last_name
            from `{p}.nhl_mart.mart_player_game_stats`
            where player_id = {player_id} order by game_id desc limit 1
        """)
    if df.empty:
        return None
    fn, ln = df.iloc[0]["first_name"], df.iloc[0]["last_name"]
    name = " ".join(x for x in [fn, ln] if x)
    return name or None


def _radar_spokes(player_id: int, season: str) -> list[dict]:
    p = bq.project()
    df = bq.query_df(f"""
        select spokes from `{p}.nhl_models.player_radar`
        where player_id = {player_id} and season = '{season}' limit 1
    """)
    if df.empty or not df.iloc[0]["spokes"]:
        return []
    spokes = json.loads(df.iloc[0]["spokes"])
    return [s for s in spokes if s.get("percentile") is not None]


def _current(player_id: int, season: str) -> dict:
    p = bq.project()
    cur: dict[str, Any] = {}

    # games + all-situations TOI/GP (the real, fixed denominator), NHL games only
    g = bq.query_df(f"""
        select count(distinct game_id) as gp, avg(toi_5v5) as toi
        from `{p}.nhl_mart.mart_player_game_stats`
        where player_id = {player_id} and season = '{season}'
          and substr(cast(game_id as string), 5, 2) in ('02', '03')
    """)
    if not g.empty and g.iloc[0]["gp"]:
        cur["games_played"] = int(g.iloc[0]["gp"])

    # overall value (single-season): production / play-driving / overall percentiles + agreement
    ov = bq.query_df(f"""
        select pos_group, overall_percentile, production_percentile, play_driving_percentile
        from `{p}.nhl_models.player_overall`
        where player_id = {player_id} and season_window = '{season}' limit 1
    """)
    pos_word = "forwards"
    if not ov.empty:
        r = ov.iloc[0]
        pos_word = {"D": "defensemen", "G": "goalies"}.get(r["pos_group"], "forwards")
        prod = _round(r["production_percentile"] and r["production_percentile"] * 100, 0)
        play = _round(r["play_driving_percentile"] and r["play_driving_percentile"] * 100, 0)
        agree = "agree"
        if prod is not None and play is not None:
            gap = prod - play
            agree = ("agree" if abs(gap) < config.VERDICT["AGREE_GAP_PTS"]
                     else "value_over_impact" if gap > 0 else "impact_over_value")
        ov_pctile = _round(r["overall_percentile"] and r["overall_percentile"] * 100, 0)
        cur["overall"] = {
            "percentile": ov_pctile, "pool": pos_word,
            "production_pctile": prod, "play_driving_pctile": play, "agreement": agree,
        }

    # ASSESSMENT (D15): the identity noun anchors on the assessment tier for THIS season — the
    # legacy percentile-to-noun value tier is retired. Carries confidence/range/inactive fields the
    # consistency checker verifies against prose.
    cur["assessment"] = _assessment_row(player_id, season)

    # top traits / watch-outs / style from the current radar
    spokes = _radar_spokes(player_id, season)
    if spokes:
        srt = sorted(spokes, key=lambda s: -s["percentile"])
        cur["top_traits"] = [{"spoke": s["key"], "label": s["label"],
                              "pctile": int(round(s["percentile"])), "honesty": s.get("tag")}
                             for s in srt[:config.VERDICT["TOP_TRAITS_N"]]]
        if len(srt) >= 5:
            cur["watch_outs"] = [{"spoke": s["key"], "label": s["label"],
                                  "pctile": int(round(s["percentile"])), "honesty": s.get("tag")}
                                 for s in srt[-config.VERDICT["WATCH_OUTS_N"]:][::-1]]
        bykey = {s["key"]: int(round(s["percentile"])) for s in spokes}
        rush, cyc = bykey.get("rush_offense"), bykey.get("cycle_forecheck")
        if rush is not None and cyc is not None:
            cur["style"] = {"rush_pctile": rush, "cycle_forecheck_pctile": cyc,
                            "dominant": "rush" if rush >= cyc else "cycle"}
        # low-confidence (noisy) impact spokes carry an sd whisker on the radar
        flags = [{"spoke": s["key"], "low_confidence": True}
                 for s in spokes if s.get("sd") is not None and s["key"] == "ev_def_impact"]
        if flags:
            cur["sample_flags"] = flags

    # finishing vs expected (NHL games), volume-weighted
    fin = bq.query_df(f"""
        select safe_divide(sum(individual_goals), sum(individual_shot_attempts)) as actual,
               safe_divide(sum(ixg), sum(individual_shot_attempts)) as expected
        from `{p}.nhl_mart.mart_player_shooting_luck`
        where player_id = {player_id} and season = '{season}'
          and substr(cast(game_id as string), 5, 2) in ('02', '03')
    """)
    if not fin.empty and fin.iloc[0]["actual"] is not None and fin.iloc[0]["expected"] is not None:
        a, e = float(fin.iloc[0]["actual"]), float(fin.iloc[0]["expected"])
        cur["finishing"] = {
            "actual_sh_pct": round(a, 3), "expected_sh_pct": round(e, 3), "delta": round(a - e, 3),
            "verdict": "below_expected" if a - e < -0.005 else "above_expected" if a - e > 0.005 else "in_line",
        }

    # consistency (single-season)
    con = bq.query_df(f"""
        select consistency_index, good_game_share, no_show_share
        from `{p}.nhl_models.player_consistency`
        where player_id = {player_id} and season_window = '{season}' limit 1
    """)
    if not con.empty and con.iloc[0]["consistency_index"] is not None:
        ci = float(con.iloc[0]["consistency_index"])
        cur["consistency"] = {
            "pctile": int(round(ci * 100)),
            "verdict": "high_floor" if ci >= 0.66 else "low_floor" if ci <= 0.33 else "average_floor",
        }

    # deployment: TOI/GP + PP/PK role (from radar usage spokes) + Edge OZ-start percentile ONLY
    dep: dict[str, Any] = {}
    if not g.empty and g.iloc[0]["toi"]:
        m = float(g.iloc[0]["toi"]); dep["toi_per_gp"] = f"{int(m)}:{round((m - int(m)) * 60):02d}"
    if spokes:
        bykey = {s["key"]: int(round(s["percentile"])) for s in spokes}
        def _role(pc):
            return None if pc is None else "heavy" if pc >= 66 else "some" if pc >= 33 else "light"
        dep["pp_role"] = _role(bykey.get("pp_value"))
        dep["pk_role"] = _role(bykey.get("pk_role"))
    edge = bq.query_df(f"""
        select oz_start_pct, oz_start_pctile, dz_start_pct
        from `{p}.nhl_mart.mart_edge_player_profile`
        where player_id = {player_id} and season_id = {_season_id(season)} and game_type = 2 limit 1
    """)
    if not edge.empty and edge.iloc[0]["oz_start_pctile"] is not None:
        # The ONLY zone signal allowed into the verdict: NHL Edge OZ-start percentile, labeled.
        dep["oz_start_pctile_edge"] = int(round(float(edge.iloc[0]["oz_start_pctile"]) * 100))
        dep["oz_start_pct_edge"] = round(float(edge.iloc[0]["oz_start_pct"]), 3)
        dep["zone_source"] = "NHL Edge"
    if dep:
        cur["deployment"] = dep

    return cur


def _deltas(player_id: int, season: str, current: dict) -> list[dict]:
    """current vs the multi-year baseline. Conservative: only emit where it genuinely diverges."""
    deltas = []
    fin = current.get("finishing")
    if fin and fin.get("verdict") == "below_expected":
        deltas.append({"dimension": "finishing", "vs": "expected", "direction": "down",
                       "note": "finishing below expected this season; goals lag the chances"})
    elif fin and fin.get("verdict") == "above_expected":
        deltas.append({"dimension": "finishing", "vs": "expected", "direction": "up",
                       "note": "finishing above expected this season; may regress"})
    return deltas


def _horizon(player_id: int, current: dict) -> Optional[dict]:
    """Neutral note when the two horizons diverge: current production vs 3yr EV play-driving impact.
    Stated as an observation that the lenses measure different things — NEVER as the model being wrong
    about anyone (we do not assume production is right and impact is wrong, or the reverse)."""
    ov = current.get("overall") or {}
    prod = ov.get("production_pctile")
    if prod is None:
        return None
    fr = _impact_frame(config.VERDICT["IDENTITY_WINDOW"])
    if fr.empty or not (fr["player_id"] == player_id).any():
        return None
    row = fr.loc[fr["player_id"] == player_id].iloc[0]
    evs = [row.get("off_impact_pctile"), row.get("def_impact_pctile")]
    evs = [v for v in evs if v is not None and not np.isnan(v)]
    if not evs:
        return None
    ev_impact = int(round(max(evs) * 100))
    gap = prod - ev_impact
    if abs(gap) < config.VERDICT["HORIZON_GAP_PTS"]:
        return None
    return {
        "production_pctile": int(round(prod)), "impact_3yr_pctile": ev_impact,
        "direction": "production_above_impact" if gap > 0 else "impact_above_production",
        "note": ("current production ({p}th) outruns three-year even-strength play-driving impact "
                 "({i}th); the two lenses measure different things"
                 ).format(p=int(round(prod)), i=ev_impact) if gap > 0 else
                ("three-year even-strength play-driving impact ({i}th) sits above current production "
                 "({p}th); the two lenses measure different things"
                 ).format(p=int(round(prod)), i=ev_impact),
    }


def build_payload(player_id: int, season: str) -> dict:
    is_g = False  # goalie verdicts are a later pass; this builder serves skaters
    payload = {
        "player_id": str(player_id), "season": season, "is_goalie": is_g,
        "display_name": _display_name(player_id, season),
        "identity": _identity(player_id, season),
        "current": _current(player_id, season),
    }
    payload["position"] = (payload["current"].get("overall", {}) or {}).get("pool", "forwards")
    payload["deltas"] = _deltas(player_id, season, payload["current"])
    horizon = _horizon(player_id, payload["current"])
    if horizon:
        payload["horizon"] = horizon
    payload["numbers_used"] = []   # Gemini fills this; the consistency checker verifies it
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", type=int, required=True)
    ap.add_argument("--season", default="2025-26")
    args = ap.parse_args()
    print(json.dumps(build_payload(args.player, args.season), indent=2))


if __name__ == "__main__":
    main()
