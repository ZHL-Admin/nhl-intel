"""
Trade / free-agency fit scoring (Phase 5.3 rebuild, blueprint 6.4).

Fit is NOT one number. The old tool collapsed it to a single cosine of player-profile vs team-need
(positive gaps only, cosine floored at 0), so a defenseman who addresses a defensive need at a
defense-STRONG team scored ~0 — position was never a term and a surplus team's need vector was
empty exactly where the player was strong. This rebuild measures fit on FIVE separate dimensions:

  1. POSITIONAL FIT (the gate / relevance): does the player's position + handedness + role slot into
     the team? Bounded in [GATE_FLOOR, 1] so a positionally-relevant skater can NEVER score 0.
  2. NEED FIT: how big is the team's statistical gap in the player's areas (team_needs). LOW need =
     "not a statistical gap" — neutral, floored, NEVER negative (a strong team can still add him).
  3. STYLE FIT: does the player's generation style (rush / cycle-forecheck / volume / pace from the
     radar) match the team's identity fingerprint (mart_team_identity)?
  4. LINE FIT: would he improve the line/pair he'd slot into (reuse score_line against the team's
     current top unit for his position)? A model estimate -> carries its interval.
  5. PLAYER QUALITY: his actual level — WAR percentile within position + RAPM impact.

overall = positional_gate * weighted_avg(need, style, line, quality); a letter grade off config
bands. None of these floors at 0 inappropriately, there is no max(0,) clamp, and the headline is
always decomposable into the five dimensions. The verdict is deterministic and explicitly notes the
model can't see injury / cap / roster context. See docs/methodology/trade-fit.md.

    from models_ml.score_team_fit import score_team_fit
    score_team_fit(player_id=8483457, team_id=54)   # Hutson -> VGK
"""

from __future__ import annotations

import json
import math

import numpy as np

from models_ml import bq, config

CFG = config.TRADE_FIT
ARCH_LIST = sorted(set(config.ARCHETYPE_NAMES_V2.values()))
COMPONENTS = ["ev_offense", "ev_defense", "pp", "pk", "finishing"]
COMPONENT_LABEL = {"ev_offense": "even-strength offense", "ev_defense": "even-strength defense",
                   "pp": "the power play", "pk": "the penalty kill", "finishing": "finishing"}
# style dimensions: (player radar spoke key, team-identity fingerprint percentile col, label).
# These are MATCHED generation axes (how the player creates offense vs how the team creates it),
# all comparable shares — deliberately NOT skating-burst-vs-team-pace, which are different axes.
STYLE_DIMS = [
    ("rush_offense", "rush_share_for_pctile", "rush offense"),
    ("cycle_forecheck", "forecheck_cycle_for_pctile", "forecheck/cycle"),
    ("shot_volume", "shot_volume_per60_pctile", "shot volume"),
]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _grade(score01: float) -> str:
    for letter, floor in CFG["GRADE_BANDS"]:
        if score01 >= floor:
            return letter
    return "F"


def _word(level: float | None) -> str:
    if level is None:
        return "n/a"
    if level >= 0.78:
        return "Excellent"
    if level >= 0.62:
        return "Strong"
    if level >= 0.46:
        return "Moderate"
    if level >= 0.30:
        return "Slight"
    return "Low"


def _latest_season(p: str) -> str:
    return bq.query_df(f"select max(season) as s from `{p}.nhl_models.team_needs`").iloc[0]["s"]


# ---------------------------------------------------------------- player profile
def _player_profile(p: str, player_id: int, season: str) -> dict:
    """Archetype mix + composite components + bio (position/handedness) + style spokes + quality."""
    pid = int(player_id)
    arch = bq.query_df(f"""select archetypes, primary_archetype
        from `{p}.nhl_models.player_archetypes` where player_id={pid} and season='{season}'""")
    comp = bq.query_df(f"""select {', '.join(COMPONENTS)}
        from `{p}.nhl_models.player_composite` where player_id={pid} and season_window='{season}'""")
    bio = bq.query_df(f"""select position, shoots from `{p}.nhl_staging.stg_player_bio`
        where player_id={pid} limit 1""")
    radar = bq.query_df(f"""select spokes from `{p}.nhl_models.player_radar`
        where player_id={pid} and season='{season}' limit 1""")
    # quality: WAR + WAR percentile within position group + RAPM impact
    qual = bq.query_df(f"""
        with g as (select player_id, position, war, war_sd, toi_5v5,
                          case when position='D' then 'D' else 'F' end pg
                   from `{p}.nhl_models.player_gar` where season_window='{season}'),
             r as (select *, percent_rank() over (partition by pg order by war) war_pct from g)
        select war, war_sd, war_pct, position from r where player_id={pid} limit 1""")
    impact = bq.query_df(f"""select off_impact, def_impact from `{p}.nhl_models.player_impact`
        where player_id={pid} and season_window='{season}' limit 1""")

    if arch.empty and comp.empty and qual.empty:
        raise ValueError(f"no {season} profile for player {pid}")

    # archetype mix
    p_arch = np.zeros(len(ARCH_LIST)); idx = {a: i for i, a in enumerate(ARCH_LIST)}
    primary, primary_w, mix = None, 0.0, []
    if not arch.empty and isinstance(arch.iloc[0]["archetypes"], str):
        for it in json.loads(arch.iloc[0]["archetypes"]):
            mix.append({"archetype": it["archetype"], "weight": round(float(it["weight"]), 3)})
            if it["archetype"] in idx:
                p_arch[idx[it["archetype"]]] = float(it["weight"])
        primary = arch.iloc[0]["primary_archetype"]
        primary_w = next((m["weight"] for m in mix if m["archetype"] == primary), 0.0)

    p_comp = {c: (float(comp.iloc[0][c]) if not comp.empty and comp.iloc[0][c] is not None else 0.0)
              for c in COMPONENTS}

    # position + handedness (bio falls back to gar position / archetype prefix)
    position = (bio.iloc[0]["position"] if not bio.empty and bio.iloc[0]["position"]
                else (qual.iloc[0]["position"] if not qual.empty else None))
    pos_group = "D" if position == "D" else "F"
    shoots = bio.iloc[0]["shoots"] if not bio.empty else None

    # style spokes (rush / cycle-forecheck / volume percentiles) from the radar
    style = {}
    if not radar.empty and isinstance(radar.iloc[0]["spokes"], str):
        sp = {s["key"]: s.get("percentile") for s in json.loads(radar.iloc[0]["spokes"])}
        style = {k: (float(sp[k]) if sp.get(k) is not None else None)
                 for k in ("rush_offense", "cycle_forecheck", "shot_volume", "burst")}

    quality = {
        "war": float(qual.iloc[0]["war"]) if not qual.empty else None,
        "war_sd": float(qual.iloc[0]["war_sd"]) if not qual.empty and qual.iloc[0]["war_sd"] is not None else None,
        "war_pct": float(qual.iloc[0]["war_pct"]) if not qual.empty and qual.iloc[0]["war_pct"] is not None else None,
        "off_impact": float(impact.iloc[0]["off_impact"]) if not impact.empty else None,
        "def_impact": float(impact.iloc[0]["def_impact"]) if not impact.empty else None,
    }
    return {"p_arch": p_arch, "p_comp": p_comp, "mix": mix, "primary": primary,
            "primary_w": primary_w, "position": position, "pos_group": pos_group,
            "shoots": shoots, "style": style, "quality": quality,
            "top_comp": max(p_comp, key=p_comp.get)}


# ---------------------------------------------------------------- team context
def _team_identity(p: str, season: str) -> dict:
    """Per team: the fingerprint percentiles used for style fit (+ a top-trait label)."""
    df = bq.query_df(f"""
        select team_id, rush_share_for_pctile,
               (forecheck_share_for_pctile + cycle_share_for_pctile)/2 as forecheck_cycle_for_pctile,
               shot_volume_per60_pctile, pace_pctile, oz_time_pct_pctile, shot_quality_pctile
        from `{p}.nhl_mart.mart_team_identity`
        where season='{season}' and window_kind='season'""")
    out = {}
    for r in df.itertuples():
        out[int(r.team_id)] = {
            "rush_share_for_pctile": _f(r.rush_share_for_pctile),
            "forecheck_cycle_for_pctile": _f(r.forecheck_cycle_for_pctile),
            "shot_volume_per60_pctile": _f(r.shot_volume_per60_pctile),
            "pace_pctile": _f(r.pace_pctile), "oz_time_pct_pctile": _f(r.oz_time_pct_pctile),
            "shot_quality_pctile": _f(r.shot_quality_pctile),
        }
    return out


def _team_handedness(p: str, season: str) -> dict:
    """Per team: TOI-weighted handedness share by position group (for the positional gate)."""
    from models_ml import duck

    if duck.serving_active():
        # Read the precomputed table (the int_shift_segments scan ran nightly).
        df = bq.query_df(f"""select team_id, pos_group, l_toi, r_toi
            from `{p}.nhl_models.team_handedness` where season='{season}'""")
        out: dict = {}
        for r in df.itertuples():
            out[(int(r.team_id), r.pos_group)] = {
                "L": float(r.l_toi or 0.0), "R": float(r.r_toi or 0.0)}
        return out

    df = bq.query_df(f"""
        with toi as (
          select s.player_id, s.team_id,
                 sum(if(c.strength_state='5v5', s.segment_duration, 0)) toi5,
                 case when s.position_code='D' then 'D' else 'F' end pg
          from `{p}.nhl_staging.int_shift_segments` s
          join `{p}.nhl_staging.int_segment_context` c using (game_id, segment_index)
          where s.is_goalie=0 and s.season='{season}'
            and substr(cast(s.game_id as string),5,2) in ('02','03')
          group by 1,2,4)
        select t.team_id, t.pg, b.shoots, sum(t.toi5) toi5
        from toi t join `{p}.nhl_staging.stg_player_bio` b using (player_id)
        where b.shoots in ('L','R') group by 1,2,3""")
    out: dict = {}
    for r in df.itertuples():
        out.setdefault((int(r.team_id), r.pg), {"L": 0.0, "R": 0.0})[r.shoots] += float(r.toi5)
    return out


# team's current top unit (trio for F, pair for D) over its last 10 games, members + their war
_TOP_UNIT_SQL = """
with g as (
  select game_id, game_date from `{p}.nhl_staging.stg_boxscores`
  where (home_team_id={team} or away_team_id={team}) and season='{season}'
    and substr(cast(game_id as string),5,2) in ('02','03')
  order by game_date desc limit 10),
seg5 as (
  select s.game_id, s.segment_index, s.player_id, s.position_code, c.segment_duration
  from `{p}.nhl_staging.int_shift_segments` s
  join `{p}.nhl_staging.int_segment_context` c using (game_id, segment_index)
  join g using (game_id)
  where s.team_id={team} and s.is_goalie=0 and c.strength_state='5v5'),
unit as (
  select segment_index, game_id, any_value(segment_duration) dur,
         array_agg(player_id order by player_id) members, count(*) n
  from seg5 where position_code in ({pos}) group by 1,2)
select (select string_agg(cast(m as string),'-' order by m) from unnest(members) m) line_key,
       any_value(members) members, sum(dur)/60.0 minutes
from unit where n={n} group by line_key order by minutes desc limit 1
"""


def _line_fit(p: str, player_id: int, team_id: int, season: str, pos_group: str,
              player_war: float | None) -> dict | None:
    """Swap the player into the team's current top unit for his position; project with score_line."""
    from models_ml.score_line import score_line
    from models_ml import duck
    line_type = "F3" if pos_group == "F" else "D2"
    if duck.serving_active():
        # Read the precomputed top unit (the int_shift_segments scan ran nightly).
        df = bq.query_df(f"""select line_key from `{p}.nhl_models.team_current_lines`
            where team_id={int(team_id)} and season='{season}'
              and line_type='{line_type}' and rnk=1""")
        if df.empty:
            return None
        members = [int(x) for x in str(df.iloc[0]["line_key"]).split("-")]
    else:
        pos = "'C','L','R'" if pos_group == "F" else "'D'"
        n = 3 if pos_group == "F" else 2
        df = bq.query_df(_TOP_UNIT_SQL.format(p=p, team=int(team_id), season=season, pos=pos, n=n))
        if df.empty:
            return None
        members = [int(m) for m in df.iloc[0]["members"]]
    if int(player_id) in members:
        return None  # already on the unit
    # replace the lowest-WAR member with the trade player
    wars = bq.query_df(f"""select player_id, war from `{p}.nhl_models.player_gar`
        where season_window='{season}' and player_id in ({','.join(str(m) for m in members)})""")
    war_by = {int(r.player_id): float(r.war) for r in wars.itertuples()}
    drop = min(members, key=lambda m: war_by.get(m, -99))
    new_unit = [int(player_id) if m == drop else m for m in members]
    try:
        new = score_line(new_unit, season, blend=False)
        cur = score_line(members, season, blend=False)
    except Exception:
        return None
    return {"members": members, "drop": drop, "new_unit": new_unit,
            "proj_xgf": new["projected_xgf_pct"], "cur_xgf": cur["projected_xgf_pct"],
            "grade": new["grade"], "partner_names": [m["name"] for m in new["members"]],
            "interval_half": round((new["interval_high"] - new["interval_low"]) / 2, 4)}


def _f(v):
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- dimensions
def _need_dimension(needs, prof) -> dict:
    """Need level = team's component gap weighted by where the PLAYER provides value, sigmoid-mapped.
    Low (surplus) reads ~0.15 — 'not a statistical gap', never negative."""
    comp_need = {r.key: float(r.gap) for r in needs[needs.need_type == "component"].itertuples()}
    # the player's positive component profile = where he provides value
    pv = {c: max(0.0, prof["p_comp"][c]) for c in COMPONENTS}
    tot = sum(pv.values()) or 1.0
    gap = sum(comp_need.get(c, 0.0) * pv[c] for c in COMPONENTS) / tot
    level = max(CFG["NEED_FLOOR"], _sigmoid(gap / CFG["NEED_GAP_SCALE"]))
    # tangible note anchored on the player's strongest component (where he provides value)
    top_c = max(pv, key=pv.get)
    if gap <= 0.5:
        note = (f"{prof['_team_abbrev']} aren't statistically short at {COMPONENT_LABEL[top_c]} — "
                f"not a gap, but a team can still add here.")
    else:
        note = (f"Addresses {prof['_team_abbrev']}'s {COMPONENT_LABEL[top_c]} gap "
                f"(~{gap:+.0f} goals behind the top teams).")
    return {"key": "need", "label": "Need fit", "level": round(level, 3),
            "value": _word(level), "note": note, "tone": "neutral" if gap <= 0.5 else "positive",
            # raw team gap in the player's area; drives the additive bonus in _combine. NEED only
            # ADDS to the score (never subtracts) — see _need_bonus. (Ignored by the response model.)
            "gap": round(gap, 3)}


def _positional_dimension(p, prof, hand, team_id) -> dict:
    """Gate in [FLOOR,1]: every NHL position is usable; modulate by handedness balance vs the team's
    actual L/R distribution at the position. The note leads on that handedness context — specific to
    THIS player + team — and never emits tautological filler ('a role every team ices'). When no
    handedness signal is available it states the position plainly and stops."""
    pg, shoots = prof["pos_group"], prof["shoots"]
    base = 0.82  # any F or D is positionally usable by any team
    pos_word = {"D": "defenseman", "F": "forward"}[pg]
    hand_word = {"L": "left-shot ", "R": "right-shot "}.get(shoots or "", "")
    abbr = prof["_team_abbrev"]
    # Plain-fact fallback (no editorializing tail) — used when handedness can't be determined.
    note = f"A {hand_word}{pos_word}.".replace("  ", " ")

    h = hand.get((int(team_id), pg))
    if h and shoots in ("L", "R") and (h["L"] + h["R"]) > 0:
        share = h[shoots] / (h["L"] + h["R"])           # team's current share of the player's hand
        # under-supplied handedness (low share) -> bump; over-supplied -> slight trim. ±0.12.
        base += (0.5 - share) * 0.24
        side = "left" if shoots == "L" else "right"
        opp = "right" if shoots == "L" else "left"
        if share <= 0.42:
            note = f"A {hand_word}{pos_word} — {abbr} lean {opp}-shot at the position, so the handedness helps."
        elif share >= 0.62:
            note = f"A {hand_word}{pos_word}, where {abbr} already have {side}-shot depth."
        else:
            note = f"A {hand_word}{pos_word}; {abbr} are balanced at the position."
    level = max(CFG["GATE_FLOOR"], min(1.0, base))
    return {"key": "positional", "label": "Positional fit", "level": round(level, 3),
            "value": _word(level), "note": note, "tone": "positive"}


def _orient(rush, cyc):
    """Rush-vs-(forecheck/cycle) ORIENTATION as a within-entity ratio in [0,1] (1 = all rush). This
    is comparable across a player (percentiles within position) and a team (within league) because
    it's each entity's own balance, not an absolute level — sidestepping the player-vs-team scale
    mismatch."""
    if rush is None or cyc is None or (rush + cyc) <= 0:
        return None
    return rush / (rush + cyc)


def _style_dimension(prof, ident) -> dict:
    """Style level = how well the player's OFFENSE-GENERATION orientation (rush vs forecheck/cycle)
    matches the team's identity orientation. A transition/rush creator into a rush team fits; a rush
    creator into a grind-it-out forecheck/cycle team is a partial mismatch. Balanced teams read
    neutral (~0.5)."""
    abbr = prof.get("_team_abbrev", "the team")
    lean_p = _orient(prof["style"].get("rush_offense"), prof["style"].get("cycle_forecheck"))
    lean_t = _orient(ident.get("rush_share_for_pctile"), ident.get("forecheck_cycle_for_pctile")) if ident else None
    if lean_p is None or lean_t is None:
        return {"key": "style", "label": "Style fit", "level": 0.5, "value": _word(0.5),
                "note": "Limited style signal — treated as neutral.", "tone": "neutral"}
    level = 1.0 - abs(lean_p - lean_t)

    def word(lean):
        return ("rush/transition" if lean >= 0.6 else
                "forecheck-and-cycle" if lean <= 0.4 else "balanced")
    tw, pw = word(lean_t), word(lean_p)
    if level >= 0.72:
        note = (f"Both the player and {abbr} play a balanced style — a comfortable stylistic fit."
                if tw == pw == "balanced" else
                f"Matches {abbr}'s {tw} identity (the player generates offense the same way).")
    elif level <= 0.45:
        note = f"{abbr} are a {tw} team; the player leans more {pw} — a stylistic mismatch."
    else:
        note = f"{abbr} lean {tw}; the player is {pw} — a partial stylistic match."
    tone = "positive" if level >= 0.6 else ("neutral" if level >= 0.45 else "warn")
    return {"key": "style", "label": "Style fit", "level": round(level, 3),
            "value": _word(level), "note": note, "tone": tone}


def _line_dimension(line) -> dict:
    if not line:
        return {"key": "line", "label": "Line fit", "level": None, "value": "n/a",
                "note": "No current top unit to slot into (insufficient recent 5v5 data).",
                "tone": "neutral", "uncertain": True}
    lo, hi = CFG["LINE_XGF_LO"], CFG["LINE_XGF_HI"]
    level = max(0.0, min(1.0, (line["proj_xgf"] - lo) / (hi - lo)))
    delta = line["proj_xgf"] - line["cur_xgf"]
    partners = [n for n in line["partner_names"] if n]
    pwith = (" with " + " & ".join(partners[:2])) if partners else ""
    note = (f"Projects a {line['grade']} pairing/line{pwith}: {line['proj_xgf']*100:.1f}% xGF "
            f"({delta*100:+.1f} vs the current unit).")
    return {"key": "line", "label": "Line fit", "level": round(level, 3),
            "value": f"{line['grade']} · {line['proj_xgf']*100:.0f}%", "note": note,
            "tone": "positive" if delta >= 0 else "neutral", "uncertain": True,
            "sd": line.get("interval_half")}


def _quality_dimension(prof) -> dict:
    q = prof["quality"]
    if q["war_pct"] is None:
        return {"key": "quality", "label": "Player quality", "level": None, "value": "n/a",
                "note": "No value estimate this season.", "tone": "neutral", "uncertain": True}
    level = q["war_pct"]
    pos_noun = "defensemen" if prof["pos_group"] == "D" else "forwards"
    war_txt = f"{q['war']:+.1f} WAR" + (f" ± {q['war_sd']:.1f}" if q["war_sd"] else "")
    note = f"{round(level*100)}th-percentile value among {pos_noun} ({war_txt})."
    return {"key": "quality", "label": "Player quality", "level": round(level, 3),
            "value": f"{round(level*100)}th", "note": note, "tone": "positive", "uncertain": True,
            "sd": round((q["war_sd"] or 0) / 12.0, 3) if q["war_sd"] else None}


# ---------------------------------------------------------------- main
def _abbrev_map(p: str, season: str) -> dict:
    df = bq.query_df(f"""select team_id, any_value(team_abbrev) a
        from `{p}.nhl_mart.mart_team_game_stats` where season='{season}' group by 1""")
    return dict(zip(df["team_id"].astype(int), df["a"]))


def _need_bonus(gap: float | None) -> float:
    """Asymmetric additive NEED bonus in [0, NEED_BONUS_MAX].

    0 for a surplus / no gap (need is neutral, never a penalty); rises monotonically with a real
    team gap in the player's area, up to NEED_BONUS_MAX. Filling a hole is upside ON TOP of the
    player-and-fit base — it can lift a grade but can never rescue a bad player.
    """
    g = gap or 0.0
    return CFG["NEED_BONUS_MAX"] * max(0.0, 2.0 * _sigmoid(g / CFG["NEED_GAP_SCALE"]) - 1.0)


def _combine(dims: list[dict]) -> tuple[float, str]:
    """(positional gate) * weighted_avg(quality, line, style)  +  asymmetric NEED bonus.

    The base is purely about the player and the fit (talent-dominant), gated so a positionally
    relevant skater is never zeroed. NEED is added afterwards and can only HELP (see _need_bonus):
    low need adds nothing, it does NOT drag the average down.
    """
    by = {d["key"]: d for d in dims}
    gate = by["positional"]["level"] or CFG["GATE_FLOOR"]
    w = CFG["WEIGHTS"]; num = den = 0.0
    for k in ("quality", "line", "style"):
        lvl = by[k]["level"]
        if lvl is not None:
            num += w[k] * lvl; den += w[k]
    base = (num / den) if den > 0 else 0.5
    gated_base = gate * base
    bonus = _need_bonus(by["need"].get("gap"))
    score = max(0.0, min(1.0, gated_base + bonus))
    return round(score, 4), _grade(score)


def _verdict(name, team_abbrev, grade, dims) -> str:
    """Deterministic verdict. The grade is driven by the base (quality/line/style); NEED is framed
    as pure upside (mention only when it's a real gap, never as a deduction), and a low base is
    attributed to its real cause — usually the player's value — not to a lack of need."""
    by = {d["key"]: d for d in dims}
    base = sorted([by[k] for k in ("quality", "line", "style") if by.get(k) and by[k]["level"] is not None],
                  key=lambda d: -(d["level"] or 0))
    bits = []
    # lead with the strongest base dimension when it's genuinely a strength
    lead = base[0] if base else None
    if lead and (lead["level"] or 0) >= 0.6:
        bits.append({"style": "fits the team's style",
                     "line": "would upgrade the line he slots into",
                     "quality": "brings real top-end value"}[lead["key"]])
    # name the legitimate drag (now quality, not need) when the player is below average
    q = by.get("quality")
    if q and q["level"] is not None and q["level"] < 0.4:
        bits.append("though he's held back by his below-average value")
    # NEED is upside only: mention a real hole as a positive; otherwise say nothing about need
    nd = by["need"]
    if (nd.get("gap") or 0.0) > 0.5:
        bits.append("and he fills a clear hole at the position")
    body = ", ".join(bits) if bits else "the dimensions are mixed"
    return (f"{name} grades {grade} as a fit for {team_abbrev}: {body}. "
            f"Weigh this against what the model can't see — injuries, departures, cap, and locker room.")


def score_team_fit(player_id: int, team_id: int, season: str | None = None) -> dict:
    p = bq.project(); season = season or _latest_season(p)
    tid = int(team_id)
    needs = bq.query_df(f"""select need_type, key, label, team_value, reference_value, gap
        from `{p}.nhl_models.team_needs` where team_id={tid} and season='{season}'""")
    if needs.empty:
        raise ValueError(f"no need profile for team {team_id} in {season}")
    abbrev = _abbrev_map(p, season)
    prof = _player_profile(p, player_id, season)
    prof["_team_abbrev"] = abbrev.get(tid, f"team {tid}")

    ident = _team_identity(p, season).get(tid, {})
    hand = _team_handedness(p, season)
    line = _line_fit(p, player_id, tid, season, prof["pos_group"], prof["quality"]["war"])

    dims = [
        _positional_dimension(p, prof, hand, tid),
        _need_dimension(needs, prof),
        _style_dimension(prof, ident),
        _line_dimension(line),
        _quality_dimension(prof),
    ]
    score, grade = _combine(dims)
    name = _player_name(p, player_id)
    verdict = _verdict(name, prof["_team_abbrev"], grade, dims)

    # legacy need profile for the UI context (top positive component/archetype gaps)
    def top_needs(nt, n):
        sub = needs[(needs.need_type == nt) & (needs.gap > 0)].sort_values("gap", ascending=False)
        return [dict(key=r.key, label=r.label, gap=round(float(r.gap), 3),
                     team_value=round(float(r.team_value), 3),
                     reference_value=round(float(r.reference_value), 3)) for r in sub.head(n).itertuples()]

    return {
        "player_id": int(player_id), "player_name": name, "team_id": tid, "season": season,
        "overall_grade": grade, "overall_score": round(score * 100, 1),
        "verdict_sentence": verdict, "dimensions": dims,
        "player_archetypes": prof["mix"],
        "need_profile": {"team_id": tid, "season": season,
                         "archetype_needs": top_needs("archetype", 5),
                         "component_needs": top_needs("component", 5)},
    }


def _player_name(p: str, player_id: int) -> str | None:
    df = bq.query_df(f"""select any_value(first_name||' '||last_name) nm
        from `{p}.nhl_staging.stg_rosters` where player_id={int(player_id)}""")
    return df.iloc[0]["nm"] if not df.empty else None


def best_team_fits(player_id: int, season: str | None = None, top_n: int = 3,
                   exclude_team_id: int | None = None) -> list[dict]:
    """Teams a player fits best — a LIGHTWEIGHT estimate (positional gate * need/style/quality, no
    per-team line fit) so all 32 teams rank cheaply. Same no-zero-floor discipline."""
    p = bq.project(); season = season or _latest_season(p)
    prof = _player_profile(p, player_id, season)
    abbrev = _abbrev_map(p, season)
    ident_all = _team_identity(p, season)
    hand = _team_handedness(p, season)
    allneeds = bq.query_df(f"""select team_id, need_type, key, label, team_value, reference_value, gap
        from `{p}.nhl_models.team_needs` where season='{season}'""")
    if allneeds.empty:
        return []
    q = _quality_dimension(prof)
    out = []
    for tid, g in allneeds.groupby("team_id"):
        tid = int(tid)
        if exclude_team_id is not None and tid == int(exclude_team_id):
            continue
        prof["_team_abbrev"] = abbrev.get(tid, f"team {tid}")
        need = _need_dimension(g, prof)
        style = _style_dimension(prof, ident_all.get(tid, {}))
        pos = _positional_dimension(p, prof, hand, tid)
        dims = [pos, need, style, {"key": "line", "label": "Line fit", "level": None},
                {"key": "quality", "label": "Player quality", "level": q["level"]}]
        score, grade = _combine(dims)
        out.append({"team_id": tid, "fit_score": round(score * 100, 1), "grade": grade,
                    "reason": need["note"] if need["level"] >= 0.5 else style["note"],
                    "top_need_label": need_label(g), "top_need_gap": need_gap(g)})
    out.sort(key=lambda x: -x["fit_score"])
    return out[:top_n]


def need_label(g):
    sub = g[(g.need_type == "component") & (g.gap > 0)].sort_values("gap", ascending=False)
    return sub.iloc[0]["label"] if not sub.empty else None


def need_gap(g):
    sub = g[(g.need_type == "component") & (g.gap > 0)].sort_values("gap", ascending=False)
    return round(float(sub.iloc[0]["gap"]), 1) if not sub.empty else None
