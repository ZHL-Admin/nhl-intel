"""
Line-fit explanation templates (Phase 5.1, blueprint 6.2 step 5).

Deterministic, data-driven sentences explaining a line-fit projection. No LLM. The scorer
(models_ml/score_line.py) passes the model's per-feature contributions (LightGBM pred_contrib,
in xGF% space) and the line's grade; this module composes a grade sentence, 2-3 reasons drawn
from the strongest positive contributions, and at most one risk from the strongest negative
contribution. Every sentence references a feature the model actually used (consistency rule).
Reused by the Phase 6 insight engine (chemistry_discovery).
"""

from __future__ import annotations

# base feature concept -> (positive-contribution phrase, negative-contribution phrase).
# A contribution is in xGF% space: positive raises the projection (a strength), negative lowers
# it (a risk). The _mean/_min/_max aggregates of a concept are summed before phrasing.
FRAGMENT = {
    "off_impact": ("strong combined even-strength offensive impact",
                   "none of the three drives much even-strength offense"),
    "def_impact": ("strong combined defensive impact",
                   "thin defensive impact — expect to be sheltered"),
    "finishing": ("finishing talent above expected", "finishing that grades below expected"),
    "rush_share": ("rush-driven shot generation", "little rush offense"),
    "rebound_share": ("a net-front, rebound-hunting presence", "few rebound chances generated"),
    "forecheck_share": ("forecheck-driven offense", "little forecheck pressure"),
    "cycle_share": ("a possession and cycle game", "little sustained cycle game"),
    "point_share": ("point-shot volume from the back end", "few point shots"),
    "mean_shot_distance": ("a shot diet from in tight", "a perimeter shot diet"),
    "slot_share": ("shots concentrated in the slot", "shots from the perimeter"),
    "pp_toi_share": ("power-play pedigree", "little power-play pedigree"),
    "pk_toi_share": ("penalty-kill responsibility", "little penalty-kill role"),
    "edge_burst_per60": ("high-end skating pace", "modest skating pace"),
    "edge_oz_pct": ("a strong territorial (o-zone) tilt", "a weak territorial tilt"),
    "pair_arch_cos": ("overlapping roles among the members",
                      "complementary, non-overlapping roles"),
    "pair_shotloc_dist": ("varied, hard-to-defend shot locations", "redundant shot locations"),
    "hand_balance": ("left/right handedness balance", "a one-handed imbalance"),
    "burst_spread": ("mismatched skating pace", "well-matched skating pace"),
    "oz_tilt_mean": ("a strong combined territorial tilt", "a weak combined territorial tilt"),
}

_SUFFIXES = ("_mean", "_min", "_max")
# concepts that are line-level descriptors rather than per-member, never aggregated
_SKIP = {"n_members", "is_forward_line"}


def _base(col: str) -> str:
    for s in _SUFFIXES:
        if col.endswith(s):
            return col[: -len(s)]
    return col


def grade_sentence(grade: str, xgf_pct: float, line_type: str) -> str:
    unit = "forward trio" if line_type == "F3" else "defense pair"
    return f"Projected as a {grade}-grade {unit} at {xgf_pct * 100:.0f}% expected-goals share."


def reasons_and_risk(contribs: dict[str, float], *, max_reasons: int = 3,
                     min_magnitude: float = 0.004) -> tuple[list[str], str | None]:
    """Collapse per-column contributions to per-concept, return strength reasons + one risk."""
    agg: dict[str, float] = {}
    for col, val in contribs.items():
        base = _base(col)
        if base in _SKIP or base not in FRAGMENT:
            continue
        agg[base] = agg.get(base, 0.0) + float(val)

    ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
    reasons: list[str] = []
    for base, v in ranked:
        if v <= min_magnitude or len(reasons) >= max_reasons:
            break
        reasons.append(FRAGMENT[base][0])

    risk: str | None = None
    if ranked:
        base, v = ranked[-1]
        if v <= -min_magnitude:
            risk = FRAGMENT[base][1]
    return reasons, risk


def _aggregate_concepts(contribs: dict[str, float]) -> dict[str, float]:
    """Collapse per-column contributions (xGF% space) to per-concept totals."""
    agg: dict[str, float] = {}
    for col, val in contribs.items():
        base = _base(col)
        if base in _SKIP or base not in FRAGMENT:
            continue
        agg[base] = agg.get(base, 0.0) + float(val)
    return agg


def swap_reasons(original_contribs: dict[str, float], swapped_contribs: dict[str, float],
                 *, max_reasons: int = 2, min_magnitude: float = 0.003) -> list[str]:
    """Why a candidate fits a line better than the current member.

    Compares per-concept contributions of the swapped line vs the original and surfaces the
    concept(s) the swap improves most, phrased with the positive FRAGMENT for that concept.
    """
    before = _aggregate_concepts(original_contribs)
    after = _aggregate_concepts(swapped_contribs)
    deltas = {k: after.get(k, 0.0) - before.get(k, 0.0) for k in set(before) | set(after)}
    ranked = sorted(deltas.items(), key=lambda kv: kv[1], reverse=True)
    out: list[str] = []
    for base, d in ranked:
        if d <= min_magnitude or len(out) >= max_reasons:
            break
        out.append(FRAGMENT[base][0])
    return out


def explain(*, grade: str, xgf_pct: float, line_type: str,
            contribs: dict[str, float]) -> dict:
    """Compose the full explanation payload for a projection."""
    reasons, risk = reasons_and_risk(contribs)
    if not reasons:
        reasons = ["a balanced statistical profile with no standout driver"]
    return {
        "grade_sentence": grade_sentence(grade, xgf_pct, line_type),
        "reasons": reasons,
        "risk": risk,
    }


# Verbatim honest-limitations footer the frontend renders under every projection (blueprint 6.2).
LIMITATIONS_FOOTER = (
    "This projects statistical shape only — how these players' measured roles and skills tend to "
    "combine. It does not capture personality, practice chemistry, coaching systems, or in-game "
    "adjustments. Treat the grade as a prior, not a verdict."
)
