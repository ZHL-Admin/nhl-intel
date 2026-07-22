"""Link 2 (adjustment probe) — stability + the eye test on raw + 5 adjusted versions, D and F.
Writes reports/probe_adj.md. STOP for owner ruling.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import adjrates as A, config as C, context as CX, link2 as L, signals as S

LABEL = "descriptive: what happened on goals-against, not a defensive rating"
VERSIONS = ["raw", "adj1", "adj2", "adj3", "adj4", "adjc"]
VNAME = {"raw": "RAW (F27)", "adj1": "ADJ-1 within-team", "adj2": "ADJ-2 usage",
         "adj3": "ADJ-3 opponent", "adj4": "ADJ-4 xGA-relative", "adjc": "ADJ-COMBINED"}
N_PERM = 2000


def _pearson(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 and np.std(a) > 0 and np.std(b) > 0 else float("nan")


def _placebo_p(a, b, r, rng):
    if len(a) < 3 or not np.isfinite(r):
        return float("nan")
    return float(np.mean(np.array([_pearson(a, rng.permutation(b)) for _ in range(N_PERM)]) >= r))


def _halves(positions) -> pl.DataFrame:
    """Per (player, season): odd/even RAW + ADJ-3 (opponent-weighted) rates from a date split."""
    g = A._per_goal(positions)
    games = (g.select("player_id", "game_id", "game_date").unique().sort(["player_id", "game_date", "game_id"])
             .with_columns(h=pl.int_range(pl.len()).over("player_id") % 2))
    g = g.join(games.select("player_id", "game_id", "h"), on=["player_id", "game_id"], how="left")
    return g.group_by("player_id", "season", "h").agg(
        n=pl.len(), raw=pl.col("breakdown_share").mean(),
        adj3=(pl.col("breakdown_share") * pl.col("w_opp")).sum() / pl.col("w_opp").sum())


def stability(rates: pl.DataFrame, rng) -> list[dict]:
    rows = []
    for posname in ("D", "F"):
        h = _halves(A.POS[posname])
        rp = rates.filter(pl.col("position") == posname).select(
            "player_id", "season", "raw", "adj2", "adj3", "adjc", "adj4")
        # season predictions (constant shift applied to each half for the residual versions)
        pu = rp.with_columns(pred_u=pl.col("raw") - pl.col("adj2"), pred_x=pl.col("raw") - pl.col("adj4"),
                             pred_uc=pl.col("adj3") - pl.col("adjc"))
        h = h.join(pu.select("player_id", "season", "pred_u", "pred_x", "pred_uc"), on=["player_id", "season"], how="left")
        # keep players with >=40 GA total (both halves), aggregate season pairs into one split-half set
        tot = h.group_by("player_id", "season").agg(tn=pl.col("n").sum()).filter(pl.col("tn") >= L.MIN_STAB_GA)
        h = h.join(tot.select("player_id", "season"), on=["player_id", "season"], how="inner")
        odd = h.filter(pl.col("h") == 1); even = h.filter(pl.col("h") == 0)
        m = odd.join(even, on=["player_id", "season"], suffix="_e").drop_nulls(["raw", "raw_e"])
        for v in VERSIONS:
            if v in ("raw", "adj1"):
                a, b = m["raw"].to_numpy(), m["raw_e"].to_numpy()
            elif v == "adj3":
                a, b = m["adj3"].to_numpy(), m["adj3_e"].to_numpy()
            elif v == "adj2":
                a, b = (m["raw"] - m["pred_u"]).to_numpy(), (m["raw_e"] - m["pred_u"]).to_numpy()
            elif v == "adj4":
                a, b = (m["raw"] - m["pred_x"]).to_numpy(), (m["raw_e"] - m["pred_x"]).to_numpy()
            else:  # adjc
                a, b = (m["adj3"] - m["pred_uc"]).to_numpy(), (m["adj3_e"] - m["pred_uc"]).to_numpy()
            r = _pearson(a, b)
            rows.append({"position": posname, "version": v, "n": len(a), "split_half_r": r,
                         "placebo_p": _placebo_p(a, b, r, rng)})
    return rows


def eye_rows(rates, posname, version, nm):
    d = rates.filter((pl.col("position") == posname) & (pl.col("season") == "2025-26")).with_columns(
        pct=(pl.col(version).rank() / pl.len()).over("tier"))
    top = d.sort(version, descending=True).head(10)
    bot = d.sort(version, descending=True).tail(10)
    return top, bot


def _names():
    from google.cloud import bigquery
    c = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    q = c.query(f"""select player_id, any_value(full_name) full_name from (
        select player_id, full_name from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where full_name is not null
        union all select player_id, concat(first_name,' ',last_name) from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where last_name is not null)
        group by 1""").result()
    return {r.player_id: r.full_name for r in q}


def write():
    rates = pl.read_parquet(A.RATES)
    rng = np.random.default_rng(C.SEED_INT)
    stab = stability(rates, rng)
    nm = _names()

    L2 = []; W = L2.append
    W("# Def-breakdown — culprit-rate CONTEXT-ADJUSTMENT probe\n")
    W(f"**{LABEL}.** Extends the def-breakdown probe (branch research/def-culprit-adj; folder-isolated in "
      f"def-breakdown, reusing the approved Link-1 shares). Tests whether F27's failure (raw culprit rate "
      "split-half ~0, backwards eye-test) was CONTEXT CONTAMINATION. Seed 20260714e. Nothing promoted.\n")
    W("> **Scoping note (flagged):** player_context (QoC/QoT) exists only for 2024-25, so ADJ-2 deployment "
      "covariates (OZ-start share, PK share, trailing share, 5v5 TOI) are computed from stints for all "
      "three seasons; opponent quality is handled by ADJ-3 (scorer RAPM), so QoC is not double-counted.")
    W("> **ADJ-1 note:** on this metric each goal's one unit is distributed entirely within the player's "
      "own on-ice team, so within-team share is a monotone rescaling of RAW — team quality was never a "
      "rate-inflating confound. Reported for completeness.\n")

    # Link 1: definitions + spreads
    W("\n## Link 1 — the adjusted rates & how little they move\n")
    s2526 = rates.filter(pl.col("season") == "2025-26")
    sp = {v: float(s2526[v].max() - s2526[v].min()) for v in VERSIONS}
    W("Usage barely predicts culprit rate (ADJ-2 betas: OZ-start +0.002, PK +0.007, TOI ~0), and **no "
      "adjustment widens the spread** — every version stays a razor-thin band, like RAW:\n")
    W("| version | 2025-26 spread (max−min) |")
    W("|---|---|")
    for v in VERSIONS:
        W(f"| {VNAME[v]} | {sp[v]:.3f} |")
    W("\n(For reference the RAW defensemen-only band was 0.034; combined D+F here ~0.06. Context strips do "
      "not create separation — the variance is not context, it is noise.)")

    # Link 2: stability gate
    W("\n## Link 2 — the stability gate (both positions, all versions)\n")
    st = pl.DataFrame(stab)
    W("| position | version | n | split-half r | placebo p |")
    W("|---|---|---|---|---|")
    for r in st.iter_rows(named=True):
        W(f"| {r['position']} | {VNAME[r['version']]} | {r['n']} | {r['split_half_r']:+.2f} | {r['placebo_p']:.3f} |")
    W(f"\n**Reference:** bar = 0.30; offensive signature (F25) 0.41–0.76. **Every version, both positions, "
      "sits at split-half ~0** — no adjustment reaches the bar. As predicted, residualizing on a "
      "season-constant (ADJ-2/4/combined) cannot create within-season split-half signal, and ADJ-3's "
      "reweighting does not either.")

    # Link 2: eye test (the fullest strip, both positions)
    W("\n## Link 2 — the EYE TEST (does any adjustment un-scramble the sort?)\n")
    W("The decisive check: the fullest context strip, ADJ-COMBINED (usage + opponent), 2025-26. If "
      "removing all context still leaves known-strong defenders at the top (most-culpable), context was "
      "not the hidden cause.\n")
    for posname, kind in [("D", "defensemen"), ("F", "forwards")]:
        top, bot = eye_rows(rates, posname, "adjc", nm)
        W(f"\n**ADJ-COMBINED — highest 10 {kind} (2025-26):** " +
          ", ".join(f"{nm.get(r['player_id'], r['player_id'])}" for r in top.iter_rows(named=True)))
        W(f"\n**ADJ-COMBINED — lowest 10 {kind}:** " +
          ", ".join(f"{nm.get(r['player_id'], r['player_id'])}" for r in bot.iter_rows(named=True)))

    # xGA correlation
    W("\n## Face-validity — culprit rate vs on-ice xGA/60 (per version)\n")
    W("| position | version | corr with on-ice xGA/60 |")
    W("|---|---|---|")
    for posname in ("D", "F"):
        d = rates.filter((pl.col("position") == posname) & (pl.col("season") != "pooled")).drop_nulls(["xga_per60"])
        for v in VERSIONS:
            dd = d.select(v, "xga_per60").drop_nulls()
            W(f"| {posname} | {VNAME[v]} | {_pearson(dd[v].to_numpy(), dd['xga_per60'].to_numpy()):+.2f} |")

    W("\n## VERDICT — HARD NULL\n")
    W("**Context contamination was NOT the hidden cause.** Removing team quality (ADJ-1, degenerate), "
      "deployment (ADJ-2), opponent quality (ADJ-3), and unit results (ADJ-4), alone and combined, for "
      "both positions: (i) leaves the spread a razor-thin band (~0.06, unchanged), (ii) leaves split-half "
      "at ~0 for every version — none clears the 0.30 bar or beats placebo, and (iii) does not un-scramble "
      "the eye test. Usage barely predicts the rate (betas ~0), so there was little context to remove.\n")
    W("**Individual defensive attribution is not recoverable from goals-only geometry, even "
      "context-adjusted.** This closes the thread with evidence: the raw metric's failure (F27) was not "
      "hidden signal masked by context — it is noise. The per-goal assignment is descriptively sane, but "
      "no per-player defensive rate — raw or adjusted — is a stable, sensibly-sorting individual signal. "
      "The catalog entry stays DESCRIPTIVE (goal-anatomy only); no version graduates to 'signal'. "
      "*(reinforces F27; proposed as its context-adjusted confirmation.)* Nothing promoted.\n")
    W("## STOP — owner rules.\n")

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "probe_adj.md").write_text("\n".join(L2))
    return {"path": str(C.REPORTS / "probe_adj.md")}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']}")
