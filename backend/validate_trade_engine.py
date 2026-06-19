"""Validate the trade engine on three representative trade archetypes and print a pasteable report.

Run from the repo (reads the DuckDB serving file, like the backend):
    SERVING_BACKEND=duckdb python -m backend.validate_trade_engine
or via `make trade-engine-validate`.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SERVING_BACKEND", "duckdb")
sys.path.insert(0, str(Path(__file__).resolve().parent))   # backend/ on the path

from services import trade_engine   # noqa: E402

# Representative scenarios (team_ids: MIN=30, VGK=54). Assets resolved from the tradeable layer.
SCENARIOS = [
    ("Star-for-picks (rebuild return)", {
        "team_ids": [30, 54],
        "movements": [
            {"asset_id": "player:8478864", "from_team_id": 30, "to_team_id": 54},   # Kaprizov -> VGK
            {"asset_id": "pick:VGK:2026:R1", "from_team_id": 54, "to_team_id": 30},
            {"asset_id": "pick:VGK:2027:R1", "from_team_id": 54, "to_team_id": 30},
            {"asset_id": "pick:VGK:2026:R2", "from_team_id": 54, "to_team_id": 30},
        ]}),
    ("Hockey trade (comparable stars)", {
        "team_ids": [30, 54],
        "movements": [
            {"asset_id": "player:8478864", "from_team_id": 30, "to_team_id": 54},   # Kaprizov <-> Marner
            {"asset_id": "player:8478483", "from_team_id": 54, "to_team_id": 30},
        ]}),
    ("Cap dump with 50% retention", {
        "team_ids": [30, 54],
        "movements": [
            {"asset_id": "player:8478864", "from_team_id": 30, "to_team_id": 54},    # Kaprizov -> VGK
            {"asset_id": "pick:MIN:2026:R2", "from_team_id": 30, "to_team_id": 54},  # MIN attaches a pick to dump
        ],
        "retentions": [{"player_id": 8478864, "retaining_team_id": 30, "retained_pct": 0.5}]}),
]


def _fmt_team(t: dict) -> str:
    cap = t.get("cap") or {}
    over = " OVER(approx)" if cap.get("over_cap") else ""
    fit = "n/a" if t.get("fit_delta") is None else f"{t['fit_delta']:+.1f}"
    return (f"  {t['team_abbrev']:4s} | talent {t['talent_delta_war']:+5.1f} WAR "
            f"[{t['talent_delta_war_low']:+5.1f},{t['talent_delta_war_high']:+5.1f}] | "
            f"surplus ${t['surplus_delta_dollars']/1e6:+6.1f}M (cap-share {t['surplus_delta_capshare']:+.3f}) | "
            f"fit {fit:>6s} | cap ${cap.get('cap_hit_change', 0)/1e6:+6.1f}M{over} | conf {t['confidence']}")


def main() -> None:
    print("=" * 100)
    print("TRADE ENGINE VALIDATION — multi-axis decomposition (talent / surplus / fit / soft cap)")
    print("=" * 100)
    for title, req in SCENARIOS:
        print(f"\n### {title}")
        res = trade_engine.evaluate(req)
        for t in res["teams"]:
            print(_fmt_team(t))
        for s in res["summary"]:
            print(f"    > {s['headline']}")
    print("\nCaveats:")
    for c in res["caveats"]:
        print(f"  - {c}")


if __name__ == "__main__":
    main()
