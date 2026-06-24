"""Deterministic verdict + reasons for the offseason roster forecast.

Pure functions over the roster_forecast row and its move ledger. EVERY sentence references a number
present in the payload (the consistency rule, like divergence.py / team_fit.py). The verdict names
the largest-magnitude moves as the drivers, foregrounds the band, and — when no material moves were
made (deep offseason / quiet summer) — says so explicitly instead of asserting a confident near-zero
forecast. A verbatim limitations footer names the blind spots the band does NOT include.
"""

from __future__ import annotations

# The band excludes these by construction; stated verbatim on every forecast so the call stays honest.
LIMITATIONS = ("This projection moves only the team LABEL of value from the roster's moves; the band "
               "excludes salary cap, injuries, training-camp job battles, a coaching change, and "
               "prospect development — the model cannot see them. A just-arrived player's value still "
               "reflects his old-team usage until he plays for his new club.")


def _ordinal(n: int) -> str:
    if n is None:
        return "unranked"
    s = {1: "st", 2: "nd", 3: "rd"}.get(n if n < 20 else n % 10, "th")
    return f"{n}{s}"


def _name(move: dict) -> str:
    return move.get("name") or f"player {move.get('player_id')}"


def driver_moves(ledger: list[dict], k: int = 3) -> list[dict]:
    """The k moves that shifted the most projected value (|delta_contribution|), arrivals/departures
    first — the same 'largest-magnitude drivers' logic divergence.py / team_fit.py use."""
    movers = [m for m in ledger if m.get("move_type") in ("arrival", "departure")
              and m.get("player_id") is not None]
    return sorted(movers, key=lambda m: abs(m.get("delta_contribution", 0.0)), reverse=True)[:k]


def verdict(row: dict, ledger: list[dict]) -> str:
    """One deterministic sentence. Every number cited is in `row`."""
    delta = row["delta"]
    proj, lo, hi = row["projected_rating"], row["band_low"], row["band_high"]
    rank, base_rank = row.get("projected_rank"), row.get("base_rank")

    if row.get("negligible"):
        return (f"No material moves yet ({row['n_moves']} roster changes, net {row['net_delta_war']:+.1f} "
                f"projected WAR): the roster still projects essentially as last season "
                f"({proj:+.2f} rating, band {lo:+.2f} to {hi:+.2f}). Check back once the additions land.")

    drivers = driver_moves(ledger, 2)
    if drivers:
        d = drivers[0]
        verb = "adding" if d["move_type"] == "arrival" else "losing"
        driver_clause = (f"driven mainly by {verb} {_name(d)} "
                         f"({d['delta_contribution']:+.1f} projected WAR)")
    else:
        driver_clause = f"from {row['n_moves']} smaller moves"

    direction = "better" if delta > 0 else "worse"
    rank_clause = ""
    if rank is not None and base_rank is not None and rank != base_rank:
        rank_clause = f", projected to move from {_ordinal(base_rank)} to {_ordinal(rank)} in the league"
    return (f"The moves project this team {abs(delta):.2f} goals/game {direction} next season "
            f"({proj:+.2f} rating, band {lo:+.2f} to {hi:+.2f}){rank_clause} — {driver_clause}.")


def reasons(row: dict, ledger: list[dict]) -> list[str]:
    """Up to three number-grounded reasons. Each references a value present in the payload."""
    out: list[str] = []
    for d in driver_moves(ledger, 3):
        verb = "Adds" if d["move_type"] == "arrival" else "Loses"
        nt = " (no NHL track record, replacement-level with a wide band)" if d.get("no_track_record") else ""
        out.append(f"{verb} {_name(d)}: {d['delta_contribution']:+.1f} projected WAR "
                   f"(band ±{d.get('war_sd', 0.0):.1f}){nt}.")
    chem = row.get("chemistry_adj")
    if chem is not None and abs(chem) >= 0.01:
        tone = "lift" if chem > 0 else "drag"
        out.append(f"Line-fit chemistry is a {abs(chem):.2f} goals/game {tone} on the projected top units.")
    if row.get("style_note"):
        out.append(str(row["style_note"]))
    return out[:3]


def explain(row: dict, ledger: list[dict]) -> dict:
    """Full payload for the team-detail endpoint: verdict, reasons, and the verbatim limitations."""
    return {"verdict": verdict(row, ledger), "reasons": reasons(row, ledger), "limitations": LIMITATIONS}
