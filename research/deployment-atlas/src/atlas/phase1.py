"""Phase 1.3 + 1.4 driver: assemble the corpus from BigQuery, run integrity.

Writes:
  data/parquet/{shifts,events,boxscore_toi,penalty_ledger}.parquet   (1.3)
  reports/figures/toi_delta_hist.png                                 (1.4 histogram)
  reports/phase1_integrity.json                                      (machine evidence)

Run: `make phase1`  (or `python -m atlas.phase1`)
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from . import config, integrity, sources
from .client import AtlasClient


def _worst_games(coverage: dict, overlaps: dict, goals: dict, n: int = 10) -> list[dict]:
    """Rank games: missing-shift games first, then most TOI-failing player-games,
    then genuine overlaps / goal misses."""
    shifts = pl.read_parquet(sources.SHIFTS_PARQUET)
    toi = pl.read_parquet(sources.BOXSCORE_TOI_PARQUET)
    ss = shifts.group_by("game_id", "player_id").agg(
        pl.col("duration_seconds").sum().alias("s"))
    m = ss.join(toi.select("game_id", "player_id", "toi_seconds"),
                on=["game_id", "player_id"], how="inner")
    m = m.with_columns(bad=(pl.col("s") - pl.col("toi_seconds")).abs() > integrity.TOI_TOLERANCE_S)
    per_game = m.group_by("game_id").agg(
        pl.col("bad").sum().alias("toi_fail_player_games"),
        (pl.col("s") - pl.col("toi_seconds")).abs().max().alias("max_abs_delta_s"),
    )
    toi_map = {r["game_id"]: r for r in per_game.to_dicts()}

    overlap_games = set(overlaps["bad_games"])
    goal_miss_games = set(goals["miss_games"])
    no_shift = coverage["no_shift_games"]

    out: list[dict] = []
    # missing-shift games are the worst (no data at all)
    for gid in no_shift[:n]:
        out.append({"game_id": gid, "reasons": ["no shift data (empty raw shift array)"],
                    "rank_key": (2, 0)})
    # then games with the most TOI failures / overlaps
    ranked = sorted(toi_map.values(), key=lambda r: (r["toi_fail_player_games"],
                    r["max_abs_delta_s"]), reverse=True)
    for r in ranked:
        if len(out) >= n:
            break
        gid = r["game_id"]
        if gid in set(no_shift):
            continue
        reasons = []
        if r["toi_fail_player_games"]:
            reasons.append(f"{r['toi_fail_player_games']} player-games TOI>30s off "
                           f"(max {r['max_abs_delta_s']}s)")
        if gid in overlap_games:
            reasons.append("genuine overlapping shifts")
        if gid in goal_miss_games:
            reasons.append("goal scorer not on ice")
        if reasons:
            out.append({"game_id": gid, "reasons": reasons})
    return out[:n]


def _histogram(delta_df: pl.DataFrame) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = delta_df["delta"].to_numpy()
    clip = 120
    dc = d.clip(-clip, clip)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(dc, bins=121, color="#2b6cb0", edgecolor="none")
    ax.axvline(-30, color="#c53030", ls="--", lw=1, label="±30s tolerance")
    ax.axvline(30, color="#c53030", ls="--", lw=1)
    ax.set_xlabel("shift-sum − boxscore TOI  (seconds, clipped ±120)")
    ax.set_ylabel("player-games")
    ax.set_title("Phase 1.4a — TOI reconciliation delta")
    ax.legend()
    within = (abs(d) <= 30).mean()
    ax.text(0.02, 0.95, f"within ±30s: {within:.3%}\nn = {len(d):,}",
            transform=ax.transAxes, va="top", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="#ccc"))
    fig.tight_layout()
    out = config.REPORTS_DIR / "figures" / "toi_delta_hist.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return str(out)


def main() -> int:
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with AtlasClient() as client:
        print("1.3 materializing corpus from BigQuery (+2 gap pbp fetches)...")
        mat = sources.materialize_all(client)
        for k, v in mat.items():
            print(f"   {k}: {v['rows']:,} rows / {v.get('games','?')} games -> {v['path']}")

        print("1.4 integrity tests...")
        cov = integrity.shift_coverage()
        no_shift = set(cov["no_shift_games"])
        a = integrity.test_toi_reconciliation()
        b = integrity.test_no_overlaps()
        c = integrity.test_goal_scorer_on_ice(no_shift)
        d = integrity.test_freshness(client)

    total_games = cov["box_games"]
    q = integrity.quarantine(cov, b, c, total_games)
    worst = _worst_games(cov, b, c)
    fig = _histogram(a["delta_series"])

    summary = {
        "materialize": mat,
        "coverage": {k: v for k, v in cov.items() if k != "shift_games_set"},
        "test_a_toi": {k: v for k, v in a.items() if k != "delta_series"},
        "test_b_overlaps": {k: (v[:50] if k == "bad_games" else v) for k, v in b.items()},
        "test_c_goal_on_ice": {k: (v[:50] if k == "miss_games" else v) for k, v in c.items()},
        "test_d_freshness": d,
        "quarantine": q,
        "worst_games": worst,
        "histogram": fig,
        "total_games": total_games,
    }
    out = config.REPORTS_DIR / "phase1_integrity.json"
    out.write_text(json.dumps(summary, indent=2, default=str))

    print(f"\n coverage: {cov['no_shift_count']} of {cov['box_games']} boxscore games have NO shift data")
    print(f" a) TOI within 30s (shift games): {a['pass_rate']:.4%} (n={a['player_games']:,}) "
          f"{'PASS' if a['passed'] else 'FAIL'}")
    print(f" b) overlapping shifts (post-dedup): {b['overlap_rows']} rows / {b['games_with_overlap']} games "
          f"{'PASS' if b['passed'] else 'FAIL'}")
    print(f" c) goal scorer on ice (shift games): {c['on_ice_rate']:.4%} (n={c['goals_tested']:,}) "
          f"{'PASS' if c['passed'] else 'FAIL'}")
    print(f" d) freshness all-match: {d['all_match']}")
    print(f" quarantine union: {q['quarantine_union']} games ({q['fraction']:.4%}) "
          f"under_0.5%={q['under_half_pct']}")
    print(f" wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
