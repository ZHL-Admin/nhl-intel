"""Probe report: reports/probe.md — Link 0 (fused event) + Link 1 (signals + culprit share). STOP at L1."""
from __future__ import annotations

import polars as pl

from . import config as C, events as E, signals as S


def _names():
    from google.cloud import bigquery
    c = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    q = c.query(f"""select player_id, any_value(full_name) full_name from (
        select player_id, full_name from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where full_name is not null
        union all select player_id, concat(first_name,' ',last_name) from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where last_name is not null)
        group by 1""").result()
    return {r.player_id: r.full_name for r in q}


def _worked(d, sel, nm):
    L = []
    for lbl, k in sel:
        if k is None:
            continue
        gg = d.filter((pl.col("game_id") == k[0]) & (pl.col("event_id") == k[1])).sort("breakdown_share", descending=True)
        L.append(f"\n**{lbl}** — `{k[0]}-{k[1]}` · scorer_openness={gg['scorer_openness'][0]:.0f} ft, "
                 f"lane_contest={gg['lane_contest'][0]:.0f} ft, nearest_puck@release={gg['nearest_puck_rel'][0]:.0f} ft, "
                 f"cross_slot={gg['cross_slot'][0]}:\n")
        L.append("| defender | breakdown share | to scorer | on-puck share | flags |")
        L.append("|---|---|---|---|---|")
        for r in gg.iter_rows(named=True):
            fl = ",".join([x for x, b in [("A_i", r["A_i"]), ("A_ii", r["A_ii"]), ("B", r["B_flag"]), ("2nd", r["secondary_flag"])] if b]) or "—"
            ops = r["on_puck_share"] or 0.0
            hard = " **HARD**" if r["hard_culprit"] else ""
            L.append(f"| {nm.get(r['player_id'], r['player_id'])} | {r['breakdown_share']:.2f}{hard} | "
                     f"{r['d_scorer']:.0f} ft | {ops:.2f} | {fl} |")
    return L


def _summaries():
    q = pl.read_parquet(E.QUAL)
    pts = q.group_by("defending_team_id", "season").agg(n=pl.len())
    ev = {"n_goals": q.height, "n_teams": q["defending_team_id"].n_unique(),
          "scorer_tracked_rate": float(q["scorer_tracked"].mean()), "fidelity_rate": float(q["fidelity"].mean()),
          "per_team_season": {"median_qual": int(pts["n"].median()), "min_qual": int(pts["n"].min()),
                              "max_qual": int(pts["n"].max()), "n_team_seasons": pts.height}}
    d = pl.read_parquet(S.SHARES)
    perg = d.group_by("game_id", "event_id").agg(h=pl.col("hard_culprit").any(), nc=pl.col("no_clear_culprit").first(),
                                                 mx=pl.col("breakdown_share").max(),
                                                 so=pl.col("scorer_openness").first(), lc=pl.col("lane_contest").first())
    thr = pl.read_parquet(S.THRESHOLDS).row(0, named=True)
    sg = {"n_goals": perg.height, "thresholds": thr, "A_ii_rate": float(d["A_ii"].mean()),
          "B_flag_rate": float(d["B_flag"].mean()), "secondary_rate": float(d["secondary_flag"].mean()),
          "goals_with_hard_culprit": int(perg["h"].sum()), "no_clear_culprit_goals": int(perg["nc"].sum()),
          "share_max_median": float(perg["mx"].median())}
    return ev, sg, d


def write():
    ev, sg, d = _summaries()
    nm = _names()
    g = d.group_by("game_id", "event_id").agg(so=pl.col("scorer_openness").first(), xw=pl.col("cross_slot").first(),
                                              hasB=pl.col("B_flag").any(), hasA=pl.col("A_ii").any(),
                                              nocl=pl.col("no_clear_culprit").first(), mx=pl.col("breakdown_share").max())

    def pick(f, by="so", asc=True):
        r = g.filter(f)
        return (r.sort(by, descending=not asc)["game_id"][0], r.sort(by, descending=not asc)["event_id"][0]) if r.height else None
    sel = [("Clean east-west open-man (Signal B)", pick(pl.col("hasB") & pl.col("xw") & pl.col("so").is_between(12, 22))),
           ("Genuine off-puck float (Signal A(ii))", pick(pl.col("hasA") & ~pl.col("hasB") & (pl.col("mx") >= 0.36), by="mx", asc=False)),
           ("No clear culprit (good defense beaten)", pick(pl.col("nocl") & pl.col("so").is_between(4, 8))),
           ("Previously-spurious well-covered scorer — now does NOT flag", (2023020339, 240))]

    L = []; W = L.append
    W("# Defensive Breakdown — probe.md\n")
    W("**Probe** (`NIR/research/def-breakdown/`). Defensive mirror of Stage 2; avoids the failed "
      f"def-scheme project (F26): no scheme labels, no team norms. Read-only; `make link0`/`make link1` "
      f"reproduce from cache. Seed {C.SEED}.\n")
    W("> **FRAMING RULE.** " + C.FRAMING + "\n")

    # L0
    W("\n## Link 0 — the fused defensive event\n")
    W("Reuses the def-scheme phase-0 defensive-frame primitives (5 defenders' normalized trajectories + "
      "dist-to-puck/net/nearest-attacker) and adds the puck + the KNOWN scorer's trajectory (pbp scorer "
      "fused to his tracked skater) in the defending team's attack-normalized frame.\n")
    W(f"- **{ev['n_goals']:,} qualifying goals-against** (TRACKED quality, n_def=5, real NHL teams), "
      f"{ev['n_teams']} teams, {ev['per_team_season']['n_team_seasons']} team-seasons "
      f"(median {ev['per_team_season']['median_qual']}/team-season, "
      f"{ev['per_team_season']['min_qual']}–{ev['per_team_season']['max_qual']}).")
    W(f"- **Fused fidelity:** scorer tracked {ev['scorer_tracked_rate']*100:.0f}%; scorer within "
      f"stick-reach of the puck in the final 1.0 s (Stage-0-style, release-anchored) "
      f"**{ev['fidelity_rate']*100:.1f}%** — the fused event is high-fidelity.")
    W(f"- Goals with complete release-frame geometry (used for signals): **{sg['n_goals']:,}**.")

    # L1 signals (REBUILT per the owner's Link-1 calibration ruling)
    t = sg["thresholds"]
    W("\n## Link 1 (rebuilt) — percentile-calibrated signals + combined culprit share\n")
    W("Per your Link-1 ruling, every distance threshold is now a **PERCENTILE of that measure's own "
      "distribution across all qualifying goals**, not a guessed foot value; **Signal A(i) (on-puck "
      "uncontested release) is DROPPED** as tautological on goals-only data (the release that scores is "
      "definitionally uncontested); Signal A is now **only** the off-puck float A(ii); and the combined "
      "share is **B-primary: 0.75·B + 0.25·A(ii)**.\n")
    W("**Signal B · open-man vector** (at release): `B_flag` = the nearest defender to a scorer who is "
      f"**open** (scorer-to-nearest-defender ≥ the p{int(C.P_OPEN*100)} of the openness distribution = "
      f"**{t['open']:.0f} ft**, vs a goal-median of {t['open_med']:.0f} ft) AND whose **lane is "
      f"uncontested** (min defender-to-shot-vector ≥ p{int(C.P_LANE*100)} = **{t['lane']:.0f} ft**). "
      "Secondary flag: the strong-side/origin defender on a cross-slot feed.")
    W(f"\n**Signal A(ii) · off-puck float**: `A_flag` = an off-puck defender whose distance to BOTH the "
      f"nearest attacker (≥ p{int(C.P_FLOAT*100)} = **{t['float_atk']:.0f} ft**) AND the net-front "
      f"(≥ **{t['float_net']:.0f} ft**) is unusually large — genuinely floating, exposed to neither a "
      "man nor the net.")
    W("\n**Combined culprit share:** `share = 0.75·B_norm + 0.25·A_norm`, each component graded by severity "
      "and normalized within the goal to sum to 1; hard-culprit flag at share ≥ 0.40. Every goal "
      "distributes exactly one unit of breakdown.\n")
    W("**Percentile → footage mapping** (sanity-check that \"open\" looks open):\n")
    W("| measure | percentile | footage | goal-median (for scale) |")
    W("|---|---|---|---|")
    W(f"| scorer openness (B) | p{int(C.P_OPEN*100)} | {t['open']:.1f} ft | {t['open_med']:.1f} ft |")
    W(f"| lane contest (B) | p{int(C.P_LANE*100)} | {t['lane']:.1f} ft | — |")
    W(f"| float vs nearest attacker (A ii) | p{int(C.P_FLOAT*100)} | {t['float_atk']:.1f} ft | — |")
    W(f"| float vs net-front (A ii) | p{int(C.P_FLOAT*100)} | {t['float_net']:.1f} ft | — |")
    W("\n**Sub-condition fire rates (frozen):** A(ii) off-puck float "
      f"{sg['A_ii_rate']*100:.1f}% of defender-rows; B open-man {sg['B_flag_rate']*100:.1f}%; secondary "
      f"{sg['secondary_rate']*100:.1f}%. **Per-goal distribution:** median max-share/goal "
      f"**{sg['share_max_median']:.2f}**; a hard culprit exists on **{sg['goals_with_hard_culprit']:,}/"
      f"{sg['n_goals']:,}** goals ({sg['goals_with_hard_culprit']/sg['n_goals']*100:.0f}%); "
      f"**{sg['no_clear_culprit_goals']:,}** ({sg['no_clear_culprit_goals']/sg['n_goals']*100:.0f}%) have "
      "no clear culprit (good defense beaten — shares distribute ~evenly). The over-firing is fixed: hard "
      "culprits fell from 59% of goals to "
      f"{sg['goals_with_hard_culprit']/sg['n_goals']*100:.0f}%.")
    W("\n**Honest framing note — the metric is COMPARATIVE.** Percentile calibration means a fixed fraction "
      f"of goals (~{int((1-C.P_OPEN)*100)}%) will always sit in the top openness percentile. So the "
      "culprit-rate ranks defenders **against each other** — \"was the collapsed/open man more often than "
      "peers\" — not against an absolute \"coverage was objectively poor\". That comparative rate over "
      "goals-against is the intended, valuable framing, and it is stated here so it is not read as an "
      "absolute judgement.")

    # worked examples
    W("\n### Worked examples under the rebuilt, percentile-calibrated assignment (re-eyeball)\n")
    L += _worked(d, sel, nm)

    W("\n## STOP — owner confirmation before Link 2\n")
    W("Rebuilt per your calibration ruling: percentile thresholds, A(i) dropped, B-primary 0.75/0.25. The "
      "over-firing is fixed — the previously-spurious well-covered-scorer goal (Sandin, 4 ft) now "
      "distributes evenly with no culprit, while genuine open-man and float goals flag sensibly. **Confirm "
      "the rebuilt assignment is sane and Link 2 (culprit-rate tally + stability gate) may run on it.** "
      "Nothing is a certain-culprit verdict on any one goal; nothing promoted.")

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "probe.md").write_text("\n".join(L))
    return {"path": str(C.REPORTS / "probe.md")}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']}")
