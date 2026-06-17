"""
Impact (RAPM) vs Value (GAR) gap read — deterministic, data-traceable, ASYMMETRIC.

RAPM = repeatable play-driving on the xG layer ("what tends to repeat"). GAR = actual goals
above replacement ("what happened"); it inherits shooting luck by design. The gap between a
player's Value percentile and Impact percentile (within position) is finishing / luck / usage.

The two divergent reads are deliberately NOT symmetric, because the year-over-year stability
finding (models_ml/validate_gar.py, cited verbatim) is asymmetric:
  - production repeats at r≈{production_r} (sticky),
  - RAPM's isolated rate at r≈{rapm_r} (noisier as a measurement),
  - the finishing residual at r≈{finishing_r} (the only truly luck-flavored slice).
So a player who DRIVES play but hasn't finished (Impact >> Value) is the better-grounded
regression case: his chances are real and repeatable, only his finishing is unrepeatable.
A player coasting on finishing (Value >> Impact) is the softer case — the production is real
and likely persists, but the edge opening the gap is the least sticky thing in hockey.

Every sentence references a number in the payload (the gap percentile points + the r values),
so "least repeatable" traces to r={finishing_r}, not an assertion (consistency rule).
"""

from __future__ import annotations

# A divergence is "material" when Value and Impact percentiles differ by at least this (points).
GAP_THRESHOLD = 15.0


def read(*, name: str, value_pct: float, impact_pct: float,
         production_r: float, rapm_r: float, finishing_r: float) -> dict:
    """Build {case, headline, body, numbers_used} for the Impact-vs-Value panel."""
    gap = round((value_pct - impact_pct) * 100, 0)  # percentile points, Value minus Impact
    pr, fr = f"{production_r:.2f}", f"{finishing_r:.2f}"

    if gap >= GAP_THRESHOLD:
        case = "value_over_impact"
        headline = "Produces above his play-driving"
        body = (f"{name} produces more than his play-driving suggests ({int(gap)} percentile "
                f"points higher in Value than Impact), and that production is real and tends to "
                f"persist — production repeats year to year at r={pr}. The edge opening the gap, "
                f"finishing above expected, is the least repeatable part of any player's game "
                f"(r={fr}), so expect the gap to narrow even if the production holds.")
    elif gap <= -GAP_THRESHOLD:
        case = "impact_over_value"
        headline = "Drives play harder than his results"
        body = (f"{name} drives more chances than his goals show ({int(-gap)} percentile points "
                f"higher in Impact than Value). Those chances are real and repeatable "
                f"(production repeats at r={pr}); the missing finish is the least repeatable part "
                f"of the game (r={fr}). This is the better-grounded regression case — a buy-low "
                f"signal with more statistical support than fading a finisher's hot run.")
    else:
        case = "aligned"
        headline = "Value and play-driving agree"
        body = (f"{name}'s Value and Impact line up (within {int(GAP_THRESHOLD)} percentile "
                f"points) — the actual results and the repeatable play-driving tell the same "
                f"story, so this profile reads with high confidence.")

    return {
        "case": case,
        "headline": headline,
        "body": body,
        "numbers_used": {"gap_pctile_points": gap, "value_pct": round(value_pct * 100),
                         "impact_pct": round(impact_pct * 100),
                         "production_r": production_r, "finishing_r": finishing_r,
                         "rapm_r": rapm_r},
    }
