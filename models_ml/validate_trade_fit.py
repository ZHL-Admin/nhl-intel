"""Validation for the multi-dimension Trade Fit rebuild (Part 3): print disagreement cases where
need and style/quality diverge, and confirm no dimension floors at 0 inappropriately.

Run:  python -m models_ml.validate_trade_fit
"""
from __future__ import annotations

from models_ml import bq
from models_ml.score_team_fit import score_team_fit

# players: Hutson(off D) 8483457, Slavin(def D) 8476958, Pastrnak(W) 8477956, McDavid 8478402.
# teams: VGK 54 (strong def), CHI 16 (weak def), TOR 10 (strong-O / weak-D), CAR 12 (high-event),
#        CBJ 29 (lower-event).


def _mediocre_d() -> int:
    """Lowest-WAR qualified defenseman this season (the 'mediocre addresses a need' case)."""
    p = bq.project()
    df = bq.query_df(f"""select player_id from `{p}.nhl_models.player_gar`
        where season_window=(select max(season_window) from `{p}.nhl_models.player_gar`
                             where season_window like '____-__')
          and position='D' and toi_5v5>=600 order by war asc limit 1""")
    return int(df.iloc[0]["player_id"])


def main() -> None:
    med_d = _mediocre_d()
    cases = [
        ("Off. D (Hutson) -> STRONG-def VGK   [need LOW, others carry]", 8483457, 54),
        ("Off. D (Hutson) -> WEAK-def CHI      [need HIGH]", 8483457, 16),
        ("Def. D (Slavin) -> STRONG-def VGK    [need LOW; positional/quality carry — was ~0]", 8476958, 54),
        ("Winger (Pastrnak) -> TOR strong-O/weak-D  [wrong position for the need]", 8477956, 10),
        ("Star (McDavid) -> CAR high-event     [style match]", 8478402, 12),
        ("Star (McDavid) -> CBJ lower-event    [style differs]", 8478402, 29),
        (f"Mediocre D ({med_d}) -> WEAK-def TOR  [real need, low quality -> moderate]", med_d, 10),
    ]
    for title, pid, tid in cases:
        try:
            r = score_team_fit(pid, tid)
        except Exception as e:
            print(f"\n### {title}\n    ERROR: {e}")
            continue
        print(f"\n### {title}")
        print(f"    OVERALL: {r['overall_grade']}  ({r['overall_score']}/100)")
        for d in r["dimensions"]:
            lvl = "  n/a" if d["level"] is None else f"{d['level'] * 100:4.0f}"
            unc = " ~" if d.get("uncertain") else "  "
            print(f"      {d['label']:16s} {lvl}{unc} {d['value']:>10s}  {d['note'][:74]}")
        print(f"    VERDICT: {r['verdict_sentence']}")


if __name__ == "__main__":
    main()
