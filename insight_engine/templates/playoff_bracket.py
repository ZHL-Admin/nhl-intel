"""
Playoff bracket predictor — pure, deterministic, no I/O, NO future data.

The caller passes a leakage-free, end-of-REGULAR-SEASON snapshot per team: the power rating (net
goals/game), the standings points (for seeding / home ice), and the identity-fingerprint percentiles
(for the style matchup). Nothing here reads BigQuery or any playoff result.

Modeling (all on the rating's native net-goals/game scale, so nothing is fit at request time):
  • single game — each team's expected goals = league average ± half the matchup margin, where
    margin = rating difference + home-ice + a capped style modifier; P(win) from the Skellam
    (Poisson-difference) distribution, ties resolved in OT with a small edge to the better team.
  • series — fold the single-game home/road probs into the 2-2-1-1-1 best-of-7 format.
  • bracket — rolled up two ways: a deterministic favorite tree, and a Monte-Carlo championship
    distribution (the favorite does not win every round, so the odds differ from the tree).

The base strength is a PLAYOFF-ADJUSTED rating: the power-rating components re-weighted for the
playoffs (5v5 + goaltending up, finishing + special teams down), validated on actual playoff series
(models_ml/build_playoff_weights.py). This beats the regular-season composite out-of-sample.

Modifiers are LEARNED and shrunk to what validates out-of-sample (no hand-set weights):
  • recent form — trajectory_15d, validated on actual playoff series (models_ml/analyze_series_model);
    surging teams regress, so a positive trajectory marks the margin DOWN. 0 if it doesn't validate.
  • style — matchup fingerprints (models_ml/train_style_effect); came back null, so it's 0 and only
    the matchup.clash "why" text remains.
Each series prob carries a 90% confidence band propagated from the two teams' rating standard errors.
Ratings drive the prediction.
"""
from __future__ import annotations

import json
import math
import os
import random
from functools import lru_cache

from scipy.stats import skellam

from .matchup import clash

HOME_ICE = 0.18          # net goals/game home-ice advantage (well-established ~0.2)
OT_EDGE_K = 2.0          # logistic slope giving the better team its overtime edge

# Learned, validated style weights (models_ml/train_style_effect.py). If style does not beat
# rating-only out-of-sample they are all ~0, so style contributes nothing to the numbers and stays
# only as the 'why' text. Reloaded from the artifact, so re-training updates the bracket.
_ART_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                         "models_ml", "artifacts", "style_coeffs.json")


_FORM_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                          "models_ml", "artifacts", "series_model.json")


def _load(path: str) -> dict:
    try:
        with open(os.path.abspath(path)) as f:
            return json.load(f)
    except Exception:
        return {}


_STYLE = _load(_ART_PATH)
# Recent-form (trajectory_15d) effect, learned + validated on actual playoff series. The weight is
# NEGATIVE: a team that surged into the playoffs (high trajectory) tends to regress, so its margin
# is marked down. Zero if recent form didn't validate out-of-sample.
_FORM = _load(_FORM_PATH)
# Playoff-specific component re-weighting (models_ml/build_playoff_weights.py): the composite rating
# weights its components for the REGULAR season; the playoffs reward 5v5 + goaltending more and
# finishing + special teams less. These validated multipliers (mean 1, so all-1 ⇒ the composite)
# re-weight the components into a playoff-adjusted rating used for the prediction margin.
_PW_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                        "models_ml", "artifacts", "playoff_weights.json")
_PWEIGHTS = _load(_PW_PATH)
# Higher seed's venue in the 2-2-1-1-1 best-of-7 (True = home).
_VENUE = (True, True, False, False, True, False, True)


def playoff_rating(team: dict) -> float:
    """Playoff-adjusted rating = scale · Σ multiplierₖ · componentₖ. The scale calibrates the
    re-weighted margin back to actual playoff-series outcomes through the Skellam→bo7 model (the
    re-weighting widens the rating spread, which would otherwise make series probs over-confident).
    Falls back to the composite total rating when components or weights are unavailable."""
    comps = team.get("components")
    mult = _PWEIGHTS.get("multipliers")
    if not comps or not mult:
        return float(team.get("rating", 0.0))
    scale = float(_PWEIGHTS.get("scale", 1.0))
    return scale * sum(float(mult.get(k, 1.0)) * float(comps.get(k, 0.0)) for k in mult)


def _p(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.5


def _game_p(margin_high: float, g_avg: float) -> float:
    """P(higher seed wins one game). margin_high = its expected goal margin (rating + venue + style)."""
    mu_h = max(0.05, g_avg + margin_high / 2)
    mu_l = max(0.05, g_avg - margin_high / 2)
    p_reg = 1.0 - float(skellam.cdf(0, mu_h, mu_l))   # P(goal diff >= 1)
    p_tie = float(skellam.pmf(0, mu_h, mu_l))         # regulation tie -> overtime
    p_ot = 1.0 / (1.0 + math.exp(-OT_EDGE_K * margin_high))
    return p_reg + p_tie * p_ot


def _bo7(p_home: float, p_road: float) -> float:
    """P(higher seed wins the series) given its per-game home/road win probs (2-2-1-1-1)."""
    @lru_cache(None)
    def rec(i: int, hw: int, lw: int) -> float:
        if hw == 4:
            return 1.0
        if lw == 4:
            return 0.0
        p = p_home if _VENUE[i] else p_road
        return p * rec(i + 1, hw + 1, lw) + (1.0 - p) * rec(i + 1, hw, lw + 1)
    out = rec(0, 0, 0)
    rec.cache_clear()
    return out


def style_edge(fp_high: dict, fp_low: dict) -> float:
    """Learned net-goals/game style nudge for the higher seed (Σ wₖ·interactionₖ), clamped.

    Weights are fit empirically and shrunk to what validates out-of-sample; when style adds no
    signal they are 0 and this returns 0. interactionₖ = (high_for-½)(low_against-½) −
    (low_for-½)(high_against-½): the higher seed generating the chance types the lower seed is
    softest at suppressing (percentiles are 0-1).
    """
    pairs = _STYLE.get("for_against")
    weights = _STYLE.get("weights_goals")
    if not pairs or not weights:
        return 0.0
    total = 0.0
    for (ffor, fagainst), w in zip(pairs, weights):
        total += w * ((_p(fp_high.get(ffor)) - 0.5) * (_p(fp_low.get(fagainst)) - 0.5)
                      - (_p(fp_low.get(ffor)) - 0.5) * (_p(fp_high.get(fagainst)) - 0.5))
    clamp = _STYLE.get("clamp_goals", 0.6)
    return max(-clamp, min(clamp, total))


def _higher(a: str, b: str, teams: dict) -> tuple[str, str]:
    """(higher seed, lower seed) by standings points, tie-broken by rating."""
    ta, tb = teams[a], teams[b]
    return (a, b) if (ta["points"], ta["rating"]) >= (tb["points"], tb["rating"]) else (b, a)


def recent_form_edge(traj_high, traj_low) -> float:
    """Net goals/game recent-form nudge for the higher seed from trajectory_15d. Validated negative:
    surging teams regress in the playoffs. Clamped. The weight is taken from the playoff-weights
    artifact (re-fit jointly on the re-weighted base); falls back to the composite-base series_model."""
    w = _PWEIGHTS.get("recent_form_weight_goals")
    clamp = _PWEIGHTS.get("recent_form_clamp_goals", 0.4)
    if w is None:                                  # fall back to the composite-base fit
        if not _FORM.get("recent_form_validated"):
            return 0.0
        w = _FORM.get("recent_form_weight_goals", 0.0)
        clamp = _FORM.get("recent_form_clamp_goals", 0.4)
    raw = float(w) * (_p0(traj_high) - _p0(traj_low))
    return max(-clamp, min(clamp, raw))


def _p0(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _series_p(margin: float, g_avg: float) -> float:
    """P(higher seed wins the series) from a net-goals margin via single-game Skellam + bo7."""
    return _bo7(_game_p(margin + HOME_ICE, g_avg), _game_p(margin - HOME_ICE, g_avg))


def series(a: str, b: str, teams: dict, g_avg: float) -> dict:
    """Full series prediction for matchup a vs b. Returns the higher seed, P(higher wins) with a
    90% confidence band propagated from the rating standard errors, the style + recent-form
    modifiers, and the style 'why' sentences (higher seed framed as home)."""
    hi, lo = _higher(a, b, teams)
    th, tl = teams[hi], teams[lo]
    se = style_edge(th["fp"], tl["fp"])
    rf = recent_form_edge(th.get("trajectory"), tl.get("trajectory"))
    # Prediction margin uses the PLAYOFF-adjusted rating (re-weighted components), not the composite.
    margin = playoff_rating(th) - playoff_rating(tl) + se + rf
    p = _series_p(margin, g_avg)

    # Confidence band: propagate the two teams' rating standard errors (±1.645σ ≈ 90%).
    sd = math.sqrt((_p0(th.get("rating_se")) ** 2) + (_p0(tl.get("rating_se")) ** 2))
    p_lo = _series_p(margin - 1.645 * sd, g_avg) if sd > 0 else p
    p_hi = _series_p(margin + 1.645 * sd, g_avg) if sd > 0 else p

    reasons = clash(th["fp"], tl["fp"], hi, lo)
    return {"high": hi, "low": lo, "p_high": p, "p_high_lo": p_lo, "p_high_hi": p_hi,
            "style": se, "recent_form": rf, "reasons": reasons}


# Within this window of a coin flip, the deterministic tree pick goes to the HIGHER SEED (home ice)
# rather than a razor-thin rating edge — the rating gap there is well inside the noise. This only
# affects who advances in the displayed tree; the Monte-Carlo odds use the true probability.
TIE_EPS = 0.02


def predicted_tree(teams: dict, r1_pairs: list[tuple[str, str]], g_avg: float) -> list[list[dict]]:
    """Deterministic bracket: the favorite advances each round (near-ties go to the higher seed)."""
    rounds: list[list[dict]] = []
    cur = list(r1_pairs)
    while cur:
        rnd, winners = [], []
        for a, b in cur:
            s = series(a, b, teams, g_avg)
            s["coin_flip"] = abs(s["p_high"] - 0.5) < TIE_EPS
            # higher seed wins when ahead OR within the coin-flip window (home-ice tiebreak)
            s["winner"] = s["high"] if s["p_high"] >= 0.5 - TIE_EPS else s["low"]
            rnd.append(s)
            winners.append(s["winner"])
        rounds.append(rnd)
        if len(winners) == 1:
            break
        cur = [(winners[i], winners[i + 1]) for i in range(0, len(winners), 2)]
    return rounds


def simulate(teams: dict, r1_pairs: list[tuple[str, str]], g_avg: float,
             n: int = 20000, seed: int = 0) -> dict:
    """Monte-Carlo the whole bracket n times. Returns per-team {r2, cf, final, cup} probabilities."""
    rng = random.Random(seed)
    cache: dict = {}

    def p_a_beats_b(a: str, b: str) -> float:
        key = frozenset((a, b))
        if key not in cache:
            cache[key] = series(a, b, teams, g_avg)
        s = cache[key]
        return s["p_high"] if a == s["high"] else 1.0 - s["p_high"]

    stages = ("r2", "cf", "final", "cup")
    reach = {t: {k: 0 for k in stages} for t in teams}
    for _ in range(n):
        cur = list(r1_pairs)
        si = 0
        while cur:
            winners = [a if rng.random() < p_a_beats_b(a, b) else b for a, b in cur]
            stage = stages[min(si, len(stages) - 1)]
            for w in winners:
                reach[w][stage] += 1
            if len(winners) == 1:
                break
            cur = [(winners[i], winners[i + 1]) for i in range(0, len(winners), 2)]
            si += 1
    return {t: {k: reach[t][k] / n for k in stages} for t in teams}
