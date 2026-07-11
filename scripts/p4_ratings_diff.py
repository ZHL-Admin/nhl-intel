"""P4 ratings-diff dossier generator.

Diffs the retrained downstream ratings (player_composite) against the pre-sweep
snapshot (player_composite_p4pre), attributes each mover to its dominant component
shift, computes league-level shift stats, and the retrained player_impact YoY
offense/defense Spearman. Writes docs/rebuild-reports/ratings-diff.md.
"""
import os
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
from google.cloud import bigquery

PROJECT = os.environ["GCP_PROJECT_ID"]
bq = bigquery.Client(project=PROJECT)
def q(sql): return bq.query(sql).to_dataframe()

WINDOWS = ["2025-26", "2024-25"]          # two most recent single-season windows
COMPS = [("ev_offense", "EV offense"), ("ev_defense", "EV defense"), ("pp", "PP"),
         ("pk", "PK"), ("finishing", "finishing"), ("penalty_diff", "penalty diff"),
         ("goalie_gsax", "goalie GSAx")]

# names: prefer current roster, fall back to any historical roster name
names = q(f"""
  select player_id, any_value(full_name) as name from (
    select player_id, full_name from `{PROJECT}.nhl_models.dim_current_roster`
    union all
    select player_id, concat(first_name,' ',last_name) as full_name
    from `{PROJECT}.nhl_staging.stg_rosters`
  ) where full_name is not null group by player_id
""").set_index("player_id")["name"].to_dict()
def nm(pid): return names.get(pid, f"#{pid}")

new = q(f"select * from `{PROJECT}.nhl_models.player_composite`")
old = q(f"select * from `{PROJECT}.nhl_models.player_composite_p4pre`")
key = ["player_id", "season_window"]
m = new.merge(old, on=key, suffixes=("", "_old"))
m["d_total"] = m["total"] - m["total_old"]
for c, _ in COMPS:
    m[f"d_{c}"] = m[c] - m[f"{c}_old"]

def dominant(row):
    ds = {label: row[f"d_{c}"] for c, label in COMPS}
    lab = max(ds, key=lambda k: abs(ds[k]))
    return f"{lab} {ds[lab]:+.1f}"

out = []
out.append("# P4 ratings-diff dossier — retrained `player_impact` + `shot_xg`\n")
out.append("Diff of the headline downstream player rating (`player_composite.total`, a "
           "goals-scale value) after the P3 retrains + P4 consumer re-run, vs the pre-sweep "
           "snapshot `player_composite_p4pre`. Movers are the largest `total` changes; the "
           "one-line cause is each player's single largest-moving component. "
           "Positive = the retrain raised the rating.\n")

for w in WINDOWS:
    sub = m[m["season_window"] == w].copy()
    sub["cause"] = sub.apply(dominant, axis=1)
    n = len(sub)
    out.append(f"\n## {w} — {n} players\n")
    # league-level summary of the shift
    r = np.corrcoef(sub["total"], sub["total_old"])[0, 1]
    agg_comp = {label: sub[f"d_{c}"].mean() for c, label in COMPS}
    top_drivers = sorted(agg_comp.items(), key=lambda kv: -abs(kv[1]))[:3]
    out.append(
        f"**League-level shift:** mean Δ {sub['d_total'].mean():+.2f}, median Δ "
        f"{sub['d_total'].median():+.2f}, mean |Δ| {sub['d_total'].abs().mean():.2f}, "
        f"SD {sub['d_total'].std():.2f} (goals). new-vs-old total corr r={r:.3f}, "
        f"Spearman ρ={spearmanr(sub['total'], sub['total_old']).correlation:.3f}. "
        f"{(sub['d_total'].abs() > 3).mean()*100:.0f}% of players moved >3 goals; "
        f"{(sub['d_total'] > 0).sum()} up / {(sub['d_total'] < 0).sum()} down. "
        f"Mean component contribution to the shift: "
        + ", ".join(f"{lab} {v:+.2f}" for lab, v in top_drivers) + ".\n")

    for direction, asc in [("risers", False), ("fallers", True)]:
        t = sub.sort_values("d_total", ascending=asc).head(25)
        out.append(f"\n### Top 25 {direction} — {w}\n")
        out.append("| # | player | pos | Δtotal | new | old | dominant cause |")
        out.append("|--:|---|---|--:|--:|--:|---|")
        for i, (_, x) in enumerate(t.iterrows(), 1):
            out.append(f"| {i} | {nm(x['player_id'])} | {x['position']} | "
                       f"{x['d_total']:+.1f} | {x['total']:.1f} | {x['total_old']:.1f} | {x['cause']} |")

# player_impact YoY Spearman (offense + defense), 400+ min both seasons
out.append("\n## Retrained `player_impact` — YoY Spearman (offense & defense)\n")
out.append("Consecutive single-season windows, players with 400+ min in both. Spearman of "
           "`off_impact` and `def_impact` (the P3 report gave only the offense Pearson range).\n")
imp = q(f"select player_id, season_window, off_impact, def_impact, toi_min "
        f"from `{PROJECT}.nhl_models.player_impact`")
sw = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
out.append("| transition | n | offense ρ | defense ρ |")
out.append("|---|--:|--:|--:|")
for a, b in zip(sw, sw[1:]):
    da = imp[(imp.season_window == a) & (imp.toi_min >= 400)]
    db = imp[(imp.season_window == b) & (imp.toi_min >= 400)]
    j = da.merge(db, on="player_id", suffixes=("_a", "_b"))
    ro = spearmanr(j["off_impact_a"], j["off_impact_b"]).correlation
    rd = spearmanr(j["def_impact_a"], j["def_impact_b"]).correlation
    out.append(f"| {a}→{b} | {len(j)} | {ro:.3f} | {rd:.3f} |")

path = "docs/rebuild-reports/ratings-diff.md"
with open(path, "w") as f:
    f.write("\n".join(out) + "\n")
print(f"wrote {path} ({len(out)} lines)")
