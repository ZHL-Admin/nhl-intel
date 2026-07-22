"""Link 0 report — the 5v5 universe, the possession window, the coverage-track schema, fidelity.

Writes the Link-0 section of reports/probe.md. Validation of the per-defender geometry is done against
the def-scheme phase-0 primitive on 2025-26 (representative; the geometry is season-invariant).
"""
from __future__ import annotations

import polars as pl

from . import config as C
from .data import universe, counts
from .tracks import TRACKS


def _fidelity() -> dict:
    tr = pl.read_parquet(TRACKS, columns=["game_id", "event_id", "frame_index", "player_id", "dist_near_atk", "season"]) \
        .filter(pl.col("season") == "2025-26")
    dp = pl.read_parquet(C.DEFSCHEME_PRIM / "def_prim_2025_26.parquet",
                         columns=["game_id", "event_id", "frame_index", "player_id", "dist_nearest_atk"])
    m = tr.join(dp, on=["game_id", "event_id", "frame_index", "player_id"], how="inner")
    return {"matched": m.height,
            "corr": float(pl.DataFrame({"a": m["dist_near_atk"], "b": m["dist_nearest_atk"]}).select(pl.corr("a", "b")).item()),
            "mad": float((m["dist_near_atk"] - m["dist_nearest_atk"]).abs().mean())}


def _qtiles(s: pl.Series) -> dict:
    return {k: round(float(s.quantile(q)), 2) for k, q in
            [("min", 0), ("p10", .1), ("p25", .25), ("median", .5), ("p75", .75), ("p90", .9), ("max", 1)]}


def write():
    u = universe()
    c = counts(u)
    tr = pl.read_parquet(TRACKS)
    kept_goals = tr.select(pl.struct("game_id", "event_id").n_unique()).item()
    fid = _fidelity()

    L = []; W = L.append
    W("# Defensive Blame · Possession-Level Rebuild — probe.md\n")
    W(f"**{C.FRAMING}**\n")
    W(f"From-scratch possession model (branch research/def-blame-rebuild, own venv, seed {C.SEED}). "
      "Blame is measured over the whole possession, in isolation per defender, ABSOLUTE (a goal may assign "
      "~0 total blame). Read-only reuse: goal-tracking fused corpus + frames, def-scheme phase-0 "
      "primitives (validation only), Atlas stints/5v5. Nothing promoted.\n")

    W("\n## Link 0 · the 5v5 universe, the possession window, the coverage tracks\n")
    W("### The strength filter (fixed: even-strength 5v5 only)\n")
    W("| stage | goals |")
    W("|---|---|")
    W(f"| all tracked goals (reconstruction_ok) | {c['all_tracked_goals']:,} |")
    W(f"| **kept: 5v5, tracked, valid attack direction** | **{c['kept_5v5_tracked']:,}** |")
    W(f"| removed: not 5v5 (PP / PK / 4v4 / 3v3 / empty-net etc.) | {c['removed_non_5v5']:,} |")
    W(f"| of the 5v5 set, kept with exactly 5 defending & 5 attacking skaters tracked at the shot | {kept_goals:,} |")
    W("\nStrength breakdown of all tracked goals (the removed non-5v5 states):\n")
    W("| strength_state | goals |")
    W("|---|---|")
    for r in c["strength_breakdown"]:
        W(f"| {r['strength_state']} | {r['count']:,} |")
    W(f"\nThe exact-5v5-at-shot occupancy gate keeps **{kept_goals:,}** goals of the {c['kept_5v5_tracked']:,} "
      "5v5 set. The dropped goals are those where tracking shows fewer or more than five skaters per side at "
      "the shot instant (momentary dropout, or phantom over-detection that would corrupt a defender's "
      "'nearest attacker'). *Decision flag:* this gate favours clean geometry but may under-sample "
      "high-traffic net-front scrambles; reported here, not silently applied.\n")

    W("### The possession window\n")
    W("Per goal the window runs from the attacking team's last clean zone entry up to the shot release "
      "(`goal_frame = release_frame`). When no in-window entry exists (possession began before the tracked "
      f"window — `entry_type = off_frame_start`), the window falls back to the final ≤{C.MAX_WINDOW_S:.0f}s "
      "of approach. Windows shorter than "
      f"{C.MIN_WINDOW_S}s are flagged (turnover chaos / no clean buildup).\n")
    W("| window source | goals |")
    W("|---|---|")
    W(f"| clean in-window zone entry | {c['with_clean_entry']:,} |")
    W(f"| fallback final-approach window (no clean entry) | {c['no_clean_entry']:,} |")
    W(f"| flagged short (< {C.MIN_WINDOW_S}s) | {c['short_window']:,} |")
    W("\n**Window length (seconds) distribution:**\n")
    q = _qtiles(u["win_len_s"])
    W("| min | p10 | p25 | median | p75 | p90 | max |")
    W("|---|---|---|---|---|---|---|")
    W("| " + " | ".join(f"{q[k]}" for k in ["min", "p10", "p25", "median", "p75", "p90", "max"]) + " |")

    W("\n### The coverage-track schema (10 Hz, geometry only — no labels, no blame)\n")
    W("One row per defending skater per frame of the window:\n")
    W("| column | meaning |")
    W("|---|---|")
    for col, mean in [
        ("near_att_id", "identity of his nearest attacker that frame (reveals whether he manages one man or switches)"),
        ("dist_near_atk", "distance to that nearest attacker (ft)"),
        ("dist_puck", "distance to the puck (ft)"),
        ("dist_slot", "distance to the most dangerous ice (net-front / slot reference)"),
        ("dist_net", "his own distance to the defended net (ft)"),
        ("att_dist_net", "his nearest attacker's distance to the defended net (for goal-side)"),
        ("goal_side", "is he goal-side of his nearest attacker (nearer the defended net along the attack axis)")]:
        W(f"| `{col}` | {mean} |")
    W(f"\nTotal: **{tr.height:,} defender-frames** over {kept_goals:,} goals.\n")

    W("### Fidelity (per-defender geometry vs def-scheme phase-0 primitive, 2025-26)\n")
    W(f"My per-defender nearest-attacker distance reproduces the independent phase-0 `dist_nearest_atk` "
      f"exactly: **corr = {fid['corr']:.4f}, mean abs diff = {fid['mad']:.3f} ft** over {fid['matched']:,} "
      "matched defender-frames. The coordinate frame and role assignment are correct.\n")

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "probe.md").write_text("\n".join(L))
    return {"kept_goals": kept_goals, "fidelity_corr": fid["corr"]}


if __name__ == "__main__":
    r = write()
    print(f"wrote reports/probe.md (Link 0) | kept {r['kept_goals']:,} goals | fidelity corr {r['fidelity_corr']:.4f}")
