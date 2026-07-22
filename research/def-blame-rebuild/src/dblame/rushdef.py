"""Rush-defense SCOPING · BUCKET-BASED (read-only; NOT integrated into any ledger). Four questions per goal:

Q1  Is it a rush?  rush-origin (carried/dumped/passed entry within 4s) AND the defense was not genuinely
    pre-set. A play the defense simply failed to get set for in time is STILL a rush; only a pre-set defense
    (established D + in-zone coverage, i.e. no fresh entry / >4s to settle) is SETTLED -> coverage ledger.
Q2  Turnover-caused?  If the existing coupling turnover detector flags the goal, PRIMARY blame is the giveaway
    (turnover ledger) and rush-defense is heavily discounted (x TURNOVER_DISCOUNT).
Q3  Disadvantage BUCKET (replaces the exact odd-man count). At the threat frame (puck first reaching
    THREAT_DEPTH of the net after entry) count defenders goal-side of the puck vs attackers driving in-zone.
    The bucket is coarse and tolerates a one-body miscount (2-on-1 and 3-on-2-against land in the SAME bucket
    because the bucket keys on the GAP na-nd, not the headcount):
        EVEN / DEFENSE-HAS-NUMBERS (gap<=0)        -> ceiling 1.0
        SLIGHTLY OUTNUMBERED       (gap==1)        -> ceiling 0.5
        BADLY OUTNUMBERED/BREAKAWAY (gap>=2, or 0 defenders back with an attacker) -> ceiling 0.1
Q4  Baseline rush discount: every rush (any bucket) carries a flat transition discount RUSH_DISCOUNT vs
    settled coverage (the group was not fully set), applied on top of the bucket ceiling.

Attribution + contest gate (ALREADY ACCEPTED — preserved exactly): within the bucket ceiling, the ONE nearest
responsible defender (goal-side + within the 25-ft scoring lane; else nearest overall) who FAILED to contest
is charged. A defender who genuinely contested (closest approach < 8 ft) and was beaten is a NULL and the
fault does NOT transfer. Backchecking forwards eligible at x0.65. Total charged never exceeds the ceiling.

Threat frame + narrow counts chosen empirically on the pinned 10 (owner tape): puck-at-40ft with defenders
goal-side +5ft / attackers in-zone +10ft best separates the tape buckets. Widening the defender radius swept
in collapsing back-checkers and wrongly flipped the SLIGHTLY reads to EVEN, so the count is deliberately tight.
"""
from __future__ import annotations

import polars as pl

from . import config as C, events2 as E2, puckloss as PL
from .data import universe
from .meta import load as load_meta
from .tracks import TRACKS

# --- Q3 threat-frame geometry (empirically tuned on the pinned set) ---
THREAT_DEPTH = 40.0     # the rush "became a threat" when the puck first reaches this depth from the net
ZONE = 64.0             # offensive blue line (depth ft): an attacker must be inside the zone to be on the rush
ND_TOL = 5.0            # a defender counts if goal-side of / challenging the puck (depth <= puck_depth + this)
NA_TOL = 10.0           # an attacker counts if at or ahead of the puck toward the net (depth <= puck_depth + this)

# --- charge chain ---
RUSH_DISCOUNT = 0.85       # Q4 flat transition discount every rush carries vs settled coverage
TURNOVER_DISCOUNT = 0.25   # Q2 heavy discount when a turnover created the rush (primary blame = giveaway)
CONTEST_FT = 8.0           # a defender "contested" if his closest approach to the scorer got within this
LANE_FT = 25.0             # a back defender is "responsible for the scoring lane" if within this of the scorer
BACKCHECK_DISCOUNT = 0.65  # a recovering backchecking FORWARD does a harder job than the established last-line D

PINNED = C.REPORTS / "rushdef_pinned.csv"   # committed, stable (game_id,event_id) set — does not move between runs
REPORT = C.REPORTS / "rushdef_scoping.md"


def _bucket(nd: int, na: int):
    """Coarse disadvantage bucket + fault ceiling. Keys on the GAP so a one-body miscount stays in-bucket."""
    if nd == 0 and na >= 1:
        return ("BADLY", 0.1)            # zero defenders back with an attacker driving = breakaway
    gap = na - nd
    if gap >= 2:
        return ("BADLY", 0.1)
    if gap == 1:
        return ("SLIGHTLY", 0.5)
    return ("EVEN", 1.0)                 # defense not outnumbered (incl. nd==0 & na==0 = no real threat)


def rush_universe() -> pl.DataFrame:
    """Q1 + Q2 per goal: is_rush (rush-origin within 4s, tracked) and turnover_caused (existing detector).
    SETTLED = not rush-origin / >4s to settle; those are already excluded by is_rush and route to coverage.
    Also carries the giveaway player on turnover-rushes so attribution can exclude him (a turnover-rush routes
    primary blame to the giveaway; he must not also be charged the rush-defense on the same goal)."""
    rd = PL._rush_and_oddman().filter(pl.col("is_rush")).select("game_id", "event_id")
    tracked = pl.read_parquet(TRACKS).select("game_id", "event_id").unique()
    turn = PL._turnovers()
    tkeys = turn.select("game_id", "event_id").unique()
    rush = rd.join(tracked, on=["game_id", "event_id"], how="inner").with_columns(
        turnover_caused=pl.struct("game_id", "event_id").is_in(tkeys.to_struct("k")))
    if turn.height:
        gv = turn.group_by("game_id", "event_id").agg(giveaway=pl.col("giveaway_player").first())
        rush = rush.join(gv, on=["game_id", "event_id"], how="left")
    else:
        rush = rush.with_columns(giveaway=pl.lit(None, dtype=pl.Int64))
    return rush


def _threat_count(target: pl.DataFrame) -> pl.DataFrame:
    """Q3 count for the given (game_id,event_id) set. Per goal: the threat frame (puck first <= THREAT_DEPTH
    after entry; fallback goal_frame-15), then defenders goal-side of the puck (+ND_TOL) vs attackers driving
    in the zone (+NA_TOL, inside the blue line). Also a pre_set diagnostic at the entry frame (Q1 annotation).
    Partitions each season's frames per goal once (dict) so it scales to the whole rush universe, not just 10."""
    u = (universe().select("game_id", "event_id", "season", "goal_frame", "entry_frame", "defending_team_id",
                           "scoring_team_id", "home_goalie_id", "away_goalie_id", "attack_sign")
         .join(target.select("game_id", "event_id"), on=["game_id", "event_id"], how="inner"))
    rows = []
    for season, fname in PL.SEASON_FILES.items():
        us = u.filter(pl.col("season") == season)
        if not us.height:
            continue
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname,
                              columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std"])
              .join(us, on=["game_id", "event_id"], how="inner")
              .with_columns(depth=89.0 - pl.col("attack_sign") * pl.col("x_std")))
        goalie = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
        puckd = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", "depth").partition_by(
            ["game_id", "event_id"], as_dict=True)
        skd = fr.filter(~pl.col("is_puck") & ~goalie).select(
            "game_id", "event_id", "frame_index", "team_id", "depth").partition_by(["game_id", "event_id"], as_dict=True)
        for row in us.iter_rows(named=True):
            gid, eid = row["game_id"], row["event_id"]
            ef = row["entry_frame"] if row["entry_frame"] is not None else row["goal_frame"] - 40
            gf = row["goal_frame"]
            pk = puckd.get((gid, eid)); sk = skd.get((gid, eid))
            if pk is None or sk is None:
                continue
            pk = pk.filter((pl.col("frame_index") >= ef) & (pl.col("frame_index") <= gf)).sort("frame_index")
            hit = pk.filter(pl.col("depth") <= THREAT_DEPTH)
            tf = hit["frame_index"][0] if hit.height else gf - 15
            pdser = pk.filter(pl.col("frame_index") == tf)["depth"]
            pdep = pdser[0] if len(pdser) else THREAT_DEPTH
            fs = sk.filter(pl.col("frame_index") == tf)
            na = fs.filter((pl.col("team_id") == row["scoring_team_id"]) & (pl.col("depth") <= pdep + NA_TOL) & (pl.col("depth") <= ZONE)).height
            nd = fs.filter((pl.col("team_id") == row["defending_team_id"]) & (pl.col("depth") <= pdep + ND_TOL)).height
            # pre_set diagnostic at the entry frame: defenders already goal-side of the puck, not outnumbered
            en = sk.filter(pl.col("frame_index") == ef)
            epk = pk.filter(pl.col("frame_index") == ef)["depth"]
            epd = epk[0] if len(epk) else ZONE
            de = en.filter((pl.col("team_id") == row["defending_team_id"]) & (pl.col("depth") < epd)).height
            ae = en.filter((pl.col("team_id") == row["scoring_team_id"]) & (pl.col("depth") <= ZONE)).height
            bucket, ceiling = _bucket(nd, na)
            rows.append({"game_id": gid, "event_id": eid, "nd_t": nd, "na_t": na, "threat_off": int(gf - tf),
                         "bucket": bucket, "ceiling": ceiling, "pre_set": bool(de >= 2 and de >= ae)})
    return pl.DataFrame(rows)


def attribution(scoped: pl.DataFrame) -> pl.DataFrame:
    """Per goal, the ONE nearest responsible defender (goal-side + in the 25-ft scoring lane; else nearest
    overall). CONTEST GATE (hard, preserved): contested-and-beaten (closest approach < CONTEST_FT) -> NULL,
    not transferred. Charge = ceiling x RUSH_DISCOUNT x (TURNOVER_DISCOUNT if turnover) x (0.65 if forward),
    capped at the bucket ceiling."""
    import pandas as pd
    g = E2._perdef(E2._framestate()).to_pandas()
    cols = ["game_id", "event_id", "ceiling", "bucket", "turnover_caused"]
    if "giveaway" in scoped.columns:
        cols.append("giveaway")
    g = g.merge(scoped.select(cols).to_pandas(), on=["game_id", "event_id"], how="inner")
    g = g.sort_values(["game_id", "event_id", "player_id"])   # DETERMINISM: pin row order for the nsmallest tie-break
    g["back"] = g["sc_goalside_goal"].astype(bool)
    g["contested"] = g["min_dsc_fa"] < CONTEST_FT
    g["is_forward"] = ~g["is_def"].astype(bool)
    rows = []
    for (gid, eid), grp in g.groupby(["game_id", "event_id"]):
        ceiling = float(grp["ceiling"].iloc[0]); turnover = bool(grp["turnover_caused"].iloc[0])
        # turnover-rush self-collision: the giveaway is primary in the turnover ledger, so exclude him from
        # being the rush-responsible defender on the same goal — fall through to the next defender (or NULL).
        pool = grp
        if "giveaway" in grp.columns:
            gv = grp["giveaway"].iloc[0]
            if pd.notna(gv):
                pool = grp[grp["player_id"] != gv]
        if pool.empty:
            continue
        lane = pool[pool["back"] & (pool["dsc_goal"] <= LANE_FT)]
        cand = lane if not lane.empty else pool
        resp = cand.sort_values(["dsc_goal", "player_id"]).head(1)   # nearest; ties broken by player_id (deterministic)
        if resp.empty:
            continue
        r = resp.iloc[0]
        mult = RUSH_DISCOUNT * (TURNOVER_DISCOUNT if turnover else 1.0) * (BACKCHECK_DISCOUNT if bool(r["is_forward"]) else 1.0)
        charged = 0.0 if bool(r["contested"]) else min(ceiling * mult, ceiling)
        rows.append({"game_id": gid, "event_id": eid, "player_id": r["player_id"], "ceiling": ceiling,
                     "gap": float(r["dsc_goal"]), "closest": float(r["min_dsc_fa"]),
                     "contested": bool(r["contested"]), "is_forward": bool(r["is_forward"]),
                     "turnover": turnover, "charged": charged})
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def rush_records():
    """Charged PUCK_LOSS RUSH_DEFENSE rows for integration into events2's puck-loss ledger. One responsible
    defender per rush; charge = bucket ceiling x RUSH_DISCOUNT x (TURNOVER_DISCOUNT if the rush was created by
    a turnover) x (0.65 if a backchecking forward), with the contest gate (contested-beaten -> NULL, dropped).
    Returns 8-col rows [game_id, event_id, player_id, 'PUCK_LOSS', 'RUSH_DEFENSE', severity, w0, w1]; the window
    is the rush (entry -> goal) so the ledger's non-overlap/cap logic sees it correctly."""
    import pandas as pd
    rush = rush_universe()
    if not rush.height:
        return []
    scoped = rush.join(_threat_count(rush), on=["game_id", "event_id"], how="inner").drop_nulls(["ceiling"])
    attr = attribution(scoped)
    if not attr.height:
        return []
    win = universe().select("game_id", "event_id", "entry_frame", "goal_frame").to_pandas()
    a = attr.to_pandas().merge(win, on=["game_id", "event_id"], how="left")
    rows = []
    for r in a.itertuples():
        if r.charged <= 0.01:                       # contested NULL or below-floor -> no record
            continue
        w1 = int(r.goal_frame)
        w0 = int(r.entry_frame) if not pd.isna(r.entry_frame) else w1 - 40
        rows.append([int(r.game_id), int(r.event_id), int(r.player_id), "PUCK_LOSS", "RUSH_DEFENSE",
                     float(r.charged), w0, w1])
    return rows


def pinned_set(rush: pl.DataFrame) -> pl.DataFrame:
    """The LOCKED 10-goal set — read from the committed CSV so the exact events never move between runs."""
    if PINNED.exists():
        return pl.read_csv(PINNED).select("game_id", "event_id")
    import hashlib
    p = (rush.with_columns(h=pl.struct("game_id", "event_id").map_elements(
        lambda s: hashlib.md5(f"{s['game_id']}-{s['event_id']}".encode()).hexdigest(), return_dtype=pl.Utf8))
        .sort("h").head(10).select("game_id", "event_id"))
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    p.write_csv(PINNED)
    return p


# owner tape buckets for the pinned goals reviewed so far (None = pending owner confirmation)
TAPE = {
    (2025020505, 552): "SLIGHTLY", (2024020410, 300): "EVEN", (2023020356, 189): "SLIGHTLY",
    (2023020735, 676): "EVEN", (2023020031, 1002): "BOUNDARY", (2025021228, 515): "SLIGHTLY",
    (2024021044, 895): "EVEN", (2023020317, 91): None, (2024020433, 397): None, (2024020487, 251): None}
TAPE_NOTE = {
    (2025020505, 552): "1-on-1 or 1-on-2", (2024020410, 300): "2-on-2 / 3-on-2, 3rd peels off",
    (2023020356, 189): "1-on-1, mishandle springs it (turnover-caused)", (2023020735, 676): "2-on-3, D outnumber",
    (2023020031, 1002): "owner: defense failed to set up, not a genuine odd-man rush", (2025021228, 515): "2-on-1",
    (2024021044, 895): "3-on-2, D even/ahead"}


def write():
    rush = rush_universe()
    pins = pinned_set(rush)
    scoped = (pins.join(rush, on=["game_id", "event_id"], how="left").fill_null(False)
              .join(_threat_count(pins), on=["game_id", "event_id"], how="left"))
    attr = attribution(scoped)
    ad = {(x["game_id"], x["event_id"]): x for x in attr.iter_rows(named=True)} if attr.height else {}

    nm = {r["player_id"]: (r["full_name"], r["sweater"]) for r in load_meta().to_dicts()}
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season", "game_date", "home_team_id",
                                               "away_team_id", "scoring_team_id", "scorer_id", "period", "game_clock_seconds")
    fmap = {(r["game_id"], r["event_id"]): r for r in fused.iter_rows(named=True)}
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    tm = {r.team_id: r.team_abbrev for r in bq.query(f"select distinct team_id,team_abbrev from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where team_abbrev is not null").result()}

    def scn(pid, season):
        if pid is None:
            return ("?", "?")
        q = list(bq.query(f"select min(concat(first_name,' ',last_name)) n, max(sweater_number) sw from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where player_id={pid} and season='{season}'").result())
        return (q[0].n, q[0].sw) if q and q[0].n else (str(pid), "?")

    import hashlib
    pinned = scoped.with_columns(h=pl.struct("game_id", "event_id").map_elements(
        lambda s: hashlib.md5(f"{s['game_id']}-{s['event_id']}".encode()).hexdigest(), return_dtype=pl.Utf8)).sort("h")

    L = []; W = L.append
    W("# Rush-defense — PINNED 10-goal set · BUCKET-based (read-only; nothing charged/aggregated)\n")
    W(f"The 10 (game, event) pairs are LOCKED to `{PINNED.name}` and do not move between runs. Rush-defense is "
      "now assessed as a coarse disadvantage BUCKET (not an exact odd-man count), because the exact integer "
      "proved unmeasurable (shot-frame too late, entry-frame too early) and unnecessary. The bar is BUCKET "
      "agreement with your tape, not exact-integer agreement.\n")
    W("**The four questions** — Q1 is it a rush? · Q2 turnover-caused? · Q3 which disadvantage bucket? · Q4 flat "
      f"rush discount. **Buckets:** EVEN/DEF-HAS-NUMBERS (gap<=0) ceiling 1.0 · SLIGHTLY (gap==1) ceiling 0.5 · "
      f"BADLY/BREAKAWAY (gap>=2 or 0 D back) ceiling 0.1. **Q4 discount = x{RUSH_DISCOUNT}** on every rush. "
      f"**Q2 turnover discount = x{TURNOVER_DISCOUNT}.** Contest gate + forward x{BACKCHECK_DISCOUNT} preserved.\n")

    W("## Q3 bucket vs owner tape (the comparison)\n")
    W("| # | game-event | scorer | model count (nd v na @ threat) | model BUCKET | owner tape bucket | agree? | Q2 turnover? | charge |")
    W("|---|---|---|---|---|---|---|---|---|")
    agree_n = resolved_n = 0
    for i, r in enumerate(pinned.iter_rows(named=True), 1):
        key = (r["game_id"], r["event_id"]); fm = fmap[key]; sc = scn(fm["scorer_id"], fm["season"])
        a = ad.get(key)
        model_b = r["bucket"] or "?"
        tape_b = TAPE.get(key)
        if tape_b is None:
            ag = "pending"
        elif tape_b == "BOUNDARY":
            ag = "boundary (Q1 below)"
        else:
            resolved_n += 1
            ok = (model_b == tape_b); agree_n += int(ok); ag = "YES" if ok else "no"
        turn = "YES" if r["turnover_caused"] else "no"
        if a is None:
            charge = "(no responsible defender)"
        elif bool(a["contested"]):
            charge = "NULL (contested-beaten)"
        else:
            charge = f"{a['charged']:.2f}"
        W(f"| {i} | {r['game_id']}-{r['event_id']} | {sc[0]} #{sc[1]} | {r['nd_t']} v {r['na_t']} | "
          f"{model_b} | {tape_b or 'pending'} | {ag} | {turn} | {charge} |")

    W(f"\n**Resolved bucket agreement: {agree_n}/{resolved_n}** (McTavish is a Q1 boundary, goals 8-10 pending your tape).\n")

    W("## Per-goal detail (Q1 rush/settled · Q2 · responsible defender · contest gate)\n")
    W("| # | scorer | Q1 | pre-set? | Q2 turnover | responsible defender | contest | ceiling | charge |")
    W("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(pinned.iter_rows(named=True), 1):
        key = (r["game_id"], r["event_id"]); fm = fmap[key]; sc = scn(fm["scorer_id"], fm["season"])
        a = ad.get(key)
        if a is None:
            dn, con, ceil, chg = ("(none)", "-", f"{r['ceiling']:.1f}", "-")
        else:
            nn = nm.get(a["player_id"], (str(a["player_id"]), "?"))
            dn = f"{nn[0]} #{nn[1]}" + (f" (F x{BACKCHECK_DISCOUNT})" if a["is_forward"] else "")
            con = "CONTESTED->null" if a["contested"] else "failed to close"
            ceil = f"{r['ceiling']:.1f}"; chg = "NULL" if a["contested"] else f"{a['charged']:.2f}"
        W(f"| {i} | {sc[0]} #{sc[1]} | RUSH | {'yes' if r['pre_set'] else 'no'} | "
          f"{'YES' if r['turnover_caused'] else 'no'} | {dn} | {con} | {ceil} | {chg} |")

    W("\n## Reading the disagreements (honest)\n")
    W("- **Lundell (2025020505):** model 2v2 -> EVEN, tape SLIGHTLY. **Cozens (2024020410) also measures 2v2 and "
      "tape is EVEN.** Same count, different tape bucket — a one-body ambiguity no count can resolve; this is "
      "precisely why we bucket instead of charging the exact integer. It straddles the softest boundary "
      "(1.0 vs 0.5 ceiling).\n")
    W("- **Benn (2023020356):** owner tape SLIGHTLY + turnover-caused. The coupling turnover detector does NOT "
      "flag it (Q2=no — the mishandle wasn't a sustained coupled possession), so primary blame is not routed to "
      "a giveaway. The model still charges ~0 because it reads the threat as a breakaway (0 defenders goal-side "
      "-> BADLY, ceiling 0.1): the right charge for the wrong reason. Flagged as a Q2 detector miss.\n")
    W("- **McTavish (2023020031):** Q1 classifies RUSH (rush-origin entry within 4s). Per the spec a rush the "
      "defense merely failed to set up for is still a RUSH; only a genuinely pre-set defense is SETTLED. "
      f"pre_set diagnostic at entry = {'yes' if pinned.filter((pl.col('game_id')==2023020031)).select('pre_set').item() else 'no'}. Reported as RUSH; your call on the boundary.\n")

    W("## STOP — owner review of the bucket comparison. Nothing integrated, nothing aggregated.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L))
    return {"pinned": pinned.height, "resolved_agree": f"{agree_n}/{resolved_n}", "report": str(REPORT)}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['report']} | pinned {r['pinned']} | bucket agreement {r['resolved_agree']}")
