"""
Player Fit scoring (rebuilt from first principles).

Fit measures how well a player's profile SERVES a team. Talent never CAPS fit — it FLOORS it:

    match = weighted(need, style, line)        # all in [0, 1]
    floor = FLOOR_CAP * overall_quality_pctile # an elite player always floors at a decent fit;
                                               # a depth player floors near zero
    fit   = floor + (1 - floor) * match        # match drives the upside, UNCAPPED by talent

So a low-value specialist who lands on a real team need can score a high fit (match ~1 regardless of
talent), and an elite player is never rated a poor fit anywhere (the floor holds). Quality is exposed
as its OWN axis beside fit — never folded into match — so "elite player, mediocre fit here" and
"depth player, ideal fit here" both read cleanly.

The three MATCH dimensions:
  1. NEED (the core; it ABSORBS POSITION): how well the player's component-level strengths land on
     the team's component-level weaknesses, BY ROLE (C / W / D / G), benchmarked against the team's
     OWN current depth (nhl_models.team_needs, team_needs_v2). Handedness is a small modifier here.
  2. STYLE: the player's offence-generation orientation vs the team's identity (match, not magnitude).
  3. LINE: complementarity with the unit he'd actually skate with (the line model's PAIRWISE
     contributions — talent-independent), Phase 3.
Goalies take a simplified path (need = team goaltending weakness, same floor; no skater style/line).

The API returns the DECOMPOSITION (need w/ its component-by-role breakdown, style, line) plus quality
as a separate axis — never a lone collapsed grade. See docs/methodology/player-fit.md.

    from models_ml.score_team_fit import score_team_fit
    score_team_fit(player_id=8478402, team_id=24)   # McDavid -> ANA
"""

from __future__ import annotations

import functools
import json
import math

import numpy as np
import pandas as pd

from models_ml import bq, config
from models_ml.compute_team_needs import role_of, SKATER_COMPONENTS, COMPONENT_LABEL, ROLE_LABEL
from models_ml.textfmt import ordinal

CFG = config.TRADE_FIT
ARCH_LIST = sorted(set(config.ARCHETYPE_NAMES_V2.values()))

# style dimensions reuse the radar spokes vs the team-identity fingerprint (matched generation axes).
STYLE_PLAYER_KEYS = ("rush_offense", "cycle_forecheck")


# ------------------------------------------------------------------ small helpers
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _grade(fit01: float) -> str:
    for letter, floor in CFG["GRADE_BANDS"]:
        if fit01 >= floor:
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


def _f(v):
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _quality_label(pct: float | None) -> str:
    if pct is None:
        return "unrated"
    if pct >= 0.90:
        return "elite"
    if pct >= 0.75:
        return "high-end"
    if pct >= 0.55:
        return "solid middle-six/top-four"
    if pct >= 0.35:
        return "depth"
    return "below-replacement"


def _latest_season(p: str) -> str:
    return bq.query_df(f"select max(season) as s from `{p}.nhl_models.team_needs`").iloc[0]["s"]


def _player_name(p: str, player_id: int) -> str | None:
    df = bq.query_df(f"""select any_value(first_name||' '||last_name) nm
        from `{p}.nhl_staging.stg_rosters` where player_id={int(player_id)}""")
    return df.iloc[0]["nm"] if not df.empty else None


def _abbrev_map(p: str, season: str) -> dict:
    df = bq.query_df(f"""select team_id, any_value(team_abbrev) a
        from `{p}.nhl_mart.mart_team_game_stats` where season='{season}' group by 1""")
    return dict(zip(df["team_id"].astype(int), df["a"]))


# ------------------------------------------------------------------ talent projection (quality floor)
# The talent that floors fit is a forward PROJECTION, not last season's result (so a contract-year /
# one-off spike doesn't inflate the floor). Derived the way the trade talent axis projects: recency-
# weight the last ~3 seasons of WAR (also by games = sample), regress the weighted level toward
# replacement (0 WAR) by sample size AND volatility, then age it forward one season on the player's
# aging curve. A young breakout has little history to dilute and ages UP (tempered little); an older
# spike is diluted by prior seasons and aged DOWN (tempered more). All inputs are serving tables.

def _recent_seasons(season: str, n: int = 3) -> list[str]:
    y = int(season[:4])
    return [f"{yy}-{str(yy + 1)[2:]}" for yy in range(y, y - n, -1)]   # newest -> oldest


@functools.lru_cache(maxsize=2)
def _aging_curves(p: str) -> dict:
    df = bq.query_df(f"select archetype, age, curve_value from `{p}.nhl_models.aging_curves`")
    out: dict = {}
    for arch, g in df.groupby("archetype"):
        out[arch] = dict(zip(g["age"].astype(int), pd.to_numeric(g["curve_value"]).astype("float64")))
    return out


def _aging_ratio(curve: dict | None, base_age: int, target_age: int) -> float:
    """curve(target)/curve(base), snapped to the nearest covered age; flat (1.0) if absent."""
    if not curve:
        return 1.0
    ages = sorted(curve)
    nearest = lambda a: min(ages, key=lambda x: abs(x - a))
    b, t = curve[nearest(base_age)], curve[nearest(target_age)]
    return float(t / b) if b > 0 else 1.0


def _age_at(birth, season: str):
    if birth is None or pd.isna(birth):
        return None
    return int((pd.Timestamp(int(season[:4]), 10, 1) - pd.Timestamp(birth)).days // 365.25)


def _project_war(g: pd.DataFrame, rw: dict, cfg: dict, ratio: float) -> dict:
    """Project one player's WAR from his (up-to-3-season) GAR rows: recency+games weighted level,
    regressed toward 0 by sample size and volatility, then aged by `ratio`. Returns proj/last/sd."""
    g = g.dropna(subset=["war"])
    if g.empty:
        return {}
    w = g["season_window"].map(rw).fillna(0.0).to_numpy()
    games = g["games"].fillna(0.0).to_numpy().clip(min=0.0)
    wars = g["war"].to_numpy(dtype="float64")
    gw = w * games
    if gw.sum() <= 0:                       # games missing -> recency-only weights
        gw = w
    if gw.sum() <= 0:
        return {}
    weighted = float(np.dot(wars, gw) / gw.sum())
    n_eff = float(np.dot(w, games))         # recency-weighted games = effective sample
    vol = float(np.std(wars)) if len(wars) >= 2 else 0.0
    cv = vol / (abs(weighted) + 0.5)
    k_eff = cfg["REGRESS_GAMES_K"] * (1.0 + cfg["VOL_INFLATE"] * cv)
    reliability = n_eff / (n_eff + k_eff) if (n_eff + k_eff) > 0 else 0.0
    proj = weighted * reliability * ratio   # regress toward replacement, then age forward
    newest = g["season_window"].map(rw).idxmax()
    last_war = float(g.loc[newest, "war"])
    sd_w = g["war_sd"].fillna(g["war_sd"].mean()).to_numpy(dtype="float64")
    base_sd = float(np.dot(np.nan_to_num(sd_w), gw) / gw.sum())
    sd = max(cfg["BAND_SD_FLOOR"], base_sd)
    if last_war - proj >= cfg["SPIKE_NOTE_GAP_WAR"]:      # widen the band on a one-off spike
        sd += cfg["SPIKE_BAND_INFLATE"] * (last_war - proj)
    return {"proj_war": proj, "last_war": last_war, "proj_war_sd": sd}


@functools.lru_cache(maxsize=4)
def _skater_projection(p: str, season: str) -> dict:
    """Projected WAR + within-position percentile for every skater (the fit quality FLOOR input)."""
    cfg = config.PLAYER_FIT_PROJECTION
    seasons = _recent_seasons(season)
    rw = {s: cfg["RECENCY_WEIGHTS"][i] for i, s in enumerate(seasons)}
    qs = ", ".join(f"'{s}'" for s in seasons)
    gar = bq.query_df(f"""select player_id, season_window, position, war, war_sd, games
        from `{p}.nhl_models.player_gar`
        where season_window in ({qs}) and position in ('C','L','R','D')""")
    if gar.empty:
        return {}
    for c in ("war", "war_sd", "games"):
        gar[c] = pd.to_numeric(gar[c], errors="coerce")
    bio = bq.query_df(f"select player_id, birth_date from `{p}.nhl_staging.stg_player_bio`")
    bio_age = {int(r.player_id): _age_at(r.birth_date, season) for r in bio.itertuples()}
    arch = bq.query_df(f"""select player_id, primary_archetype from `{p}.nhl_models.player_archetypes`
        where season='{season}'""")
    arch_by = {int(r.player_id): r.primary_archetype for r in arch.itertuples()}
    curves = _aging_curves(p)

    rows = []
    for pid, g in gar.groupby("player_id"):
        pid = int(pid)
        pos = g.sort_values("games", ascending=False).iloc[0]["position"]
        pg = "D" if pos == "D" else "F"
        age = bio_age.get(pid) or cfg["AGE_DEFAULT"]
        curve = curves.get(arch_by.get(pid)) or curves.get("All Defensemen" if pg == "D" else "All Forwards")
        ratio = _aging_ratio(curve, age, age + 1)
        proj = _project_war(g.set_index("season_window", drop=False), rw, cfg, ratio)
        if not proj:
            continue
        rows.append({"player_id": pid, "pg": pg, "age": age, **proj})
    df = pd.DataFrame(rows)
    if df.empty:
        return {}
    df["pctile"] = df.groupby("pg")["proj_war"].rank(pct=True)
    return {int(r.player_id): {"proj_war": float(r.proj_war), "proj_war_sd": float(r.proj_war_sd),
                               "last_war": float(r.last_war), "pctile": float(r.pctile),
                               "pos_group": r.pg, "age": int(r.age)} for r in df.itertuples()}


@functools.lru_cache(maxsize=4)
def _goalie_projection(p: str, season: str) -> dict:
    """Projected WAR + within-goalie percentile for every goalie (no aging — goalie curves are flat)."""
    cfg = config.PLAYER_FIT_PROJECTION
    seasons = _recent_seasons(season)
    rw = {s: cfg["RECENCY_WEIGHTS"][i] for i, s in enumerate(seasons)}
    qs = ", ".join(f"'{s}'" for s in seasons)
    gar = bq.query_df(f"""select goalie_id as player_id, season_window, war, war_sd,
        games_played as games from `{p}.nhl_models.goalie_gar` where season_window in ({qs})""")
    if gar.empty:
        return {}
    for c in ("war", "war_sd", "games"):
        gar[c] = pd.to_numeric(gar[c], errors="coerce")
    rows = []
    for pid, g in gar.groupby("player_id"):
        proj = _project_war(g.set_index("season_window", drop=False), rw, cfg, 1.0)   # flat aging
        if not proj:
            continue
        rows.append({"player_id": int(pid), **proj})
    df = pd.DataFrame(rows)
    if df.empty:
        return {}
    df["pctile"] = df["proj_war"].rank(pct=True)
    return {int(r.player_id): {"proj_war": float(r.proj_war), "proj_war_sd": float(r.proj_war_sd),
                               "last_war": float(r.last_war), "pctile": float(r.pctile),
                               "pos_group": "goalie", "age": None} for r in df.itertuples()}


# ------------------------------------------------------------------ player profile
def _player_profile(p: str, player_id: int, season: str) -> dict:
    """Position/role, per-component within-role percentiles (skater strengths), overall quality
    percentile (the floor + the separate quality axis), style spokes, and the archetype mix (display).
    Goalies get a simplified profile (goalie overall percentile; no skater components/style)."""
    pid = int(player_id)
    bio = bq.query_df(f"""select position, shoots from `{p}.nhl_staging.stg_player_bio`
        where player_id={pid} limit 1""")
    position = bio.iloc[0]["position"] if not bio.empty and bio.iloc[0]["position"] else None
    shoots = bio.iloc[0]["shoots"] if not bio.empty else None

    # composite carries position_code too — use it as a fallback so role is robust to missing bio.
    # NOTE: `position` is a reserved word in DuckDB (the serving backend), so it is never used as an
    # output alias here — only as an (accepted) column reference.
    comp_pos = bq.query_df(f"""select any_value(position) as pos
        from `{p}.nhl_models.player_composite` where player_id={pid} and season_window='{season}'""")
    if (not position) and (not comp_pos.empty) and comp_pos.iloc[0]["pos"]:
        position = comp_pos.iloc[0]["pos"]
    role = role_of(position)

    if role == "G":
        return _goalie_profile(p, pid, season, position, shoots)

    # per-component percentile WITHIN ROLE (the player's strength by component)
    pct = bq.query_df(f"""
        with base as (
          select player_id,
            case when position='C' then 'C' when position in ('L','R','LW','RW') then 'W'
                 when position='D' then 'D' else position end as role,
            ev_offense, ev_defense, pp, pk, finishing
          from `{p}.nhl_models.player_composite` where season_window='{season}'),
        r as (
          select player_id, role,
            percent_rank() over (partition by role order by ev_offense) as ev_offense,
            percent_rank() over (partition by role order by ev_defense) as ev_defense,
            percent_rank() over (partition by role order by pp) as pp,
            percent_rank() over (partition by role order by pk) as pk,
            percent_rank() over (partition by role order by finishing) as finishing
          from base)
        select {', '.join(SKATER_COMPONENTS)} from r where player_id={pid} limit 1""")
    comp_pct = {c: (_f(pct.iloc[0][c]) if not pct.empty else None) for c in SKATER_COMPONENTS}

    # overall quality percentile (within position group) -> floor + separate axis
    qual = _skater_quality(p, pid, season)

    # archetype mix (display only)
    arch = bq.query_df(f"""select archetypes, primary_archetype
        from `{p}.nhl_models.player_archetypes` where player_id={pid} and season='{season}'""")
    mix, primary = [], None
    if not arch.empty and isinstance(arch.iloc[0]["archetypes"], str):
        for it in json.loads(arch.iloc[0]["archetypes"]):
            mix.append({"archetype": it["archetype"], "weight": round(float(it["weight"]), 3)})
        primary = arch.iloc[0]["primary_archetype"]

    # style spokes (rush / cycle-forecheck percentiles) from the radar
    radar = bq.query_df(f"""select spokes from `{p}.nhl_models.player_radar`
        where player_id={pid} and season='{season}' limit 1""")
    style = {}
    if not radar.empty and isinstance(radar.iloc[0]["spokes"], str):
        sp = {s["key"]: s.get("percentile") for s in json.loads(radar.iloc[0]["spokes"])}
        style = {k: (_f(sp[k]) if sp.get(k) is not None else None) for k in STYLE_PLAYER_KEYS}

    if comp_pct["ev_offense"] is None and qual["percentile"] is None:
        raise ValueError(f"no {season} skater profile for player {pid}")

    return {"is_goalie": False, "position": position, "role": role, "shoots": shoots,
            "comp_pct": comp_pct, "quality": qual, "style": style, "mix": mix, "primary": primary}


def _quality_from_projection(proj: dict | None, pos_group: str) -> dict:
    """Quality = the PROJECTED talent (the floor input + the separate quality axis). projected WAR,
    its within-position percentile, the band, and last season's WAR (for the honest spike note)."""
    if proj is None:
        return {"percentile": None, "war": None, "war_sd": None, "last_war": None,
                "pos_group": pos_group}
    return {"percentile": proj["pctile"], "war": proj["proj_war"], "war_sd": proj["proj_war_sd"],
            "last_war": proj["last_war"], "pos_group": pos_group}


def _skater_quality(p: str, pid: int, season: str) -> dict:
    """Projected talent for the skater (drives the floor + the separate quality axis)."""
    return _quality_from_projection(_skater_projection(p, season).get(int(pid)), "skater")


def _goalie_profile(p: str, pid: int, season: str, position, shoots) -> dict:
    """Goalies: projected goaltending talent (no skater components). Strength = the same projected
    percentile that feeds the floor, so the need overlap and the floor use one consistent number."""
    proj = _goalie_projection(p, season).get(int(pid))
    if proj is None:
        raise ValueError(f"no {season} goalie projection for player {pid}")
    quality = _quality_from_projection(proj, "goalie")
    return {"is_goalie": True, "position": "G", "role": "G", "shoots": shoots,
            "comp_pct": {"goaltending": proj["pctile"]}, "mix": [], "primary": None, "style": {},
            "quality": quality}


# ------------------------------------------------------------------ team context
def _role_needs(p: str, team_id: int, season: str, role: str) -> dict:
    """team_needs rows for this team at the player's role: {component: {need, label, strength}}."""
    df = bq.query_df(f"""select component, label, need, team_strength, league_pctile
        from `{p}.nhl_models.team_needs`
        where team_id={int(team_id)} and season='{season}' and role='{role}'""")
    out = {}
    for r in df.itertuples():
        out[r.component] = {"need": _f(r.need) or 0.0, "label": r.label,
                            "league_pctile": _f(r.league_pctile)}
    return out


def _team_handedness(p: str, season: str) -> dict:
    """Per (team, pos_group): TOI-weighted L/R 5v5 share — a small handedness modifier inside need."""
    from models_ml import duck
    if duck.serving_active():
        df = bq.query_df(f"""select team_id, pos_group, l_toi, r_toi
            from `{p}.nhl_models.team_handedness` where season='{season}'""")
        return {(int(r.team_id), r.pos_group): {"L": float(r.l_toi or 0.0), "R": float(r.r_toi or 0.0)}
                for r in df.itertuples()}
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


def _team_identity(p: str, season: str, team_id: int) -> dict:
    df = bq.query_df(f"""
        select rush_share_for_pctile,
               (forecheck_share_for_pctile + cycle_share_for_pctile)/2 as forecheck_cycle_for_pctile
        from `{p}.nhl_mart.mart_team_identity`
        where season='{season}' and window_kind='season' and team_id={int(team_id)} limit 1""")
    if df.empty:
        return {}
    return {"rush_share_for_pctile": _f(df.iloc[0]["rush_share_for_pctile"]),
            "forecheck_cycle_for_pctile": _f(df.iloc[0]["forecheck_cycle_for_pctile"])}


# team's current top unit (trio for F, pair for D) over its last 10 games, members
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
select any_value(members) members, sum(dur)/60.0 minutes
from unit where n={n}
group by (select string_agg(cast(m as string),'-' order by m) from unnest(members) m)
order by minutes desc limit 1
"""


def _line_complement(p: str, player_id: int, team_id: int, season: str, role: str) -> dict | None:
    """Swap the player into the team's current top unit for his role, project with the line model, and
    measure COMPLEMENTARITY = the sum of the model's PAIRWISE feature contributions (arch overlap,
    shot-loc variety, handedness, pace spread, tilt). Talent-independent (member-level contributions,
    which carry individual quality, are excluded), so line measures fit, not the player's level."""
    from models_ml.score_line import score_line
    from models_ml import duck
    line_type = "F3" if role in ("C", "W") else "D2"
    if duck.serving_active():
        df = bq.query_df(f"""select line_key from `{p}.nhl_models.team_current_lines`
            where team_id={int(team_id)} and season='{season}' and line_type='{line_type}' and rnk=1""")
        if df.empty:
            return None
        members = [int(x) for x in str(df.iloc[0]["line_key"]).split("-")]
    else:
        pos = "'C','L','R'" if line_type == "F3" else "'D'"
        n = 3 if line_type == "F3" else 2
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
    pair_keys = ("pair_arch_cos", "pair_shotloc_dist", "hand_balance", "burst_spread", "oz_tilt_mean")
    contribs = new.get("contribs", {}) or {}
    complement = sum(float(v) for k, v in contribs.items() if k in pair_keys)
    # partners = the EXISTING linemates he'd play with (exclude the incoming player himself)
    partner_names = [m["name"] for m in new["members"] if int(m["player_id"]) != int(player_id)]
    return {"members": members, "drop": drop,
            "proj_xgf": new["projected_xgf_pct"], "cur_xgf": cur["projected_xgf_pct"],
            "grade": new["grade"], "partner_names": partner_names,
            "complement": complement,
            "interval_half": round((new["interval_high"] - new["interval_low"]) / 2, 4)}


# ------------------------------------------------------------------ dimensions
def _need_dimension(prof: dict, role_needs: dict, hand: dict, team_id: int, abbr: str) -> dict:
    """NEED (the core, absorbs position). opp_c = team_need_c * player_strength_c at the player's role;
    need_score blends the single best opportunity (a specialist nailing the biggest hole) with breadth.
    Handedness is a small modifier. Returns the dimension + a component-by-role BREAKDOWN."""
    # components are data-driven from the team's role needs (so D excludes finishing automatically)
    comps = ["goaltending"] if prof["is_goalie"] else [c for c in SKATER_COMPONENTS if c in role_needs]
    low, strong = CFG["LOW_NEED"], CFG["STRONG_NEED"]

    def _role_tag(n: float, s: float) -> str:
        if n < low:
            return "low_need"
        if s >= n:
            return "fills" if n >= strong else "covered"
        return "gap" if n >= strong else "covered"

    breakdown, opps = [], []
    for c in comps:
        need_c = role_needs.get(c, {}).get("need", 0.0)
        str_c = prof["comp_pct"].get(c)
        str_c = 0.0 if str_c is None else float(str_c)
        opp = need_c * str_c
        opps.append(opp)
        breakdown.append({"component": c, "label": COMPONENT_LABEL[c],
                          "team_need": round(need_c, 3), "player_strength": round(str_c, 3),
                          "opportunity": round(opp, 3), "tag": _role_tag(need_c, str_c)})
    breakdown.sort(key=lambda b: b["team_need"], reverse=True)   # FE renders sorted by need desc
    if opps:
        w = CFG["NEED_PRIMARY_W"]
        need_score = w * max(opps) + (1 - w) * (sum(opps) / len(opps))
    else:
        need_score = 0.0

    # small handedness modifier (skaters only): bump if the team is short the player's shot at his pos
    if not prof["is_goalie"] and prof["shoots"] in ("L", "R"):
        pg = "D" if prof["role"] == "D" else "F"
        h = hand.get((int(team_id), pg))
        if h and (h["L"] + h["R"]) > 0:
            share = h[prof["shoots"]] / (h["L"] + h["R"])
            need_score = max(0.0, min(1.0, need_score * (1.0 + (0.5 - share) * CFG["HAND_MOD"])))

    # tangible note: anchor on the INTERSECTION — the component where his strength meets their need
    # (max opportunity = need x strength), NOT the biggest need and biggest strength glued together.
    role_word = ROLE_LABEL[prof["role"]]
    comp_name = lambda b: b["label"].split("· ")[-1].lower()
    addressed = max(breakdown, key=lambda b: b["opportunity"]) if breakdown else None
    top_need = max(breakdown, key=lambda b: b["team_need"]) if breakdown else None
    if addressed and addressed["opportunity"] >= CFG["NEED_OVERLAP_MIN"]:
        note = (f"{abbr} are thin at {role_word} {comp_name(addressed)} and he provides it "
                f"({ordinal(round(addressed['player_strength'] * 100))} pct).")
    elif top_need and top_need["team_need"] >= 0.5:
        note = (f"{abbr}'s biggest {role_word} need is {comp_name(top_need)}, which isn't his "
                f"strength — he doesn't directly address their hole.")
    else:
        note = f"{abbr} have solid {role_word} depth — not a roster hole to fill."
    tone = "positive" if need_score >= 0.45 else "neutral"

    # takeaway: name the biggest filled need and the biggest remaining gap (FE renders, doesn't author)
    fills = [b for b in breakdown if b["tag"] == "fills"]
    gaps = [b for b in breakdown if b["tag"] == "gap"]
    top_fill = max(fills, key=lambda b: b["team_need"]) if fills else None
    top_gap = max(gaps, key=lambda b: b["team_need"]) if gaps else None
    if top_fill and top_gap:
        need_summary = f"Fills {abbr}'s {top_fill['label'].lower()} need; still a gap at {top_gap['label'].lower()}."
    elif top_fill:
        need_summary = f"Fills {abbr}'s {top_fill['label'].lower()} need at {role_word}."
    elif top_gap:
        need_summary = f"Doesn't fill a top {role_word} need — biggest gap at {top_gap['label'].lower()}."
    else:
        need_summary = f"{abbr} have no acute {role_word} needs he addresses."

    return {"key": "need", "label": "Need fit", "level": round(need_score, 3),
            "value": _word(need_score), "note": note, "tone": tone,
            "breakdown": breakdown, "need_summary": need_summary}


def _orient(rush, cyc):
    if rush is None or cyc is None or (rush + cyc) <= 0:
        return None
    return rush / (rush + cyc)


def _style_dimension(prof: dict, ident: dict, abbr: str) -> dict:
    """STYLE: the player's rush-vs-(forecheck/cycle) ORIENTATION (a within-entity ratio) vs the team's
    identity orientation. A match, not a magnitude — does not scale with the player's value."""
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
    # the driver MUST agree with the level word (consistency checker): Strong/Excellent (>=0.62) = a
    # match, Moderate (0.46-0.62) = partial, Slight/Low (<0.46) = mismatch — same cuts as _word().
    if level >= 0.62:
        note = (f"Both play a balanced style — a comfortable stylistic fit." if tw == pw == "balanced"
                else f"Matches {abbr}'s {tw} identity (he generates offense the same way).")
    elif level >= 0.46:
        note = f"{abbr} lean {tw}; he is {pw} — a partial stylistic match."
    else:
        note = f"{abbr} are a {tw} team; he leans more {pw} — a stylistic mismatch."
    tone = "positive" if level >= 0.62 else ("neutral" if level >= 0.46 else "warn")
    return {"key": "style", "label": "Style fit", "level": round(level, 3),
            "value": _word(level), "note": note, "tone": tone}


def _grade_article(grade: str | None) -> str:
    """'an' before a vowel-sound grade (A, F), else 'a' — so we never render 'a A line'."""
    return "an" if grade and grade[0] in "AEFHILMNORSX" else "a"


def _line_dimension(line: dict | None) -> dict:
    """LINE: the projected unit he'd skate on. The BAR scales with the projected line quality (xGF%
    mapped through the line grade band) so it tracks the stated grade; the NOTE explains WHY via the
    talent-independent complementarity signal (does he complement or overlap his linemates)."""
    if not line:
        return {"key": "line", "label": "Line fit", "level": None, "value": "n/a",
                "note": "No current top unit to slot into (insufficient recent 5v5 data).",
                "tone": "neutral", "uncertain": True}
    lo, hi = CFG["LINE_XGF_LO"], CFG["LINE_XGF_HI"]
    level = max(0.0, min(1.0, (line["proj_xgf"] - lo) / (hi - lo)))   # bar tracks the projected grade
    comp = _sigmoid(line["complement"] / CFG["LINE_COMP_SCALE"])      # complementarity = the WHY
    partners = [n for n in line["partner_names"] if n]
    pwith = (" with " + " & ".join(partners[:2])) if partners else ""
    art = _grade_article(line["grade"])
    if comp >= 0.6:
        note = f"Complements the unit{pwith} (varied roles/shot locations); projects {art} {line['grade']} line."
    elif comp <= 0.4:
        note = f"Overlaps the unit{pwith} stylistically; projects {art} {line['grade']} line."
    else:
        note = f"A neutral stylistic fit on the unit{pwith}; projects {art} {line['grade']} line."
    return {"key": "line", "label": "Line fit", "level": round(level, 3),
            "value": _word(level), "note": note, "tone": "positive" if level >= 0.5 else "neutral",
            "uncertain": True, "sd": line.get("interval_half")}


def _quality_axis(prof: dict) -> dict:
    """The SEPARATE quality axis (never folded into match). Reports the PROJECTED talent — recency-
    weighted, regressed, aged — so a contract-year spike doesn't read as a clean elite; the projected
    percentile drives the floor. When last season sits well above the projection, the band is already
    widened (in the projection) and the note says so honestly."""
    q = prof["quality"]
    pct, war, war_sd, last = q["percentile"], q["war"], q["war_sd"], q.get("last_war")
    pos = "goalies" if prof["is_goalie"] else ("defensemen" if prof["role"] == "D" else "forwards")
    label = _quality_label(pct)
    gap = config.PLAYER_FIT_PROJECTION["SPIKE_NOTE_GAP_WAR"]
    if pct is None:
        note = "No multi-season value estimate (too little NHL history to project)."
    else:
        war_txt = (f"{war:+.1f} WAR" + (f" ± {war_sd:.1f}" if war_sd else "")) if war is not None else ""
        note = f"Projects to {ordinal(round(pct * 100))}-percentile value among {pos}" \
               f"{(' (' + war_txt + ')') if war_txt else ''}."
        if last is not None and war is not None and last - war >= gap:
            note += (f" Last season {last:+.1f} WAR — the projection regresses toward his "
                     f"multi-season level and ages it forward.")
    return {"percentile": pct, "war": war, "war_sd": war_sd, "last_war": last,
            "label": label, "note": note}


# ------------------------------------------------------------------ composition
def _match(dims: list[dict]) -> float:
    """Weighted blend of the available match dimensions (need/style/line), renormalised over present."""
    w = CFG["MATCH_WEIGHTS"]
    by = {d["key"]: d for d in dims}
    num = den = 0.0
    for k in ("need", "style", "line"):
        d = by.get(k)
        if d and d.get("level") is not None:
            num += w[k] * d["level"]; den += w[k]
    return (num / den) if den > 0 else 0.0


def _compose(quality_pct: float | None, match: float) -> tuple[float, str]:
    """fit = floor + (1 - floor) * match, where floor = FLOOR_CAP * quality percentile."""
    floor = CFG["FLOOR_CAP"] * (quality_pct if quality_pct is not None else 0.0)
    fit = max(0.0, min(1.0, floor + (1.0 - floor) * match))
    return round(fit, 4), _grade(fit)


def _verdict(name, abbr, grade, quality, dims, is_goalie) -> str:
    """Deterministic verdict: lead with the quality TIER (the floor), then the strongest match driver,
    then the served need. Decomposition is the product; this just narrates it."""
    by = {d["key"]: d for d in dims}
    qtier = quality["label"]
    match_dims = [by[k] for k in ("need", "style", "line") if by.get(k) and by[k].get("level") is not None]
    lead = max(match_dims, key=lambda d: d["level"]) if match_dims else None
    clause = f"{name} is {('an' if qtier and qtier[0] in 'aeiou' else 'a')} {qtier} player"
    if lead and lead["level"] >= 0.6:
        clause += " " + {"need": f"who fills a real {abbr} need",
                         "style": f"whose style suits {abbr}",
                         "line": "who complements the unit he'd join"}[lead["key"]]
    nd = by.get("need")
    if nd and nd["level"] < 0.35 and not (lead and lead["key"] == "need"):
        clause += f", though {abbr} aren't especially short where he helps"
    # Player-specific verdict only. The canonical fit-vs-quality explanation and the "can't see"
    # caveat live ONCE, in the UI footnote — not repeated here.
    return f"{clause}. Fit grades {grade}."


# ------------------------------------------------------------------ main
def score_team_fit(player_id: int, team_id: int, season: str | None = None) -> dict:
    p = bq.project(); season = season or _latest_season(p)
    tid = int(team_id)
    abbr_map = _abbrev_map(p, season)
    abbr = abbr_map.get(tid, f"team {tid}")
    prof = _player_profile(p, player_id, season)
    role_needs = _role_needs(p, tid, season, prof["role"])
    if not role_needs:
        raise ValueError(f"no need profile for team {team_id} at role {prof['role']} in {season}")

    quality = _quality_axis(prof)
    hand = _team_handedness(p, season) if not prof["is_goalie"] else {}
    need = _need_dimension(prof, role_needs, hand, tid, abbr)

    if prof["is_goalie"]:
        dims = [need]                                   # goalies: need only (no skater style/line)
    else:
        ident = _team_identity(p, season, tid)
        line = _line_complement(p, player_id, tid, season, prof["role"])
        dims = [need, _style_dimension(prof, ident, abbr), _line_dimension(line)]

    match = _match(dims)
    fit, grade = _compose(quality["percentile"], match)
    name = _player_name(p, player_id)
    verdict = _verdict(name, abbr, grade, quality, dims, prof["is_goalie"])

    return {
        "player_id": int(player_id), "player_name": name, "team_id": tid, "season": season,
        "role": prof["role"],
        "overall_grade": grade, "overall_score": round(fit * 100, 1),
        "verdict_sentence": verdict,
        "quality": quality,                              # SEPARATE axis — never folded into match
        "dimensions": dims,                              # need (w/ breakdown) + style + line
        "need_breakdown": need["breakdown"],             # sorted by team need desc, each tagged
        "need_summary": need["need_summary"],            # one-line takeaway (FE renders, doesn't author)
        "player_archetypes": prof["mix"],
    }


# ------------------------------------------------------------------ best teams (lightweight)
def best_team_fits(player_id: int, season: str | None = None, top_n: int = 3,
                   exclude_team_id: int | None = None) -> list[dict]:
    """Teams a player fits best — a LIGHTWEIGHT estimate (need + style + floor, no per-team line) so
    all 32 teams rank cheaply. Same floor/match composition; for a fixed player the ordering comes
    from need + style (talent floors everywhere equally)."""
    p = bq.project(); season = season or _latest_season(p)
    prof = _player_profile(p, player_id, season)
    abbr_map = _abbrev_map(p, season)
    quality = _quality_axis(prof)
    hand = _team_handedness(p, season) if not prof["is_goalie"] else {}

    needs_all = bq.query_df(f"""select team_id, component, label, need
        from `{p}.nhl_models.team_needs` where season='{season}' and role='{prof['role']}'""")
    if needs_all.empty:
        return []
    out = []
    for tid, g in needs_all.groupby("team_id"):
        tid = int(tid)
        if exclude_team_id is not None and tid == int(exclude_team_id):
            continue
        abbr = abbr_map.get(tid, f"team {tid}")
        role_needs = {r.component: {"need": _f(r.need) or 0.0, "label": r.label} for r in g.itertuples()}
        need = _need_dimension(prof, role_needs, hand, tid, abbr)
        dims = [need]
        if not prof["is_goalie"]:
            dims.append(_style_dimension(prof, _team_identity(p, season, tid), abbr))
        fit, grade = _compose(quality["percentile"], _match(dims))
        top = max(need["breakdown"], key=lambda b: b["team_need"]) if need["breakdown"] else None
        out.append({"team_id": tid, "fit_score": round(fit * 100, 1), "grade": grade,
                    "reason": need["note"],
                    "top_need_label": top["label"] if top else None,
                    "top_need_gap": round(top["team_need"], 3) if top else None})
    out.sort(key=lambda x: -x["fit_score"])
    return out[:top_n]
