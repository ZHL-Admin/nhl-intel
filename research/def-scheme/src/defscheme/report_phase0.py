"""Phase 0 report: reports/phase0.md — inventory, primitive schema, coverage, quality filtering."""
from __future__ import annotations

import datetime as dt
import glob

import polars as pl

from . import config as C

PRIM_SCHEMA = [
    ("game_id, event_id, season", "goal-against identity (Stage 0 key)"),
    ("defending_team_id / scoring_team_id", "scored-on team / attacking team"),
    ("frame_index", "10 Hz frame within the buildup"),
    ("player_id", "a DEFENDING skater (goalies excluded)"),
    ("strength_state / n_def", "ice strength / defending skaters present (pentagon size; 5 at 5v5)"),
    ("x_norm, y_norm", "position, attack-direction normalized (defended net at +89,0)"),
    ("dist_net", "distance to the DEFENDED net"),
    ("dist_puck, dx_puck, dy_puck", "position relative to the puck"),
    ("off_centroid, team_spread", "distance to defenders' centroid / mean spread (pentagon shape)"),
    ("dist_nearest_atk", "distance to the nearest attacker"),
    ("zone", "dzone (x_norm>=25) / neutral / ozone"),
    ("puck_side", "strong (same y-side as puck) / weak"),
    ("low_high", "low (x_norm>=54, near net) / high / na"),
]


def _prims() -> pl.DataFrame:
    files = sorted(glob.glob(str(C.PARQUET / "def_prim_*.parquet")))
    return pl.concat([pl.read_parquet(f) for f in files]) if files else pl.DataFrame()


def write():
    p = _prims()
    fused = pl.read_parquet(C.GT_FUSED)
    tracked = int((fused["q_a"] & fused["q_b"]).sum())

    L = []; W = L.append
    W("# Phase 0 — Scaffold, inventory, defensive-frame primitives\n")
    W("**Defensive Scheme & Role** (`NIR/research/def-scheme/`). Read-only over goal-tracking + prior "
      f"research; own venv; `make phase0` reproduces from cache. Seed {C.SEED}.\n")
    W("> **" + C.LAW_1 + "**\n")
    W("> **" + C.LAW_2 + "**\n")

    # 0.2 inventory
    W("\n## 0.2 Inventory (read-only inputs)\n")
    W("| input | path | status | timestamp |")
    W("|---|---|---|---|")
    for name, path in [("goal-tracking fused_goals", C.GT_FUSED), ("goal_events", C.GT_EVENTS),
                       ("frame cache (2023-24)", C.GT_FRAMES_DIR / "frames_2023_24.parquet"),
                       ("Atlas stints", C.ATLAS_STINTS), ("System Effects regime ledger", C.SYSFX_REGIME),
                       ("System Effects team fingerprints", C.SYSFX_FP)]:
        ex = path.exists()
        ts = dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if ex else "—"
        W(f"| {name} | {str(path).split('NIR/')[-1]} | {'OK' if ex else 'MISSING'} | {ts} |")
    chem = glob.glob(str(C.NIR / "research/chemistry/data/parquet/pairs/*.parquet"))
    W(f"| Chemistry pairs corpus | research/chemistry/data/parquet/pairs/ | {'OK' if chem else 'MISSING'} | "
      f"{len(chem)} season files |")
    W("\n**`gtrack.api` confirmation:** `team_goals(team, side='against')` returns each team's goals-against "
      "(fused rows with goalie_id, home/away/scoring team, attack_sign, q_a/q_b). Frames for those goals "
      "are read from the Stage-0 frame cache (`frames_<season>.parquet`) keyed by (game_id, event_id) — "
      "the API surfaces the goal identities; the 10 Hz frames come from the Stage-0 cache (read-only). "
      "Defensive geometry uses the goal-tracking 10 Hz conventions (positions raw, velocities SavGol-"
      "smoothed; Phase 0 is positional only).")

    # 0.3 primitive schema + coverage
    W("\n## 0.3 Defensive-frame primitive schema\n")
    W("Per goal-against, per frame, per DEFENDING skater, in the defending team's frame (attack-direction "
      "normalized so the DEFENDED net is at (+89, 0)). **Geometry only — no scheme or role labels (Law 2).**\n")
    W("| field | meaning |")
    W("|---|---|")
    for f, m in PRIM_SCHEMA:
        W(f"| `{f}` | {m} |")

    if p.height:
        W("\n## Coverage & quality filtering\n")
        W(f"- **Universe: TRACKED goals** (Stage 0 a∧b) — {tracked:,}/{fused.height:,} "
          f"({tracked/fused.height*100:.1f}%) of all goals; carrier/quality filter reused from Stage 0.")
        gg = p.select("game_id", "event_id").unique().height
        W(f"- **{p.height:,} defender-frame rows** across **{gg:,} goals-against** and "
          f"**{p['defending_team_id'].n_unique()} defending teams**.")
        bs = p.group_by("season").agg(rows=pl.len(), goals=pl.col("game_id").n_unique()).sort("season")
        W("\n| season | defender-frames | goals-against |")
        W("|---|---|---|")
        for r in bs.iter_rows(named=True):
            W(f"| {r['season']} | {r['rows']:,} | {r['goals']:,} |")
        # per team-season coverage distribution
        ts = p.group_by("defending_team_id", "season").agg(ga=pl.col("game_id").n_unique())
        real = ts.filter(pl.col("ga") >= 20); exhib = ts.filter(pl.col("ga") < 20)
        W(f"\n**Per team-season goals-against** (real NHL team-seasons, ≥20 GA): "
          f"median {int(real['ga'].median())}, p10 {int(real['ga'].quantile(.1))}, "
          f"p90 {int(real['ga'].quantile(.9))}, min {int(real['ga'].min())}, max {int(real['ga'].max())} "
          f"({real.height} team-seasons across {real['defending_team_id'].n_unique()} NHL teams). "
          "(Phase 1 sets the per-situation min-sample gate.)")
        exids = sorted(exhib["defending_team_id"].unique().to_list())
        W(f"\n**Coverage caveat — exhibition rosters flagged:** {exhib.height} team-seasons have <20 GA "
          f"(team-ids {exids}) — these are **All-Star Game** (7801–7806) and **4 Nations / international** "
          "(60s) exhibition rosters whose goals are in the corpus. They carry non-standard team-ids and a "
          "different (exhibition) scheme context; **Phase 1's min-sample gate excludes them** and they are "
          "not part of the NHL team-scheme universe.")
        # strength + situation distributions
        st = p.group_by("n_def").len().sort("len", descending=True)
        W("\n**Defending skaters present (n_def):** " + ", ".join(f"{r['n_def']}={r['len']:,}" for r in st.head(5).iter_rows(named=True))
          + " (n_def=5 is the clean 5v5 pentagon; other counts are special-teams, flagged for Phase 1).")
        for col in ["zone", "puck_side", "low_high"]:
            dd = p.group_by(col).len().sort("len", descending=True)
            W(f"- **{col}:** " + ", ".join(f"{r[col]}={r['len']:,}" for r in dd.iter_rows(named=True)) + ".")
        W(f"\n**Primitive sanity:** median dist_net {p['dist_net'].median():.1f} ft, "
          f"median dist_puck {p['dist_puck'].median():.1f} ft, median dist_nearest_atk "
          f"{p['dist_nearest_atk'].drop_nulls().median():.1f} ft, median team_spread {p['team_spread'].median():.1f} ft.")

    W("\n## STOP — Phase 0 for owner review\n")
    W("Primitives built (geometry only). **Next (Phase 1, on owner go):** aggregate into the coverage "
      "signature with the goals-only bias mitigation (league baseline + offensive-goals cross-view). "
      "No scheme claim is made in Phase 0.")

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "phase0.md").write_text("\n".join(L))
    return {"path": str(C.REPORTS / "phase0.md"), "rows": p.height if p.height else 0}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']} ({r['rows']:,} defender-frame rows)")
