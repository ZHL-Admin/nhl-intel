"""
Matchup-preview style-clash templates (Phase 5.3, blueprint 6.4).

Deterministic sentences comparing two teams' identity fingerprints (mart_team_identity league
percentiles). No LLM. Each rule fires only when the percentile contrast is sharp enough, and every
sentence it emits references the percentiles in the payload (consistency rule). Reused by the
Phase 6 insight engine.

clash(home, away) takes two dicts of {metric_key: percentile (0-1)} plus abbreviations and returns
an ordered list of clash sentences (most pronounced first).
"""

from __future__ import annotations

# how far apart two percentiles must be for a contrast rule to fire
CONTRAST = 0.30
# how high a single-team percentile must be to call out a strength
STRONG = 0.70


def _p(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.5


def _pct(v) -> str:
    return f"{round(_p(v) * 100)}th pct"


def clash(home: dict, away: dict, home_abbr: str, away_abbr: str) -> list[str]:
    out: list[tuple[float, str]] = []

    def contrast(metric, hi_phrase, lo_phrase):
        h, a = _p(home.get(metric)), _p(away.get(metric))
        if abs(h - a) < CONTRAST:
            return
        hi, lo = (home_abbr, away_abbr) if h > a else (away_abbr, home_abbr)
        hp, lp = (h, a) if h > a else (a, h)
        out.append((abs(h - a),
                    f"{hi} {hi_phrase} ({_pct(hp)}) against {lo}'s {lo_phrase} ({_pct(lp)})."))

    contrast("pace", "plays at a high pace", "slower game")
    contrast("forecheck_share_for", "leans on a heavy forecheck", "lighter forecheck")
    contrast("rush_share_for", "generates off the rush", "low-rush attack")
    contrast("shot_quality", "hunts high-quality looks", "lower shot quality")
    contrast("shot_volume_per60", "drives shot volume", "lower-volume attack")
    contrast("hits_per60", "plays a physical game", "less physical")

    # single-team standout strengths (only if not already a contrast leader)
    for team, abbr, opp in [(home, home_abbr, away_abbr), (away, away_abbr, home_abbr)]:
        if _p(team.get("forecheck_share_for")) >= STRONG and _p(team.get("forecheck_share_for")) - \
                _p((away if abbr == home_abbr else home).get("forecheck_share_for")) < CONTRAST:
            out.append((0.1, f"{abbr} forechecks among the league's heaviest "
                             f"({_pct(team.get('forecheck_share_for'))})."))

    out.sort(key=lambda t: t[0], reverse=True)
    seen, result = set(), []
    for _, s in out:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result[:4]
