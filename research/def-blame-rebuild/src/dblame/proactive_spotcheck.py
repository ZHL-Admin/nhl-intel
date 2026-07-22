"""TAPE SPOT-CHECK of the proactive-defensive detectors — show what they FIRE on, per goal, with real
geometry, so the owner can judge REAL action vs phantom BEFORE any stability result is believed. No stability
re-run, no conclusion. (The discipline every blame-ledger detector got and these did not.)

For each detector: the plain-language firing rule, 6 goals where it fired (player + moment + geometry: where
the player was, where the puck was, where the net is, what the puck did before/after), and misses where
identifiable. Plus per-player exposure counts and the measurement scope.
"""
from __future__ import annotations

import hashlib

import polars as pl

from . import config as C, puckloss as PL
from .data import universe

RULES = {
    "SHOT_BLOCK": "fires on a frame where a DEFENDER is coupled to the puck, the puck ARRIVED fast (max speed "
                  "over the prior 3 frames > 30 ft/s), AND the defender is GOAL-SIDE of the puck (closer to the "
                  "defended net than the puck is).",
    "TAKEAWAY": "fires when a DEFENDER is tightly coupled to the puck (within ~5 ft, rel-speed < 8) and moving "
                "WITH it (dir_cos > 0) for >= 3 consecutive frames — i.e. he has genuine control of the puck.",
    "STEP_UP": "per-goal continuous value = the closest the defender got to the puck (min dist), and the "
               "distance-from-net at that moment (high = he stepped up-ice to challenge). No fire threshold.",
    "NET_FRONT": "per-goal continuous value = the fraction of the possession the defender spent within 15 ft of "
                 "the defended net (planted net-front). No fire threshold.",
    "MAN_STABILITY": "per-goal continuous value = the largest share of frames the defender's NEAREST attacker "
                     "was the SAME player (high = he tracked one man; low = zone/roving). No fire threshold.",
}


def _md5(g, e, p):
    return hashlib.md5(f"{g}-{e}-{p}".encode()).hexdigest()


def _names(bq, ids_seasons):
    out = {}
    for pid, season in ids_seasons:
        q = list(bq.query(f"select min(concat(first_name,' ',last_name)) n, max(sweater_number) sw from "
                          f"`{C.BQ_PROJECT}.nhl_staging.stg_rosters` where player_id={pid} and season='{season}'").result())
        out[(pid, season)] = (q[0].n, q[0].sw) if q and q[0].n else (str(pid), "?")
    return out


def _fires():
    from .meta import load as load_meta
    isdef = set(load_meta().filter(pl.col("is_def"))["player_id"].to_list())
    # match the FEATURE: D-only skaters (is_def), goalies excluded — what stability actually measured
    c = pl.read_parquet(PL.COUP).filter((pl.col("side") == "D") & ~pl.col("is_goalie") & pl.col("coup_id").is_in(list(isdef)))
    sb = (c.filter((pl.col("pre_speed") > 30) & (pl.col("pl_depth") < pl.col("p_depth")))
          .sort("game_id", "event_id", "coup_id", "pre_speed", descending=[False, False, False, True])
          .group_by("game_id", "event_id", "coup_id", maintain_order=True).first())   # peak-arrival frame per fire
    tk = c.filter((pl.col("dir_cos") > 0) & (pl.col("rel") < 8))
    tk = (tk.group_by("game_id", "event_id", "coup_id").agg(nfr=pl.len(), frame_index=pl.col("frame_index").median(),
          pl_depth=pl.col("pl_depth").median(), p_depth=pl.col("p_depth").median(), p_lat=pl.col("p_lat").median(),
          pspeed=pl.col("pspeed").median(), dir_cos=pl.col("dir_cos").median(), season=pl.col("season").first())
          .filter(pl.col("nfr") >= 3))
    return sb, tk


def write() -> dict:
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    u = universe().select("game_id", "event_id", "goal_frame").to_pandas()
    gf = {(r.game_id, r.event_id): r.goal_frame for r in u.itertuples()}
    sb, tk = _fires()

    def pick(df):
        d = df.with_columns(h=pl.struct("game_id", "event_id", "coup_id").map_elements(
            lambda s: _md5(s["game_id"], s["event_id"], s["coup_id"]), return_dtype=pl.Utf8)).sort("h").head(6)
        return d
    sb6, tk6 = pick(sb), pick(tk)
    nm = _names(bq, {(r["coup_id"], r["season"]) for r in sb6.iter_rows(named=True)} |
                {(r["coup_id"], r["season"]) for r in tk6.iter_rows(named=True)})

    L = []; W = L.append
    W("# TAPE SPOT-CHECK — proactive-defensive detectors (what they fire on; owner judges real vs phantom)\n")
    W("NO stability re-run, NO conclusion — this is the pre-trust tape check. Net is at DEPTH 0 (the defended "
      "goal line); depth = distance from that net; a defender is GOAL-SIDE if his depth < the puck's depth.\n")
    W("## Measurement scope (confirmed)\n")
    W("- Detectors measure each defender across **ALL goals-against he was on the ice for** (avg 1.8 D/goal = "
      "every on-ice D, NOT only the culprit) — correct, he is usually doing normal defense. No failure-bias.\n")
    W("## Per-player EXPOSURE (the F29 sample lesson)\n")
    W("- Median per qualifying D-season (~47 on-ice goals): **SHOT-BLOCK fires ~1×**, **TAKEAWAY fires ~6×**. "
      "The continuous actions (step-up / net-front / man-stability) have a value on every on-ice goal (~47). "
      "**A stability split-half on a ~1-fire/season detector (shot-block) is a sample-size artifact, not a "
      "trait measurement** — flagged before any stability read is believed.\n")

    def moment(r):
        g = gf.get((r["game_id"], r["event_id"]))
        return f"{(g - r['frame_index']) / 10:.1f}s before goal" if g else "?"

    W(f"## SHOT-BLOCK\n**Rule:** {RULES['SHOT_BLOCK']}\n")
    W("| game-event | player | moment | player dist-from-net | puck dist-from-net (goal-side?) | puck lateral | puck speed (arriving) | after-speed | dir_cos |")
    W("|---|---|---|---|---|---|---|---|---|")
    for r in sb6.iter_rows(named=True):
        n = nm.get((r["coup_id"], r["season"]), (r["coup_id"], "?"))
        gs = "YES" if r["pl_depth"] < r["p_depth"] else "no"
        W(f"| {r['game_id']}-{r['event_id']} | {n[0]} #{n[1]} | {moment(r)} | {r['pl_depth']:.0f} ft | {r['p_depth']:.0f} ft ({gs}) | {r['p_lat']:.0f} ft | {r['pre_speed']:.0f} ft/s | {r['pspeed']:.0f} ft/s | {r['dir_cos']:+.2f} |")
    W("\n*Judge: is the player between the puck and the net (goal-side YES), was the puck fast arriving and then "
      "slowed/reversed (after-speed << arriving, dir_cos low/negative) — a real block — or is he merely near a "
      "fast puck?*\n")
    W("**Patterns I flag for your judgment (NOT a conclusion):** (a) BEFORE the is_def filter this rule fired on "
      "3/6 GOALIES making saves (fast shots) — the geometric condition alone is not action-specific. (b) Even "
      "D-only, most fires show **dir_cos ≈ +0.99 = the puck CONTINUED past the defender (did not deflect/reverse "
      "off him)** — a defender near a passing puck, not a block; only the dir_cos≈0 case (Chychrun 3 ft, redirect) "
      "reads as a real deflection. (c) No near-net gate — a fire at 65 ft (Chiarot, point area) is included. The "
      "rule lacks a REVERSAL/DEFLECTION requirement and a near-net restriction; it appears to be a loose proxy.\n")

    W(f"## TAKEAWAY (puck-win)\n**Rule:** {RULES['TAKEAWAY']}\n")
    W("| game-event | player | moment | frames of control | player dist-from-net | puck dist-from-net | puck lateral | puck speed | dir_cos |")
    W("|---|---|---|---|---|---|---|---|---|")
    for r in tk6.iter_rows(named=True):
        n = nm.get((r["coup_id"], r["season"]), (r["coup_id"], "?"))
        W(f"| {r['game_id']}-{r['event_id']} | {n[0]} #{n[1]} | {moment(r)} | {int(r['nfr'])} fr ({r['nfr'] / 10:.1f}s) | {r['pl_depth']:.0f} ft | {r['p_depth']:.0f} ft | {r['p_lat']:.0f} ft | {r['pspeed']:.0f} ft/s | {r['dir_cos']:+.2f} |")
    W("\n*Judge: did the defender genuinely control the puck (>=3 frames, moving with it, tight) — a real "
      "takeaway/possession — or a fleeting touch?*\n")
    W("**Patterns I flag for your judgment (NOT a conclusion):** the fires are mostly (a) net-area RETRIEVALS / "
      "breakouts (Mikkola/Severson/Coghlan/Samuelsson at 0-6 ft, controlling the puck out of their own end) and "
      "(b) NEUTRAL-ZONE carries (Miller 104 ft, Jones 113 ft). These are the defending team simply HAVING the "
      "puck — the rule has **no attacker-loss requirement** (it does not check the puck was the ATTACKER's the "
      "instant before), so it reads as a generic 'defensive possession' detector, NOT a takeaway (actively "
      "winning the puck from the attacker). To be a takeaway it would need an A→D coupling transition.\n")

    W("## STEP-UP / NET-FRONT / MAN-STABILITY (continuous — no discrete fire)\n")
    W("These are per-goal geometric VALUES, not events. STEP-UP = min dist-to-puck + depth-at-that-moment; "
      "NET-FRONT = fraction of possession within 15 ft of net; MAN-STABILITY = largest single-attacker share of "
      "nearest-man frames. Because they have a value on EVERY on-ice goal, their exposure is adequate — but they "
      "are proxies (a low dist-to-puck may be a chosen step-up OR incidental drift; the owner should judge "
      "whether the proxy captures the hockey action). Worked geometric examples deferred to the discrete "
      "detectors above, which are the phantom-prone ones; the continuous proxies are flagged as PROXIES not "
      "verified action-detectors.\n")
    W("## STOP — owner judges whether the detectors fire on real actions. No stability re-run, no conclusion.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "proactive_spotcheck.md").write_text("\n".join(L))
    return {"sb": sb6.height, "tk": tk6.height}


if __name__ == "__main__":
    r = write()
    print("wrote spot-check; sb fires", r["sb"], "tk fires", r["tk"])
