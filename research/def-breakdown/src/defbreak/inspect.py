"""INSPECT — a pure reporting/dump pass over artifacts that already exist.

No modeling, no verdict, no new metrics. Reads the def-breakdown Link-1 per-goal culprit shares
(signals.SHARES) and the def-culprit-adj adjusted rates (adjrates.RATES) and dumps the actual
distributions, full leaderboards, per-goal share split, clean-subset counts, and player-by-player
half-rank stability. Output is tables and numbers. Writes reports/inspect.md + full CSVs under
reports/inspect_csv/. STOP at the end for owner review.
"""
from __future__ import annotations

import polars as pl

from . import adjrates as A, config as C, link2 as L, signals as S

VERSIONS = ["raw", "adj1", "adj2", "adj3", "adj4", "adjc"]
VNAME = {"raw": "RAW", "adj1": "ADJ-1 within-team", "adj2": "ADJ-2 usage",
         "adj3": "ADJ-3 opponent", "adj4": "ADJ-4 xGA-relative", "adjc": "ADJ-COMBINED"}
SEASONS = ["2025-26", "2024-25"]
CSVDIR = C.REPORTS / "inspect_csv"


# ----------------------------------------------------------------------------- lookups
def _names_teams():
    """player_id -> full_name; and (player_id, season) -> team_abbrev via dominant defending team."""
    from google.cloud import bigquery
    c = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    nm = {r.player_id: r.full_name for r in c.query(f"""
        select player_id, any_value(full_name) full_name from (
          select player_id, full_name from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where full_name is not null
          union all select player_id, concat(first_name,' ',last_name) from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where last_name is not null)
        group by 1""").result()}
    tmap = {r.team_id: r.team_abbrev for r in c.query(f"""
        select distinct team_id, team_abbrev from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where team_abbrev is not null""").result()}
    return nm, tmap


def _player_team(tmap) -> pl.DataFrame:
    sh = pl.read_parquet(S.SHARES).select("player_id", "season", "defending_team_id")
    dom = (sh.group_by("player_id", "season", "defending_team_id").agg(n=pl.len())
           .sort("n", descending=True).group_by("player_id", "season").first())
    return dom.with_columns(team=pl.col("defending_team_id").replace_strict(tmap, default="?")).select("player_id", "season", "team")


def _ga60() -> pl.DataFrame:
    return pl.read_parquet(A.CX.ATLAS / "player_5v5.parquet").select(
        "player_id", season="season_label", ga_per60="ga_per60")


# ----------------------------------------------------------------------------- helpers
def _stats(x: pl.Series) -> dict:
    return {"n": x.len(), "min": x.min(), "p10": x.quantile(.10), "p25": x.quantile(.25),
            "median": x.median(), "p75": x.quantile(.75), "p90": x.quantile(.90),
            "max": x.max(), "mean": x.mean(), "sd": x.std()}


def _hist(vals, bins=20, width=50) -> list[str]:
    vals = [v for v in vals if v is not None]
    if not vals:
        return ["(empty)"]
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return [f"all values = {lo:.4f} (n={len(vals)})"]
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        k = min(int((v - lo) / step), bins - 1)
        counts[k] += 1
    mx = max(counts) or 1
    out = []
    for i, ct in enumerate(counts):
        edge = lo + i * step
        bar = "#" * int(round(ct / mx * width))
        out.append(f"{edge:+.4f} | {bar} {ct}")
    return out


# ----------------------------------------------------------------------------- section builders
def leaderboard(rates, pos, season, version, nm, team, ga60) -> pl.DataFrame:
    d = (rates.filter((pl.col("position") == pos) & (pl.col("season") == season))
         .join(team, on=["player_id", "season"], how="left")
         .join(ga60, on=["player_id", "season"], how="left"))
    d = d.with_columns(pct_in_tier=(pl.col(version).rank() / pl.len()).over("tier"))
    d = d.sort(version, descending=True).with_row_index("rank", offset=1)
    return d.select(
        "rank", player=pl.col("player_id").replace_strict(nm, default=pl.col("player_id").cast(pl.Utf8)),
        team="team", position="position", tier="tier", on_ice_ga="ga",
        rate=pl.col(version).round(4), pct_in_tier=(pl.col("pct_in_tier") * 100).round(0),
        on_ice_xga60=pl.col("xga_per60").round(2), ga_per60=pl.col("ga_per60").round(2))


def dump_leaderboard_md(W, df, title, k=40):
    W(f"\n### {title}  (n eligible = {df.height})\n")
    W("| rank | player | team | pos | tier | on-ice GA | rate | pct-in-tier | on-ice xGA/60 | GA/60 |")
    W("|---|---|---|---|---|---|---|---|---|---|")
    rows = df.to_dicts()
    show = rows if df.height <= 2 * k else rows[:k] + [None] + rows[-k:]
    for r in show:
        if r is None:
            W(f"| … | *({df.height - 2*k} rows omitted — full list in CSV)* | | | | | | | | |")
            continue
        xg = f"{r['on_ice_xga60']:.2f}" if r["on_ice_xga60"] is not None else "—"
        gg = f"{r['ga_per60']:.2f}" if r["ga_per60"] is not None else "—"
        pc = f"{r['pct_in_tier']:.0f}%" if r["pct_in_tier"] is not None else "—"
        W(f"| {r['rank']} | {r['player']} | {r['team']} | {r['position']} | {r['tier']} | "
          f"{r['on_ice_ga']} | {r['rate']:.4f} | {pc} | {xg} | {gg} |")


def per_goal_shares() -> tuple[dict, list, dict]:
    sh = pl.read_parquet(S.SHARES)
    g = sh.group_by("game_id", "event_id").agg(maxshare=pl.col("breakdown_share").max())
    ms = g["maxshare"]
    stats = _stats(ms)
    hist = _hist(ms.to_list())
    n = g.height
    clear = int((ms >= 0.40).sum())
    diffuse = int(((ms >= 0.25) & (ms < 0.40)).sum())
    nocul = int((ms < 0.25).sum())
    buckets = {"n_goals": n, "clear>=0.40": clear, "diffuse 0.25-0.40": diffuse, "no-culprit<0.25": nocul,
               "clear_pct": clear / n * 100, "diffuse_pct": diffuse / n * 100, "nocul_pct": nocul / n * 100}
    return stats, hist, buckets


def clean_subset(rates, nm, team, ga60, season="2025-26") -> dict[str, pl.DataFrame]:
    """Restrict to clear-single-culprit goals (a defender's share >= 0.40) and count per player."""
    sh = pl.read_parquet(S.SHARES).filter(pl.col("season") == season)
    g = sh.group_by("game_id", "event_id").agg(maxshare=pl.col("breakdown_share").max())
    clean = sh.join(g.filter(pl.col("maxshare") >= 0.40).select("game_id", "event_id"), on=["game_id", "event_id"])
    clean = clean.filter(pl.col("breakdown_share") >= 0.40)     # the clear culprit on that goal
    cnt = clean.group_by("player_id", "season").agg(clean_culprits=pl.len())
    pos = L._position()
    base = (rates.filter(pl.col("season") == season)
            .select("player_id", "season", "position", "ga", "toi_5v5_min")
            .join(cnt, on=["player_id", "season"], how="left")
            .with_columns(clean_culprits=pl.col("clean_culprits").fill_null(0))
            .join(team, on=["player_id", "season"], how="left")
            .with_columns(per60=pl.when(pl.col("toi_5v5_min") > 0)
                          .then(pl.col("clean_culprits") / (pl.col("toi_5v5_min") / 60.0)).otherwise(None),
                          player=pl.col("player_id").replace_strict(nm, default=pl.col("player_id").cast(pl.Utf8))))
    res = {}
    for p in ("D", "F"):
        res[p] = (base.filter(pl.col("position") == p)
                  .select("player", "team", "position", "clean_culprits",
                          on_ice_ga=pl.col("ga"), per60=pl.col("per60").round(3))
                  .sort("clean_culprits", descending=True))
    return res


def half_ranks(nm, team, season="2025-26") -> dict[str, pl.DataFrame]:
    """Per player: first-half vs second-half rank for RAW and ADJ-COMBINED (odd/even games by date)."""
    rates = pl.read_parquet(A.RATES)
    res = {}
    for pos, plist in A.POS.items():
        g = A._per_goal(plist).filter(pl.col("season") == season)
        games = (g.select("player_id", "game_id", "game_date").unique()
                 .sort(["player_id", "game_date", "game_id"])
                 .with_columns(h=pl.int_range(pl.len()).over("player_id") % 2))
        g = g.join(games.select("player_id", "game_id", "h"), on=["player_id", "game_id"], how="left")
        half = g.group_by("player_id", "h").agg(
            n=pl.len(), raw=pl.col("breakdown_share").mean(),
            adj3=(pl.col("breakdown_share") * pl.col("w_opp")).sum() / pl.col("w_opp").sum())
        # combined half = adj3_half - season pred (adj3 - adjc), a constant per player
        pred = (rates.filter((pl.col("position") == pos) & (pl.col("season") == season))
                .select("player_id", pred_uc=pl.col("adj3") - pl.col("adjc"), ga="ga"))
        half = half.join(pred, on="player_id", how="inner").with_columns(adjc=pl.col("adj3") - pl.col("pred_uc"))
        h1 = half.filter(pl.col("h") == 0); h2 = half.filter(pl.col("h") == 1)
        m = h1.join(h2, on="player_id", suffix="_2").drop_nulls(["raw", "raw_2"])
        m = m.with_columns(
            raw_h1_rank=pl.col("raw").rank(method="ordinal", descending=True),
            raw_h2_rank=pl.col("raw_2").rank(method="ordinal", descending=True),
            adjc_h1_rank=pl.col("adjc").rank(method="ordinal", descending=True),
            adjc_h2_rank=pl.col("adjc_2").rank(method="ordinal", descending=True),
            player=pl.col("player_id").replace_strict(nm, default=pl.col("player_id").cast(pl.Utf8)))
        res[pos] = m.sort("ga", descending=True).select(
            "player", total_ga="ga", n_h1="n", n_h2="n_2",
            raw_h1_rank="raw_h1_rank", raw_h2_rank="raw_h2_rank",
            adjc_h1_rank="adjc_h1_rank", adjc_h2_rank="adjc_h2_rank")
    return res


# ----------------------------------------------------------------------------- write
def write():
    rates = pl.read_parquet(A.RATES)
    nm, tmap = _names_teams()
    team = _player_team(tmap)
    ga60 = _ga60()
    CSVDIR.mkdir(parents=True, exist_ok=True)

    W_ = []; W = W_.append
    W("# Def-breakdown / def-culprit-adj — INSPECT dump\n")
    W("Pure reporting pass over existing artifacts (`signals.SHARES` per-goal culprit shares; "
      "`adjrates.RATES` adjusted rates). No modeling, no verdict, no new metrics — tables and numbers "
      "only. Rate versions: RAW, ADJ-1 within-team (== RAW by construction on this metric), ADJ-2 usage, "
      "ADJ-3 opponent-quality, ADJ-4 xGA-relative, ADJ-COMBINED. Eligibility ≥25 on-ice GA. "
      "Full ranked lists are attached as CSVs under `reports/inspect_csv/`.\n")
    counts = rates.group_by("position", "season").agg(n=pl.len()).sort(["position", "season"])
    W("**Eligible player-seasons (≥25 on-ice GA):**\n")
    W("| position | season | n |")
    W("|---|---|---|")
    for r in counts.iter_rows(named=True):
        W(f"| {r['position']} | {r['season']} | {r['n']} |")

    # ---------- B. distribution shape (all versions x position x season) ----------
    W("\n## B. Distribution shape — per version × position × season\n")
    W("| position | season | version | n | min | p10 | p25 | median | p75 | p90 | max | mean | sd |")
    W("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pos in ("D", "F"):
        for season in SEASONS:
            for v in VERSIONS:
                s = _stats(rates.filter((pl.col("position") == pos) & (pl.col("season") == season))[v])
                W(f"| {pos} | {season} | {VNAME[v]} | {s['n']} | " +
                  " | ".join(f"{s[k]:+.4f}" for k in ["min", "p10", "p25", "median", "p75", "p90", "max", "mean", "sd"]) + " |")

    # text histograms (2025-26, all versions x position)
    W("\n### Text histograms (20 bins) — 2025-26\n")
    for pos in ("D", "F"):
        for v in VERSIONS:
            W(f"\n**{pos} — {VNAME[v]} (2025-26):**\n```")
            for line in _hist(rates.filter((pl.col("position") == pos) & (pl.col("season") == "2025-26"))[v].to_list()):
                W(line)
            W("```")

    # ---------- C. per-goal share distribution ----------
    W("\n## C. Per-goal share distribution (the thing under the aggregate)\n")
    st, hist, bk = per_goal_shares()
    W("Across all tracked goals-against, the **maximum single-defender share per goal** "
      "(how concentrated the culprit share is when assigned):\n")
    W("| stat | value |")
    W("|---|---|")
    for k in ["n", "min", "p10", "p25", "median", "p75", "p90", "max", "mean", "sd"]:
        W(f"| {k} | {st[k]:.4f} |" if k != "n" else f"| {k} | {st[k]} |")
    W("\n**Clarity buckets (three-way split of goals by max share):**\n")
    W("| bucket | goals | pct |")
    W("|---|---|---|")
    W(f"| clear single culprit (max ≥ 0.40) | {bk['clear>=0.40']} | {bk['clear_pct']:.1f}% |")
    W(f"| diffuse (0.25–0.40) | {bk['diffuse 0.25-0.40']} | {bk['diffuse_pct']:.1f}% |")
    W(f"| no-culprit (< 0.25) | {bk['no-culprit<0.25']} | {bk['nocul_pct']:.1f}% |")
    W(f"| **total** | **{bk['n_goals']}** | 100% |")
    W("\n**Max-share histogram (20 bins, all goals):**\n```")
    for line in hist:
        W(line)
    W("```")

    # ---------- A + E. full leaderboards (primary 2025-26 all versions; 2024-25 anchors) ----------
    W("\n## A/E. Full leaderboards — top 40 / bottom 40 (complete lists in CSV)\n")
    csv_index = []
    for pos in ("D", "F"):
        for season in SEASONS:
            for v in VERSIONS:
                df = leaderboard(rates, pos, season, v, nm, team, ga60)
                path = CSVDIR / f"lb_{pos}_{season.replace('-', '')}_{v}.csv"
                df.write_csv(path)
                csv_index.append(str(path.relative_to(C.REPORTS)))
                # markdown: 2025-26 all versions; 2024-25 only RAW + ADJ-COMBINED anchors
                if season == "2025-26" or v in ("raw", "adjc"):
                    dump_leaderboard_md(W, df, f"{pos} — {VNAME[v]} — {season}")
    W("\n**All full ranked leaderboards (every version × position × season) as CSV:**\n")
    for p in csv_index:
        W(f"- `reports/{p}`")

    # ---------- D. clean-subset preview ----------
    W("\n## D. Clean-subset preview — clear-single-culprit goals only (max share ≥ 0.40)\n")
    W("Counts only (no modeling): among goals with a clear single culprit, how many each eligible "
      "player accumulates in 2025-26, with a per-60 (clean culprits per 60 min 5v5 TOI). "
      "Full lists in CSV.\n")
    cs = clean_subset(rates, nm, team, ga60)
    for pos in ("D", "F"):
        df = cs[pos]
        path = CSVDIR / f"clean_{pos}_202526.csv"
        df.write_csv(path)
        W(f"\n### {pos} — clean-culprit count, 2025-26 (n eligible = {df.height}; full list `reports/{path.relative_to(C.REPORTS)}`)\n")
        W("| player | team | on-ice GA | clean culprits | per-60 |")
        W("|---|---|---|---|---|")
        rows = df.to_dicts()
        show = rows if df.height <= 80 else rows[:40] + [None] + rows[-40:]
        for r in show:
            if r is None:
                W(f"| … *({df.height - 80} omitted)* | | | | |")
                continue
            p60 = f"{r['per60']:.3f}" if r["per60"] is not None else "—"
            W(f"| {r['player']} | {r['team']} | {r['on_ice_ga']} | {r['clean_culprits']} | {p60} |")

    # ---------- F. per-player half-rank stability ----------
    W("\n## F. Name stability — first-half vs second-half rank (2025-26), top 40 by GA\n")
    W("Odd/even split of each player's goals-against by date; rank within each half (1 = highest rate). "
      "RAW and ADJ-COMBINED side by side, so the instability is visible player-by-player. Full lists in CSV.\n")
    hr = half_ranks(nm, team)
    for pos in ("D", "F"):
        df = hr[pos]
        path = CSVDIR / f"halfranks_{pos}_202526.csv"
        df.write_csv(path)
        W(f"\n### {pos} — half-rank table (n both-halves = {df.height}; full list `reports/{path.relative_to(C.REPORTS)}`)\n")
        W("| player | total GA | n h1 | n h2 | RAW h1 rank | RAW h2 rank | ADJ-COMB h1 rank | ADJ-COMB h2 rank |")
        W("|---|---|---|---|---|---|---|---|")
        for r in df.head(40).to_dicts():
            W(f"| {r['player']} | {r['total_ga']} | {r['n_h1']} | {r['n_h2']} | "
              f"{r['raw_h1_rank']} | {r['raw_h2_rank']} | {r['adjc_h1_rank']} | {r['adjc_h2_rank']} |")

    W("\n## STOP — owner review. (Reporting dump only; nothing modeled, judged, or promoted.)\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "inspect.md").write_text("\n".join(W_))
    return {"path": str(C.REPORTS / "inspect.md"), "csvs": len(csv_index) + 4}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']} | {r['csvs']} CSVs under reports/inspect_csv/")
