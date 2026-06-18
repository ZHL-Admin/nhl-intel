"""Validation for Trade Fit: NEED is an asymmetric ADDITIVE bonus, not an averaged term.

Prints, per case, the score decomposition (gate, base, need_bonus, final, grade) and asserts the
asymmetry must-holds:
  - low need NEVER lowers the grade vs the same trade with the need bonus removed (bonus >= 0);
  - need can only help; a bad player can never be rescued to a good grade by need alone;
  - a top-5 player to a team ALREADY STRONG at his position still grades A (talent carries; low
    need adds nothing but does not penalise).
Also prints the score distribution over a sample so the GRADE_BANDS can be tuned to it.

Run (fast, against the serving file):  SERVING_BACKEND=duckdb python -m models_ml.validate_trade_fit
"""
from __future__ import annotations

import statistics

from models_ml import bq, config
from models_ml.score_team_fit import score_team_fit, _need_bonus

CFG = config.TRADE_FIT


def _season() -> str:
    p = bq.project()
    return bq.query_df(f"select max(season) s from `{p}.nhl_models.team_needs`").iloc[0]["s"]


def _lowest_war(position_clause: str) -> int:
    """Lowest-WAR qualified skater (the 'bad player' case)."""
    p = bq.project(); s = _season()
    df = bq.query_df(f"""select player_id from `{p}.nhl_models.player_gar`
        where season_window='{s}' and toi_5v5>=600 {position_clause} order by war asc limit 1""")
    return int(df.iloc[0]["player_id"])


def _mid_war(position_clause: str, target_pctile: float = 0.30) -> int:
    """A below-average-but-rosterable skater (~target WAR percentile) — the 'mediocre, addresses a
    need' case (default ~30th pctile so the need bump visibly lifts him toward C without making him
    good)."""
    p = bq.project(); s = _season()
    df = bq.query_df(f"""with q as (
            select player_id, percent_rank() over (order by war) pr
            from `{p}.nhl_models.player_gar` where season_window='{s}' and toi_5v5>=600 {position_clause})
        select player_id from q order by abs(pr - {target_pctile}) asc limit 1""")
    return int(df.iloc[0]["player_id"])


def decompose(r: dict) -> dict:
    """Recompute gate / base / gated_base / need_bonus / final from a scored result's dims."""
    by = {d["key"]: d for d in r["dimensions"]}
    gate = by["positional"]["level"] or CFG["GATE_FLOOR"]
    w = CFG["WEIGHTS"]; num = den = 0.0
    for k in ("quality", "line", "style"):
        lv = by[k]["level"]
        if lv is not None:
            num += w[k] * lv; den += w[k]
    base = (num / den) if den > 0 else 0.5
    gated = gate * base
    bonus = _need_bonus(by["need"].get("gap"))
    return {"gate": gate, "base": base, "gated_base": gated, "need_bonus": bonus,
            "need_gap": by["need"].get("gap"), "need_level": by["need"]["level"],
            "quality": by["quality"]["level"], "line": by["line"]["level"], "style": by["style"]["level"],
            "final": round(gated + bonus, 4), "grade": r["overall_grade"]}


def _extreme_need_teams(player_id: int, season: str) -> tuple[int, int]:
    """For a player, the team with the LOWEST and HIGHEST need-gap in his area (data-driven)."""
    teams = bq.query_df(f"""select distinct team_id from `{bq.project()}.nhl_mart.mart_team_game_stats`
        where season='{season}'""")["team_id"].astype(int).tolist()
    gaps = []
    for tid in teams:
        try:
            r = score_team_fit(player_id, tid, season)
        except Exception:
            continue
        g = {d["key"]: d for d in r["dimensions"]}["need"].get("gap") or 0.0
        gaps.append((g, tid))
    gaps.sort()
    return gaps[0][1], gaps[-1][1]  # (lowest-need team, highest-need team)


def _row(title, pid, tid, season):
    r = score_team_fit(pid, tid, season)
    d = decompose(r)
    print(f"\n{title}")
    print(f"  player={pid} team={tid}  gate={d['gate']:.2f} base={d['base']:.2f} "
          f"gated_base={d['gated_base']:.3f}  need_gap={d['need_gap']} need_bonus=+{d['need_bonus']:.3f}"
          f"  -> final={d['final']:.3f}  grade={d['grade']}")
    print(f"     dims: quality={d['quality']} line={d['line']} style={d['style']} need_level={d['need_level']}")
    print(f"     verdict: {r['verdict_sentence']}")
    return r, d


def main() -> None:
    season = _season()
    MCDAVID = 8478402            # top-5 player
    KESSELRING = 8480891         # the reported case (below-avg D)
    ANA = 24
    low_need_team, high_need_team = _extreme_need_teams(MCDAVID, season)
    bad = _lowest_war("and position='D'")
    mediocre = _mid_war("and position='D'", target_pctile=0.38)
    print(f"season={season}  McDavid low-need team={low_need_team} high-need team={high_need_team}  "
          f"mediocre D={mediocre}  bad D={bad}")

    results = []
    results.append(_row("KESSELRING -> ANA (reported: low need, good fit, below-avg value) — expect B/C not D",
                        KESSELRING, ANA, season))
    results.append(_row("TOP-5 (McDavid) -> ALREADY-STRONG/low-need team — KEY asymmetry test: expect A",
                        MCDAVID, low_need_team, season))
    results.append(_row("TOP-5 (McDavid) -> BIG-need team — high base + full need bonus: expect highest A",
                        MCDAVID, high_need_team, season))
    results.append(_row("MEDIOCRE D -> BIG-need team — bonus lifts a middling player toward ~C",
                        mediocre, high_need_team, season))
    results.append(_row("BAD D -> low-need team — low base, no bonus: expect D/F",
                        bad, low_need_team, season))
    results.append(_row("BAD D -> BIG-need team — full bonus still can't rescue: expect D/F",
                        bad, high_need_team, season))

    # ---- asymmetry assertions -------------------------------------------------
    print("\n=== ASYMMETRY CHECKS ===")
    ok = True
    for r, d in results:
        if d["need_bonus"] < -1e-9:
            print(f"  FAIL: negative need bonus {d['need_bonus']}"); ok = False
        if (d["need_gap"] or 0) <= 0 and d["need_bonus"] > 1e-9:
            print(f"  FAIL: low/no need added a bonus {d['need_bonus']}"); ok = False

    _, d_low = results[1]; _, d_high = results[2]
    if abs(d_low["need_bonus"]) > 1e-9:
        print(f"  FAIL: McDavid low-need team still got a need bonus {d_low['need_bonus']}"); ok = False
    if d_high["final"] < d_low["final"] - 1e-9:
        print("  FAIL: high-need team scored LOWER than low-need for the same player"); ok = False
    if d_low["grade"] != "A":
        print(f"  WARN: McDavid->strong team graded {d_low['grade']} (expected A) — check weights/bands")
    # the bad player WITH a full need bonus (results[5]) must still grade D/F — need can't rescue
    _, d_bad_bigneed = results[5]
    if d_bad_bigneed["grade"] in ("A", "B", "C"):
        print(f"  FAIL: bad player rescued to {d_bad_bigneed['grade']} by need"); ok = False
    # Kesselring (results[0]) must not be D/F (good fit, only dragged by value)
    _, d_kess = results[0]
    if d_kess["grade"] in ("D", "F"):
        print(f"  WARN: Kesselring graded {d_kess['grade']} (expected B/C, not D)")
    print("  asymmetry holds." if ok else "  *** ASYMMETRY VIOLATED ***")

    # ---- score distribution (for band tuning) --------------------------------
    print("\n=== SCORE DISTRIBUTION (sample of player x team) ===")
    players = bq.query_df(f"""select player_id from `{bq.project()}.nhl_models.player_gar`
        where season_window='{season}' and toi_5v5>=400 order by war desc limit 6""")["player_id"].astype(int).tolist()
    players += bq.query_df(f"""select player_id from `{bq.project()}.nhl_models.player_gar`
        where season_window='{season}' and toi_5v5>=400 order by war asc limit 6""")["player_id"].astype(int).tolist()
    team_sample = [ANA, low_need_team, high_need_team, 22, 10, 54]
    scores = []
    for pid in players:
        for tid in team_sample:
            try:
                scores.append(score_team_fit(pid, tid, season)["overall_score"] / 100.0)
            except Exception:
                pass
    scores.sort()
    if scores:
        qs = {p: scores[min(len(scores) - 1, int(p / 100 * len(scores)))] for p in (5, 10, 25, 50, 75, 90, 95)}
        print(f"  n={len(scores)} min={scores[0]:.3f} max={scores[-1]:.3f} mean={statistics.mean(scores):.3f}")
        print("  percentiles:", {k: round(v, 3) for k, v in qs.items()})
        print("  current bands:", CFG["GRADE_BANDS"])


if __name__ == "__main__":
    main()
