"""Puck-loss ledger REBUILD (owner-approved) — trajectory/coupling possession, whole-ice turnovers with
directness x danger severity, and odd-man-scaled rush defense. Coverage ledger is FROZEN and untouched;
this module produces ONLY the PUCK_LOSS ledger records (event types: TURNOVER, RUSH_DEFENSE).

COUPLING = possession: the puck is within stick-reach (<=6 ft) AND its velocity tracks a skater's
(relative speed <=12 ft/s — carried, not a shot/pass passing by). A fast puck near a skater is NOT his
(kills the Quinn phantom by construction). Turnover = a coupled team-A possession (>=3 frames) ending
without handing to team-A, then team-B couples, ANYWHERE on the ice (no defensive-zone restriction).

Severity (mandatory): directness x danger — a turnover only charges meaningfully when it directly and
dangerously produced the goal; a harmless neutral-zone bobble the goal only loosely follows scores ~0.
Rush defense: on a CLEAN rush (no turnover) the rush defenders carry fault scaled by the odd-man curve at
the point of danger (backcheckers counted). On a TURNOVER-RUSH the giveaway is primary; rush-defense is
further discounted.
"""
from __future__ import annotations

import hashlib

import numpy as np
import polars as pl

from . import config as C
from .data import universe

COUP = C.PARQUET / "coupling.parquet"
REC = C.PARQUET / "puckloss.parquet"
STICK = 6.0          # coupling reach (ft)
TOL = 12.0           # coupling relative speed (ft/s): puck moves WITH the carrier
GENUINE_TOL = 12.0   # any coupled frame is genuine for attribution (the coupling filter already excludes fast touches)
MINRUN = 3           # frames: a real coupled possession (>=0.3s)
RECENT_FR = 30
MAX_T2G = 10.0
DANGER_LO, DANGER_HI = None, None    # set from data
SEASON_FILES = {"2023-24": "frames_2023_24.parquet", "2024-25": "frames_2024_25.parquet", "2025-26": "frames_2025_26.parquet"}


def coupling() -> pl.DataFrame:
    """Per goal, per frame: the coupled owner (velocity-tracking within reach), and puck kinematics."""
    u = universe().select("game_id", "event_id", "season", "goal_frame", "defending_team_id",
                          "home_goalie_id", "away_goalie_id", "attack_sign")
    parts = []
    for season, fname in SEASON_FILES.items():
        us = u.filter(pl.col("season") == season)
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std", "y_std"])
              .join(us, on=["game_id", "event_id"], how="inner").filter(pl.col("frame_index") <= pl.col("goal_frame"))
              .sort(["game_id", "event_id", "frame_index"]))
        puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", "attack_sign", px="x_std", py="y_std")
        puck = puck.with_columns(vx=pl.col("px").diff().over(["game_id", "event_id"]), vy=pl.col("py").diff().over(["game_id", "event_id"]))
        puck = puck.with_columns(pspeed=(pl.col("vx") ** 2 + pl.col("vy") ** 2).sqrt() * C.HZ,
                                 p_depth=89.0 - pl.col("attack_sign") * pl.col("px"), p_lat=pl.col("attack_sign") * pl.col("py"))
        # pre_speed = the puck's max speed over the preceding 3 frames — a REBOUND arrives fast (a shot/hard
        # puck) then sits slow near the goalie; genuine control does not have a fast-arrival signature.
        gk = ["game_id", "event_id"]
        puck = puck.with_columns(pre_speed=pl.max_horizontal(
            pl.col("pspeed").shift(1).over(gk), pl.col("pspeed").shift(2).over(gk), pl.col("pspeed").shift(3).over(gk)))
        sk = fr.filter(~pl.col("is_puck")).sort(["game_id", "event_id", "player_id", "frame_index"]).with_columns(
            svx=pl.col("x_std").diff().over(["game_id", "event_id", "player_id"]),
            svy=pl.col("y_std").diff().over(["game_id", "event_id", "player_id"]))
        j = sk.join(puck, on=["game_id", "event_id", "frame_index"], how="inner").with_columns(
            dist=((pl.col("x_std") - pl.col("px")) ** 2 + (pl.col("y_std") - pl.col("py")) ** 2).sqrt(),
            rel=(((pl.col("vx") - pl.col("svx")) ** 2 + (pl.col("vy") - pl.col("svy")) ** 2).sqrt()) * C.HZ)
        # dir_cos = does the puck move WITH the player (same direction)? +1 = carried together, <=0 = the
        # puck moves independently (a loose puck near him). Closeness is not possession.
        j = j.with_columns(dir_cos=(pl.col("vx") * pl.col("svx") + pl.col("vy") * pl.col("svy")) /
                           (((pl.col("vx") ** 2 + pl.col("vy") ** 2).sqrt() * (pl.col("svx") ** 2 + pl.col("svy") ** 2).sqrt()) + 1e-9),
                           pl_depth=89.0 - pl.col("attack_sign") * pl.col("x_std"))   # the player's own distance from the defended goal line
        j = j.filter((pl.col("dist") <= STICK) & (pl.col("rel") <= TOL))
        own = (j.sort(["game_id", "event_id", "frame_index", "rel"]).group_by(["game_id", "event_id", "frame_index"], maintain_order=True).first()
               .with_columns(side=pl.when(pl.col("team_id") == pl.col("defending_team_id")).then(pl.lit("D")).otherwise(pl.lit("A")),
                             is_goalie=(pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id")))
               .select("game_id", "event_id", "frame_index", "side", "is_goalie", "rel", "pspeed",
                       "pre_speed", "dir_cos", "pl_depth", "p_depth", "p_lat", "season", coup_id="player_id"))
        parts.append(own)
    out = pl.concat(parts)
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(COUP)
    return out


def _turnovers() -> pl.DataFrame:
    """Whole-ice coupling turnovers with attribution (genuine controller / botched reception; goalie eligible)."""
    c = pl.read_parquet(COUP).sort(["game_id", "event_id", "frame_index"])
    gf = universe().select("game_id", "event_id", "goal_frame").to_pandas()
    gfmap = dict(zip(zip(gf.game_id, gf.event_id), gf.goal_frame))
    rows = []
    for (gid, eid), g in c.group_by(["game_id", "event_id"], maintain_order=True):
        s = g.to_dicts()
        goalf = gfmap.get((gid, eid))
        # coupled runs (merge same-side consecutive, gap <=2)
        runs, cur = [], None
        for r in s:
            if cur and r["side"] == cur["side"] and r["frame_index"] - cur["rows"][-1]["frame_index"] <= 2:
                cur["rows"].append(r)
            else:
                if cur:
                    runs.append(cur)
                cur = {"side": r["side"], "rows": [r]}
        if cur:
            runs.append(cur)
        # GOALIE POSSESSION (owner ruling): a genuine goalie giveaway happens when he is OUT of the crease
        # PLAYING the puck — the key detail. In the crease (depth 0-8 ft from the goal line) the puck is near
        # him because shots go to the net: that is a save/rebound, not his possession (94 of 97 flagged cases
        # were in-crease, incl Hellebuyck/Thompson). GENUINE goalie control requires BOTH: he is out of the
        # save zone (median depth OUT front >8 OR BEHIND the net <0) AND the puck moves WITH him — >=5
        # consecutive frames moving (>3), tightly coupled (rel<5), his direction (dir_cos>0). Else it is a
        # rebound (excluded). A bad rebound kicked to empty space is not captured (blind spot).
        from collections import defaultdict
        gfr = defaultdict(list)
        for r in s:
            if r["is_goalie"]:
                gfr[r["coup_id"]].append(r)
        genuine = set()
        for gpid, frs in gfr.items():
            frs.sort(key=lambda x: x["frame_index"])
            depths = sorted(x["pl_depth"] for x in frs if x["pl_depth"] is not None)
            med_depth = depths[len(depths) // 2] if depths else 3.0
            out_of_crease = med_depth > 8.0 or med_depth < 0.0
            longest = run = 0
            prev = None
            for x in frs:
                tight = (x["pspeed"] is not None and x["pspeed"] > 3 and x["rel"] < 5.0
                         and x["dir_cos"] is not None and x["dir_cos"] > 0.0)
                run = (run + 1) if (tight and prev is not None and x["frame_index"] == prev + 1) else (1 if tight else 0)
                prev = x["frame_index"]
                longest = max(longest, run)
            if out_of_crease and longest >= 5:
                genuine.add(gpid)
        for r in s:
            r["g_rebound"] = r["is_goalie"] and r["coup_id"] not in genuine
        for run in runs:
            run["len"] = len(run["rows"])
            run["is_goalie"] = all(x["is_goalie"] for x in run["rows"])
            run["genuine_len"] = sum(1 for x in run["rows"] if not x["g_rebound"])   # frames that are real possession
        # a real DEFENDING possession needs >=MINRUN genuine (non-rebound) coupled frames
        d_real = [r for r in runs if r["side"] == "D" and r["genuine_len"] >= MINRUN]
        if not d_real:
            continue
        # TURNOVER = the last sustained coupled DEFENDING possession (skater or goalie) that the defending
        # team does NOT recover (no later non-goalie coupled possession; a goalie touch is not a recovery),
        # with the goal following within MAX_T2G. Catches immediate-shot giveaways (no coupled A needed).
        turn_poss = None
        for dr in reversed(d_real):
            end = dr["rows"][-1]["frame_index"]
            if end >= goalf:
                continue
            if any(r["side"] == "D" and not r["is_goalie"] and r["len"] >= MINRUN and r["rows"][0]["frame_index"] > end for r in runs):
                continue
            if (goalf - end) / C.HZ > MAX_T2G:
                continue
            turn_poss = dr; break
        if turn_poss is None:
            continue
        # ATTRIBUTION with a COUPLING-PRECONDITION on the LOSING side (owner ruling 2026-07-16): a turnover
        # requires the defending team to have HELD genuine coupled control that then broke to the attacker. A
        # puck never coupled to the defending team before the attackers gained it — a board battle, a net-front
        # scramble, a loose puck in traffic won by the attackers — is a 50/50 the attackers won, not a giveaway.
        # POSSESSION MODEL: a defending possession is a chain of genuine (non-rebound) coupled D touches, split
        # only by a SUSTAINED attacker control run (>= A_CTRL genuine frames moving with the attacker) — brief
        # attacker touches do not end it. A possession is VALID only if it CONTAINS a control run (>= CTRL
        # frames moving WITH a defender, dir_cos>0 = held, not a lone reach/carom). The giver is the last
        # genuine D touch of the last valid possession (so a 1-frame giveaway at the tail of a held possession
        # still counts — Sillinger — while a lone scramble touch after the attacker controlled does not). If no
        # valid possession exists, the defending team never held the puck -> not a turnover.
        CTRL, A_CTRL = 2, 3
        a_sustained = []
        for run in runs:
            if run["side"] != "A":
                continue
            ag = [x for x in run["rows"] if x["rel"] <= GENUINE_TOL and x["frame_index"] < goalf
                  and x["dir_cos"] is not None and x["dir_cos"] > 0]
            if len(ag) >= A_CTRL:
                a_sustained.append((ag[0]["frame_index"], ag[-1]["frame_index"]))
        d_poss, cur = [], []
        for run in runs:
            if run["side"] != "D":
                continue
            dg = [x for x in run["rows"] if x["rel"] <= GENUINE_TOL and not x["g_rebound"] and x["frame_index"] < goalf]
            if not dg:
                continue
            if cur and any(cur[-1]["frame_index"] < a0 <= dg[0]["frame_index"] for a0, a1 in a_sustained):
                d_poss.append(cur); cur = []   # a sustained attacker control run broke the possession
            cur.extend(dg)
        if cur:
            d_poss.append(cur)
        valid = [p for p in d_poss if sum(1 for x in p if x["dir_cos"] is not None and x["dir_cos"] > 0) >= CTRL]
        if not valid:
            continue   # the defending team never HELD coupled control -> battle/scramble, not a turnover
        giver = valid[-1][-1]   # last genuine touch of the last valid defending possession
        flip = giver["frame_index"]
        t2g = (goalf - flip) / C.HZ
        if t2g > MAX_T2G:
            continue
        # botched reception (skater): a slow-arrival (<=25 ft/s) non-coupled touch after the giver -> that
        # receiver botched it; a fast incoming (>25) is a deflection, not his (stays with the passer). Bounded
        # to before any sustained attacker control run after the giver (a post-attacker touch is not his loss).
        kind = "genuine_or_passer"
        for run in runs:
            if run["side"] != "D":
                continue
            for r in run["rows"]:
                if (r["frame_index"] > giver["frame_index"] and not r["is_goalie"] and r["frame_index"] < goalf
                        and not any(giver["frame_index"] < a0 <= r["frame_index"] for a0, a1 in a_sustained)
                        and r["pspeed"] is not None and r["pspeed"] <= 25 and r["rel"] > GENUINE_TOL):
                    giver = r; kind = "botched_reception"
        # touches = attacking coupled runs between the giveaway and the goal (directness)
        touches = sum(1 for r in runs if r["side"] == "A" and flip < r["rows"][0]["frame_index"] <= goalf)
        flip_row = giver
        rows.append({"game_id": gid, "event_id": eid, "giveaway_player": giver["coup_id"], "flip_frame": flip,
                     "time_to_goal": t2g, "touches": touches, "giver_is_goalie": bool(giver["is_goalie"]),
                     "attribution_kind": kind, "turn_depth": flip_row["p_depth"], "turn_lat": flip_row["p_lat"]})
    return pl.DataFrame(rows) if rows else pl.DataFrame(schema={
        "game_id": pl.Int64, "event_id": pl.Int64, "giveaway_player": pl.Int64, "flip_frame": pl.Int64,
        "time_to_goal": pl.Float64, "touches": pl.Int64, "giver_is_goalie": pl.Boolean,
        "attribution_kind": pl.Utf8, "turn_depth": pl.Float64, "turn_lat": pl.Float64})


def _rush_and_oddman() -> pl.DataFrame:
    """Rush classification (reuse entry logic) + odd-man count at the point of danger (backcheckers counted)."""
    u = universe().select("game_id", "event_id", "season", "goal_frame", "defending_team_id",
                          "attack_sign", "entry_frame", "entry_type")
    is_rush = pl.col("entry_type").is_in(["carried", "dumped", "passed"]) & pl.col("entry_frame").is_not_null() \
        & ((pl.col("goal_frame") - pl.col("entry_frame")) <= int(4 * C.HZ))
    u = u.with_columns(is_rush=is_rush)
    # odd-man at goal_frame-15 (point of danger): defenders goal-side of the puck vs attackers in the danger lane
    parts = []
    for season, fname in SEASON_FILES.items():
        us = u.filter(pl.col("season") == season)
        fr = pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std"]) \
            .join(us.select("game_id", "event_id", "goal_frame", "defending_team_id", "attack_sign"), on=["game_id", "event_id"], how="inner")
        fr = fr.filter(pl.col("frame_index") == pl.col("goal_frame") - 15)
        pk = fr.filter(pl.col("is_puck")).select("game_id", "event_id", ppx="x_std")
        d = fr.filter(~pl.col("is_puck")).join(pk, on=["game_id", "event_id"], how="inner").with_columns(
            toward=pl.col("attack_sign") * pl.col("x_std"), ptoward=pl.col("attack_sign") * pl.col("ppx"))
        nd = d.filter((pl.col("team_id") == pl.col("defending_team_id")) & (pl.col("toward") > pl.col("ptoward"))).group_by("game_id", "event_id").agg(nd=pl.len())
        na = d.filter((pl.col("team_id") != pl.col("defending_team_id")) & (pl.col("toward") >= pl.col("ptoward") - 5)).group_by("game_id", "event_id").agg(na=pl.len())
        parts.append(nd.join(na, on=["game_id", "event_id"], how="full", coalesce=True).fill_null(0))
    om = pl.concat(parts)
    return u.join(om, on=["game_id", "event_id"], how="left").with_columns(pl.col("nd").fill_null(0), pl.col("na").fill_null(0))


def _oddman_scale(nd, na):
    """Fixed curve: nd>=na -> 1.0; na=nd+1 -> 0.5; na=nd+2 -> 0.2; na>=nd+3 or nd=0 -> ~0."""
    if nd == 0:
        return 0.0
    gap = na - nd
    return 1.0 if gap <= 0 else (0.5 if gap == 1 else (0.2 if gap == 2 else 0.0))


def turnover_records():
    """Charged turnover ledger rows for integration into events2's PUCK_LOSS ledger: returns a list of
    [game_id, event_id, player_id, 'PUCK_LOSS', 'TURNOVER', severity, flip_frame, flip_frame]."""
    import numpy as np
    tv = _turnovers()
    if not tv.height:
        return []
    rel = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "release_x", "nd_scorer_rel").to_pandas()
    u = universe().select("game_id", "event_id", "attack_sign").to_pandas()
    t = tv.to_pandas().merge(u, on=["game_id", "event_id"]).merge(rel, on=["game_id", "event_id"])
    t["scorer_depth"] = 89.0 - t["attack_sign"] * t["release_x"]
    directness = np.clip((MAX_T2G - t["time_to_goal"]) / MAX_T2G, 0, 1) / (1.0 + 0.6 * t["touches"])
    danger = np.clip((30.0 - t["scorer_depth"]) / 30.0, 0, 1) * np.clip(t["nd_scorer_rel"] / 15.0, 0.2, 1.0)
    danger = np.where(t["giver_is_goalie"], np.maximum(danger, 0.7), danger)   # genuine goalie giveaway: dangerous by origin
    t["severity"] = np.clip(directness * danger, 0, 1)
    return [[r.game_id, r.event_id, r.giveaway_player, "PUCK_LOSS", "TURNOVER", float(r.severity),
             int(r.flip_frame), int(r.flip_frame)] for r in t.itertuples() if r.severity > 0.01]


def build() -> dict:
    tv = _turnovers()
    rd = _rush_and_oddman()
    rel = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "release_x", "release_y", "nd_scorer_rel").to_pandas()
    u = universe().select("game_id", "event_id", "attack_sign", "goal_frame").to_pandas()
    import numpy as np
    tvp = tv.to_pandas().merge(u, on=["game_id", "event_id"]).merge(rel, on=["game_id", "event_id"])
    tvp["scorer_depth"] = 89.0 - tvp["attack_sign"] * tvp["release_x"]
    # DIRECTNESS x DANGER severity. directness: fewer touches + less time = more direct. danger: the resulting
    # chance (net-front + open). A harmless NZ bobble far/loosely preceding a goal -> ~0.
    directness = np.clip((MAX_T2G - tvp["time_to_goal"]) / MAX_T2G, 0, 1) / (1.0 + 0.6 * tvp["touches"])
    danger = np.clip((30.0 - tvp["scorer_depth"]) / 30.0, 0, 1) * np.clip(tvp["nd_scorer_rel"] / 15.0, 0.2, 1.0)
    danger = np.where(tvp["giver_is_goalie"], np.maximum(danger, 0.7), danger)
    tvp["severity"] = np.clip(directness * danger, 0, 1)
    recs = []
    turn_goals = set()
    for r in tvp.itertuples():
        turn_goals.add((r.game_id, r.event_id))
        if r.severity > 0.01:
            recs.append([r.game_id, r.event_id, r.giveaway_player, "PUCK_LOSS", "TURNOVER", float(r.severity)])
    # RUSH-DEFENSE: clean rush (no turnover) -> odd-man-scaled fault on defenders goal-side at danger.
    # turnover-rush -> giveaway primary (already added); rush-defense further discounted (x0.4).
    rdp = rd.to_pandas()
    for r in rdp.itertuples():
        if not r.is_rush:
            continue
        scale = _oddman_scale(int(r.nd), int(r.na))
        if scale <= 0:
            continue
        is_turnrush = (r.game_id, r.event_id) in turn_goals
        sev = scale * (0.4 if is_turnrush else 1.0) * 0.6   # 0.6 base weight; report distribution, owner tunes
        # attribute to the goal-side defenders at danger — assigned to the single nearest-net defender as
        # a placeholder unit (full rush-defense modeling of which defender is a later refinement)
        recs.append([r.game_id, r.event_id, None, "PUCK_LOSS", "RUSH_DEFENSE", float(sev)])
    out = pl.DataFrame(recs, schema=["game_id", "event_id", "player_id", "ledger", "event_type", "severity"], orient="row")
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(REC)
    tvn = out.filter(pl.col("event_type") == "TURNOVER")
    ng = universe().select(pl.struct("game_id", "event_id").n_unique()).item()
    return {"turnover_pool": tv.height, "charged_turnovers": tvn.height, "n_goals": ng,
            "charged_rate": tvn.height / ng, "rush_defense": out.filter(pl.col("event_type") == "RUSH_DEFENSE").height,
            "sev_q": {k: round(float(tvn["severity"].quantile(q)), 2) for k, q in [("p50", .5), ("p90", .9), ("max", 1.0)]} if tvn.height else {}}


if __name__ == "__main__":
    import sys
    if "coupling" in sys.argv:
        o = coupling()
        print(f"coupling frames: {o.height:,} | goals: {o.select(pl.struct('game_id','event_id').n_unique()).item():,}")
    else:
        r = build()
        print(f"turnover pool: {r['turnover_pool']:,} | CHARGED turnovers (sev>0.01): {r['charged_turnovers']:,} "
              f"of {r['n_goals']:,} ({r['charged_rate']*100:.0f}%) | rush-defense: {r['rush_defense']:,}")
        print("charged turnover severity:", r["sev_q"])
