"""Sanity exhibit (not a new analysis): the named 2025-26 culprit-rate leaderboard for owner eyeball.

Descriptive only — "what happened on goals-against, not a defensive rating." Uses the approved Link-1
assignment. No modeling, no claims. Uses the permitted vocabulary ("culprit rate"); the framing rule
bans "blame" in outputs, so the owner's "blame-rate" is rendered as the continuous culprit rate
(identical quantity). Parametrized by position: defensemen (D) or forwards (C/L/R).
"""
from __future__ import annotations

import polars as pl

from . import config as C, link2 as L, signals as S

LABEL = "descriptive: what happened on goals-against, not a defensive rating"
SEASON = "2025-26"


def _names():
    from google.cloud import bigquery
    c = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    q = c.query(f"""select player_id, any_value(full_name) full_name from (
        select player_id, full_name from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where full_name is not null
        union all select player_id, concat(first_name,' ',last_name) from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where last_name is not null)
        group by 1""").result()
    return {r.player_id: r.full_name for r in q}


def _rates(positions: list[str]) -> pl.DataFrame:
    """Per player-season culprit rate for the given positions (self-contained; mirrors link2.tally)."""
    d = pl.read_parquet(S.SHARES)
    gd = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "game_date")
    pos = L._position()
    x = (d.join(gd, on=["game_id", "event_id"], how="left").join(pos, on="player_id", how="left")
         .filter(pl.col("position").is_in(positions)))
    p5 = pl.read_parquet(C.NIR / "research/deployment-atlas/data/parquet/player_5v5.parquet") \
        .select("player_id", season="season_label", toi_min="toi_min", xga_per60="xga_per60")
    r = (x.group_by("player_id", "season").agg(ga=pl.len(), cont=pl.col("breakdown_share").mean(),
                                               hard=pl.col("hard_culprit").mean())
         .join(p5, on=["player_id", "season"], how="left")
         .filter((pl.col("season") == SEASON) & (pl.col("ga") >= L.MIN_RATE_GA) & pl.col("toi_min").is_not_null()))
    return r.with_columns(
        tier=pl.when(pl.col("toi_min") >= pl.col("toi_min").quantile(0.67)).then(pl.lit("hi"))
        .when(pl.col("toi_min") >= pl.col("toi_min").quantile(0.33)).then(pl.lit("mid")).otherwise(pl.lit("lo")),
        pct_in_tier=(pl.col("cont").rank() / pl.len()).over(
            pl.when(pl.col("toi_min") >= pl.col("toi_min").quantile(0.67)).then(pl.lit("hi"))
            .when(pl.col("toi_min") >= pl.col("toi_min").quantile(0.33)).then(pl.lit("mid")).otherwise(pl.lit("lo"))))


def write(positions=("C", "L", "R"), kind="forwards", top_label="top-line, heavy minutes",
          depth_label="depth / fourth line", fname="eyetest_forwards_2025_26.md"):
    d = _rates(list(positions))
    toi_hi = float(d["toi_min"].quantile(0.75))
    nm = _names()

    def tag(tier, toi_min):
        if tier == "hi" and toi_min is not None and toi_min >= toi_hi:
            return top_label
        if tier == "hi":
            return top_label.split(",")[0]
        if tier == "lo":
            return depth_label
        return ""

    top = d.sort("cont", descending=True).head(15)
    bot = d.sort("cont", descending=True).tail(15)
    Lo = []; W = Lo.append
    W(f"# Def-breakdown — 2025-26 culprit-rate eyeball exhibit ({kind})\n")
    W(f"**{LABEL}.**\n")
    W(f"Sanity check only (owner eyeball vs reputation), not a new analysis and not promoted. From the "
      f"approved Link-1 assignment; **{kind}** clearing the ≥{L.MIN_RATE_GA} on-ice-GA gate in {SEASON}, "
      f"sorted by continuous culprit rate (summed per-goal breakdown share / on-ice goals-against; the "
      "share is distributed among all five defending skaters, so a forward's rate is his portion of team "
      "breakdowns on goals he was on ice for). \"Pct in tier\" = rank within his TOI tier; on-ice xGA/60 "
      "for context. (Reminder from Link 2: this rate did NOT replicate split-half for defensemen; the same "
      "descriptive one-season caveat applies here.)\n")

    def tbl(rows, header):
        W(f"\n### {header}\n")
        W(f"| # | {kind[:-1] if kind.endswith('s') else kind} | culprit rate | pct in tier | on-ice GA | on-ice xGA/60 | tier tag |")
        W("|---|---|---|---|---|---|---|")
        for i, r in enumerate(rows.iter_rows(named=True), 1):
            xga = f"{r['xga_per60']:.2f}" if r["xga_per60"] is not None else "—"
            W(f"| {i} | {nm.get(r['player_id'], r['player_id'])} | {r['cont']:.3f} | {r['pct_in_tier']*100:.0f}% | "
              f"{r['ga']} | {xga} | {tag(r['tier'], r['toi_min'])} |")

    tbl(top, f"15 HIGHEST culprit-rate {kind} (2025-26)")
    tbl(bot, f"15 LOWEST culprit-rate {kind} (2025-26)")
    W(f"\n**{LABEL}.**\n")
    W("\n## STOP — owner eyeball review.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / fname).write_text("\n".join(Lo))
    return {"path": str(C.REPORTS / fname), "n_eligible": d.height,
            "range": (float(d["cont"].min()), float(d["cont"].max()), float(d["cont"].mean()))}


if __name__ == "__main__":
    import sys
    if "d" in sys.argv:
        r = write(("D",), "defensemen", "top-pair, heavy minutes", "depth pairing", "eyetest_2025_26.md")
    else:
        r = write()
    print(f"wrote {r['path']} ({r['n_eligible']} eligible in {SEASON}) | rate range {r['range'][0]:.3f}-{r['range'][1]:.3f} (mean {r['range'][2]:.3f})")
