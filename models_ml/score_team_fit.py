"""
Trade/free-agency fit scoring service (Phase 5.3, blueprint 6.4).

Scores how well a player addresses a team's needs: the cosine of the player's profile (archetype
mix + composite components) with the team's need vector (the positive gaps from
nhl_models.team_needs), on both the archetype and the component axis. Returns a 0-100 fit score,
deterministic reasons (insight_engine/templates/team_fit.py), and the team's need profile for the
UI. Wrapped by the backend POST /tools/trade-fit.

    from models_ml.score_team_fit import score_team_fit
    score_team_fit(player_id=8478402, team_id=10)
"""

from __future__ import annotations

import json

import numpy as np

from models_ml import bq, config
from insight_engine.templates import team_fit as tmpl

ARCH_LIST = sorted(set(config.ARCHETYPE_NAMES.values()))
COMPONENTS = ["ev_offense", "ev_defense", "pp", "pk", "finishing"]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def _latest_season(p: str) -> str:
    return bq.query_df(f"select max(season) as s from `{p}.nhl_models.team_needs`").iloc[0]["s"]


def score_team_fit(player_id: int, team_id: int, season: str | None = None) -> dict:
    p = bq.project()
    season = season or _latest_season(p)

    needs = bq.query_df(f"""select need_type, key, label, team_value, reference_value, gap
        from `{p}.nhl_models.team_needs`
        where team_id = {int(team_id)} and season = '{season}'""")
    if needs.empty:
        raise ValueError(f"no need profile for team {team_id} in {season}")

    arch_need = {r.key: float(r.gap) for r in needs[needs.need_type == "archetype"].itertuples()}
    comp_need = {r.key: float(r.gap) for r in needs[needs.need_type == "component"].itertuples()}

    arch_row = bq.query_df(f"""select archetypes, primary_archetype
        from `{p}.nhl_models.player_archetypes`
        where player_id = {int(player_id)} and season = '{season}'""")
    comp_row = bq.query_df(f"""select {', '.join(COMPONENTS)}
        from `{p}.nhl_models.player_composite`
        where player_id = {int(player_id)} and season_window = '{season}'""")
    if arch_row.empty and comp_row.empty:
        raise ValueError(f"no {season} profile for player {player_id}")

    # player vectors
    p_arch = np.zeros(len(ARCH_LIST))
    primary, primary_w, mix = None, 0.0, []
    if not arch_row.empty and isinstance(arch_row.iloc[0]["archetypes"], str):
        idx = {a: i for i, a in enumerate(ARCH_LIST)}
        for item in json.loads(arch_row.iloc[0]["archetypes"]):
            mix.append({"archetype": item["archetype"], "weight": round(float(item["weight"]), 3)})
            if item["archetype"] in idx:
                p_arch[idx[item["archetype"]]] = float(item["weight"])
        primary = arch_row.iloc[0]["primary_archetype"]
        primary_w = next((m["weight"] for m in mix if m["archetype"] == primary), 0.0)

    p_comp = {c: (float(comp_row.iloc[0][c]) if not comp_row.empty
                  and comp_row.iloc[0][c] is not None else 0.0) for c in COMPONENTS}
    top_comp = max(p_comp, key=p_comp.get)

    # need vectors (positive gaps only)
    n_arch = np.array([max(0.0, arch_need.get(a, 0.0)) for a in ARCH_LIST])
    n_comp = np.array([max(0.0, comp_need.get(c, 0.0)) for c in COMPONENTS])
    pc_vec = np.array([max(0.0, p_comp[c]) for c in COMPONENTS])

    arch_fit = _cosine(p_arch, n_arch)
    comp_fit = _cosine(pc_vec, n_comp)
    fit_score = round(100.0 * (0.5 * arch_fit + 0.5 * comp_fit), 1)

    reasons = tmpl.reasons(
        player_primary_arch=primary, player_arch_weight=primary_w,
        team_arch_needs=arch_need, player_top_component=top_comp,
        player_top_component_value=p_comp[top_comp], team_component_needs=comp_need)

    # need profile for the UI: top archetype + component needs (positive gaps, descending)
    def top_needs(nt, n):
        sub = needs[(needs.need_type == nt) & (needs.gap > 0)].sort_values("gap", ascending=False)
        return [dict(key=r.key, label=r.label, gap=round(float(r.gap), 3),
                     team_value=round(float(r.team_value), 3),
                     reference_value=round(float(r.reference_value), 3))
                for r in sub.head(n).itertuples()]

    return {
        "player_id": int(player_id), "team_id": int(team_id), "season": season,
        "fit_score": fit_score, "reasons": reasons, "player_archetypes": mix,
        "need_profile": {
            "team_id": int(team_id), "season": season,
            "archetype_needs": top_needs("archetype", 5),
            "component_needs": top_needs("component", 5),
        },
    }
