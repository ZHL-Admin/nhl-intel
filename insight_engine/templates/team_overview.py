"""
Team Overview "quick insights" generator (Layer 1).

Pure, deterministic, no LLM and no BigQuery: takes a team's already-computed season values and
league ranks (the same numbers /teams/{id} puts on the page) and emits plain-English insight
cards, each anchored to a number on the page (the consistency rule, mirroring team_fit /
value_gap). The router computes the inputs and calls this; the function is unit-testable against
fixtures because it never touches I/O.

Every candidate carries a `key` (category) so the frontend can DEDUPE a card against the Streak
Doctor "cold strip" — e.g. not lead with goaltending in both. Candidates are returned most-salient
first; the caller renders the top N after dedup. Divergence stories (finishing / goaltending
out- or under-running the chances) are weighted highest because they are the most worth surfacing.
"""
from __future__ import annotations

# All ranks here are 1 = best. Top/bottom thirds of a 32-team league.
_GOOD_BY = 10


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _tone(rank: int, n: int) -> str:
    if rank <= _GOOD_BY:
        return "positive"
    if rank >= n - (_GOOD_BY - 1):
        return "caution"
    return "neutral"


def _salience(rank: int, n: int) -> float:
    """Distance from the middle of the league — extremes are most worth surfacing."""
    return abs(rank - (n + 1) / 2)


# How far two ranks must diverge before a finishing/goaltending luck story is worth telling.
_DIVERGENCE_RANKS = 6


def insights(team: dict, n: int = 32) -> list[dict]:
    """Build ordered quick-insight candidates from a team's season values + ranks.

    `team` keys (any may be missing -> that card is skipped, never faked):
      team_abbrev, gf_per_gp, ga_per_gp, cf_pct, xgf_share, hdcf_per60, hdca_per60,
      *_rank counterparts (gf_per_gp_rank, ga_per_gp_rank, cf_pct_rank, xgf_pct_rank,
      hdcf_per60_rank, hdca_per60_rank, xga_per60_rank).
    """
    ab = team.get("team_abbrev") or "They"
    out: list[tuple[float, dict]] = []

    def add(sal: float, key: str, tone: str, icon: str, title: str, body: str) -> None:
        out.append((sal, {"key": key, "tone": tone, "icon": icon, "title": title, "body": body}))

    gf, gfr = team.get("gf_per_gp"), team.get("gf_per_gp_rank")
    if gf is not None and gfr:
        add(_salience(gfr, n), "offense", _tone(gfr, n), "flame", "Scoring",
            f"{ab} are scoring {gf:.2f} goals per game, {_ordinal(gfr)} of {n} in the NHL.")

    ga, gar = team.get("ga_per_gp"), team.get("ga_per_gp_rank")
    if ga is not None and gar:
        add(_salience(gar, n), "defense", _tone(gar, n), "shield", "Goal prevention",
            f"They allow {ga:.2f} goals per game, {_ordinal(gar)} of {n}.")

    cf, cfr = team.get("cf_pct"), team.get("cf_pct_rank")
    if cf is not None and cfr:
        add(_salience(cfr, n), "possession", _tone(cfr, n), "gauge", "Possession",
            f"{ab} control {cf * 100:.1f}% of shot attempts at 5v5, {_ordinal(cfr)} in the league.")

    xs, xr = team.get("xgf_share"), team.get("xgf_pct_rank")
    if xs is not None and xr:
        add(_salience(xr, n), "chances", _tone(xr, n), "crosshair", "Chance quality",
            f"Their expected-goals share is {xs * 100:.1f}% which ranks {_ordinal(xr)}/{n}.")

    hf, hfr = team.get("hdcf_per60"), team.get("hdcf_per60_rank")
    if hf is not None and hfr:
        add(_salience(hfr, n), "danger_for", _tone(hfr, n), "zap", "High-danger offense",
            f"{ab} generate {hf:.1f} high-danger chances per 60, {_ordinal(hfr)} of {n}.")

    hp, hpr = team.get("hdca_per60"), team.get("hdca_per60_rank")
    if hp is not None and hpr:
        add(_salience(hpr, n), "danger_against", _tone(hpr, n), "shield-check", "High-danger defense",
            f"They give up {hp:.1f} high-danger chances per 60, {_ordinal(hpr)} of {n}.")

    # Finishing: goals rank vs expected-goals-share rank. Positive diff => scoring ahead of chances.
    if gfr and xr:
        diff = xr - gfr
        if diff >= _DIVERGENCE_RANKS:
            add(_salience(1, n) + diff, "finishing", "caution", "sparkles", "Finishing above expected",
                f"{ab} rank {_ordinal(gfr)} in goals but {_ordinal(xr)} in expected-goals share — "
                f"some scoring regression is likely.")
        elif diff <= -_DIVERGENCE_RANKS:
            add(_salience(1, n) - diff, "finishing", "positive", "sparkles", "Finishing below expected",
                f"{ab} rank {_ordinal(xr)} in expected-goals share but {_ordinal(gfr)} in goals — "
                f"better finishing luck would lift the offense.")

    # Goaltending: goals-against rank vs expected-goals-against rank. Positive diff => fewer GA than expected.
    xar = team.get("xga_per60_rank")
    if gar and xar:
        diff = xar - gar
        if diff >= _DIVERGENCE_RANKS:
            add(_salience(1, n) + diff, "goaltending", "caution", "hand", "Goaltending carrying",
                f"{ab} sit {_ordinal(gar)} in goals against despite {_ordinal(xar)} in expected goals "
                f"against — goaltending has outrun the chances allowed.")
        elif diff <= -_DIVERGENCE_RANKS:
            add(_salience(1, n) - diff, "goaltending", "neutral", "hand", "Goaltending lagging",
                f"{ab} are {_ordinal(xar)} in expected goals against but {_ordinal(gar)} in actual "
                f"goals against — the crease has cost them.")

    out.sort(key=lambda t: t[0], reverse=True)
    return [card for _, card in out]
