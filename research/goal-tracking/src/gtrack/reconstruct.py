"""Extended goal-buildup reconstruction (numpy, vectorized for the full 26k-goal corpus).

Rule 7b: this REUSES the algorithm validated in research/replay-probe/src/replayprobe/reconstruct.py
(net-mouth box; arrival = first in-net frame reached by a shot flight; nearest-skater carrier with
loose-gap hysteresis; release = flight start) and EXTENDS it to emit the full connective-event detail
and derived geometry Stage 0 requires, with the handoff's fixed parameters (carrier 5.5 ft; flight
>= 40 ft/s on Savitzky-Golay-smoothed speed sustained >= 2 frames). It is a faster re-implementation of
the same logic, re-validated at Stage 0.4 -- it does not change what replay-probe validated.

LAW 2: geometry supplies CONTEXT; the scorer/assisters come from stg_play_by_play (passed in via ctx).
Nothing here overrides those labels; reconstructed carriers are descriptive.
"""
from __future__ import annotations

import numpy as np

from . import config, kinematics

CARRY = config.CARRY_RADIUS_FT
GAP = config.LOOSE_GAP_MAX
FLIGHT_FPS = config.FLIGHT_SPEED_FPS
FLIGHT_MIN = config.FLIGHT_MIN_FRAMES
NET_X, NET_BACK, NET_Y = config.NET_X, config.NET_BACK, config.NET_Y_HALF
BLUE = config.BLUE_LINE
CROWD = config.CROWD_RADIUS_FT
SCREEN_R = config.SCREEN_CREASE_RADIUS_FT
DUMP_FR = int(round(config.DUMP_MIN_SECONDS * config.HZ))


def _degenerate(n: int, smeth: str) -> dict:
    """A goal whose puck is never validly tracked: keep the row (labels live) but null all geometry."""
    return {"n_frames": n, "attack_sign": None, "smooth_method": smeth, "reconstruction_ok": False,
            "arrival_frame": None, "arrival_x": None, "arrival_y": None, "release_frame": None,
            "release_x": None, "release_y": None, "release_arrival_gap": None, "flight_detected": False,
            "segments": [], "passes": [], "entry": None, "n_passes": 0,
            "release_entities": [], "arrival_entities": [], "ew_disp_2s": None, "screen_opp": 0,
            "screen_own": 0, "screen_count_rel": 0, "nd_scorer_rel": None, "nd_scorer_1s": None,
            "goalie_depth_rel": None, "goalie_lat_speed_rel": None, "scorer_speed_recep": None,
            "scorer_speed_rel": None, "release_clock": None, "entry_to_goal": None, "rush_flag": False,
            "q_a": False, "q_b": False, "q_c_crowd": 0, "q_d": False, "recep_frame": None}


def _dense(fidx, x, y, n):
    """Scatter (frame, x, y) into dense length-n arrays with NaN where the entity is absent."""
    ax = np.full(n, np.nan); ay = np.full(n, np.nan)
    ax[fidx] = x; ay[fidx] = y
    return ax, ay


def _in_net(px, py):
    ax = np.abs(px)
    return (ax >= NET_X) & (ax <= NET_BACK) & (np.abs(py) <= NET_Y)


def _tri_contains(px, py, ax, ay, bx, by, qx, qy):
    """Point (qx,qy) inside triangle (p,a,b) via barycentric sign test (vectorized over q)."""
    d = (ay - by) * (px - bx) + (bx - ax) * (py - by)
    d = d if d != 0 else 1e-9
    wa = ((ay - by) * (qx - bx) + (bx - ax) * (qy - by)) / d
    wb = ((by - py) * (qx - bx) + (px - bx) * (qy - by)) / d
    wc = 1 - wa - wb
    return (wa >= 0) & (wb >= 0) & (wc >= 0)


def reconstruct_goal(fr, ctx) -> dict:
    """fr: polars DF for one goal [frame_index,is_puck,player_id,team_id,x_std,y_std]. ctx: labels/ids."""
    fi = fr["frame_index"].to_numpy()
    n = int(fi.max()) + 1
    ispk = fr["is_puck"].to_numpy()
    # puck dense trajectory (positions raw; velocity smoothed per 10 Hz honesty)
    p = fr.filter(fr["is_puck"])
    px, py = _dense(p["frame_index"].to_numpy(), p["x_std"].to_numpy(), p["y_std"].to_numpy(), n)
    pspeed, smeth = kinematics.speed_series(px, py)
    puck_present = ~np.isnan(px)
    if not puck_present.any():                 # puck never validly tracked in this clip (see ledger L1)
        return _degenerate(n, smeth)

    # skater rows (exclude goalies from carrier/defender geometry)
    goalies = {g for g in (ctx.get("home_goalie_id"), ctx.get("away_goalie_id")) if g}
    s = fr.filter(~fr["is_puck"] & fr["player_id"].is_not_null())
    s_fi = s["frame_index"].to_numpy(); s_pid = s["player_id"].to_numpy()
    s_tm = s["team_id"].to_numpy(); s_x = s["x_std"].to_numpy(); s_y = s["y_std"].to_numpy()
    # per-player dense trajectories
    players = {}
    for pid in np.unique(s_pid):
        m = s_pid == pid
        xarr, yarr = _dense(s_fi[m], s_x[m], s_y[m], n)
        players[int(pid)] = (xarr, yarr, int(s_tm[m][0]))

    # ---- carrier per frame: nearest non-goalie skater within CARRY of the puck ----
    non_g = ~np.isin(s_pid, list(goalies)) if goalies else np.ones(len(s_pid), bool)
    cd = np.hypot(s_x - px[s_fi], s_y - py[s_fi])  # distance skater->puck at its frame
    valid = non_g & (cd <= CARRY) & puck_present[s_fi]
    carrier = np.full(n, -1, np.int64); carrier_team = np.full(n, -1, np.int64); cdist = np.full(n, np.inf)
    order = np.lexsort((cd, s_fi))  # by frame, then distance
    seen = set()
    for i in order:
        if not valid[i]:
            continue
        f = int(s_fi[i])
        if f in seen:
            continue
        seen.add(f); carrier[f] = int(s_pid[i]); carrier_team[f] = int(s_tm[i]); cdist[f] = cd[i]

    # ---- arrival = first in-net frame reached by a shot flight (validated) ----
    innet = _in_net(px, py)
    dn = np.abs(np.abs(px) - 89.0)
    flight = (pspeed >= FLIGHT_FPS) & puck_present
    # net-ward flight frames: dn not increasing
    netward = np.ones(n, bool); netward[1:] = dn[1:] <= dn[:-1] + 1.0
    flt = flight & netward
    net_frames = np.where(innet)[0]
    arrival = None
    for i in net_frames:
        if any(flt[max(1, i - 6):i + 1]):
            arrival = int(i); break
    if arrival is None and len(net_frames):
        # jam-in fallback: first in-net frame worked in by a carrier within the prior 3 frames
        for i in net_frames:
            if np.any(carrier[max(0, i - 3):i + 1] >= 0):
                arrival = int(i); break
        if arrival is None:
            arrival = int(net_frames[0])
    if arrival is None:
        arrival = int(np.nanargmin(dn))
    attack_sign = 1.0 if px[arrival] > 0 else -1.0
    gl_x = 89.0 * attack_sign

    # ---- release: flight-start of the terminal fast run ending at arrival (>=40ft/s, >=2 frames) ----
    flight_detected = False; release = arrival
    i = arrival
    run = []
    j = arrival
    while j >= 1 and flt[j]:
        run.append(j); j -= 1
    if len(run) >= FLIGHT_MIN:
        flight_detected = True; release = int(min(run))
    else:
        # walked-in/tucked goal: fall back to last controlled frame before arrival
        for f in range(arrival, -1, -1):
            if carrier[f] >= 0:
                release = f; break
    rel_gap = arrival - release

    # geometry snapshots (all entities at release & arrival)
    def _entities(f):
        out = []
        if puck_present[f]:
            out.append({"id": 1, "team": None, "x": float(px[f]), "y": float(py[f]), "is_puck": True})
        for pid, (xa, ya, tm) in players.items():
            if not np.isnan(xa[f]):
                out.append({"id": pid, "team": tm, "x": float(xa[f]), "y": float(ya[f]), "is_puck": False})
        return out
    rel_ent, arr_ent = _entities(release), _entities(arrival)

    # ---- possession segments (hysteresis: bridge <=GAP loose frames within one player's run) ----
    segs = []  # [pid, team, start, end]
    for f in range(n):
        c = carrier[f]
        if c < 0:
            continue
        if segs and segs[-1][0] == c and (f - segs[-1][3]) <= GAP + 1:
            segs[-1][3] = f
        else:
            segs.append([int(c), int(carrier_team[f]), f, f])

    # ---- passes: consecutive segments, same team, different player ----
    passes = []
    for a, b in zip(segs, segs[1:]):
        if a[1] == b[1] and a[0] != b[0]:
            sf, ef = a[3], b[2]
            passes.append({"passer_id": a[0], "receiver_id": b[0], "team_id": a[1],
                           "start_frame": sf, "end_frame": ef,
                           "start_x": float(px[sf]) if puck_present[sf] else None,
                           "start_y": float(py[sf]) if puck_present[sf] else None,
                           "end_x": float(px[ef]) if puck_present[ef] else None,
                           "end_y": float(py[ef]) if puck_present[ef] else None})

    # ---- final continuous possession + zone entry ----
    # The final continuous possession is broken only by a REAL defending turnover (a defending-team
    # possession segment >= 3 frames), not by brief loose pucks in an offensive-zone cycle. It starts
    # right after the last such turnover before the shot (else at the clip start).
    scoring_team = ctx.get("scoring_team_id")
    def_turnovers = [sg[3] for sg in segs if sg[1] != scoring_team and (sg[3] - sg[2] + 1) >= 3 and sg[3] < release]
    term_start = (max(def_turnovers) + 1) if def_turnovers else 0
    entry = None
    span = np.arange(term_start, arrival + 1)
    # first crossing of attacking blue line into O-zone within the span
    ent_frame = None
    for f in span[1:]:
        if not (puck_present[f] and puck_present[f - 1]):
            continue
        prev_o = px[f - 1] * attack_sign > BLUE
        cur_o = px[f] * attack_sign > BLUE
        if (not prev_o) and cur_o:
            ent_frame = int(f); break
    if ent_frame is None:
        # no crossing: clip began with possession already in the O-zone
        if puck_present[term_start] and px[term_start] * attack_sign > BLUE:
            entry = {"frame": None, "x": None, "y": None, "carrier_id": None, "entry_type": "off_frame_start"}
    else:
        # classify
        etype = "dumped"
        carried = carrier[ent_frame] >= 0 and carrier_team[ent_frame] == scoring_team
        passed = any(pz["team_id"] == scoring_team and pz["start_x"] is not None and pz["end_x"] is not None and
                     (pz["start_x"] * attack_sign <= BLUE) and (pz["end_x"] * attack_sign > BLUE) and
                     pz["start_frame"] <= ent_frame <= pz["end_frame"] + GAP for pz in passes)
        if passed:
            etype = "passed"
        elif carried:
            etype = "carried"
        else:
            after = carrier[ent_frame:ent_frame + DUMP_FR + 1]
            etype = "dumped" if np.all(after < 0) else "carried"
        entry = {"frame": ent_frame, "x": float(px[ent_frame]), "y": float(py[ent_frame]),
                 "carrier_id": int(carrier[ent_frame]) if carrier[ent_frame] >= 0 else None, "entry_type": etype}

    entry_to_goal = None
    if entry and entry["frame"] is not None:
        entry_to_goal = (arrival - entry["frame"]) / config.HZ
    rush_flag = (entry_to_goal is not None) and (entry_to_goal <= config.RUSH_FLAG_SECONDS)

    # ================= derived geometry =================
    scorer = ctx.get("scorer_id")
    def_goalie = ctx.get("def_goalie_id")   # beaten goalie (pbp goalie_in_net_id)

    def pos(pid, f):
        pl = players.get(int(pid)) if pid else None
        if pl is None or np.isnan(pl[0][f]):
            return None
        return pl[0][f], pl[1][f]

    # ew_disp_2s: max lateral (y) puck swing crossing the slot midline in the 2.0s before release
    w0 = max(0, release - 20)
    wy = py[w0:release + 1]; wy = wy[~np.isnan(wy)]
    ew_disp_2s = float(wy.max() - wy.min()) if wy.size and (wy.min() < 0 < wy.max()) else 0.0

    # screens at release: bodies in triangle(puck,left post,right post) AND within 10ft of crease center
    lpx, lpy, rpx, rpy = gl_x, -3.0, gl_x, 3.0
    ccx, ccy = gl_x, 0.0
    screen_opp = screen_own = 0
    for pid, (xa, ya, tm) in players.items():
        xf, yf = xa[release], ya[release]
        if np.isnan(xf) or pid in goalies:
            continue
        if np.hypot(xf - ccx, yf - ccy) <= SCREEN_R and _tri_contains(px[release], py[release], lpx, lpy, rpx, rpy, xf, yf):
            if tm == scoring_team:
                screen_own += 1
            else:
                screen_opp += 1
    screen_count_rel = screen_opp + screen_own

    # nearest-defender-to-scorer at release and 1.0s prior
    def nd_scorer(f):
        sp = pos(scorer, f)
        if sp is None:
            return None
        best = np.inf
        for pid, (xa, ya, tm) in players.items():
            if tm == scoring_team or pid in goalies or np.isnan(xa[f]):
                continue
            best = min(best, np.hypot(xa[f] - sp[0], ya[f] - sp[1]))
        return float(best) if np.isfinite(best) else None
    nd_scorer_rel = nd_scorer(release)
    nd_scorer_1s = nd_scorer(max(0, release - 10))

    # goalie depth along puck->goalie ray, and lateral speed at release
    goalie_depth_rel = goalie_lat_speed_rel = None
    if def_goalie and int(def_goalie) in players:
        gx, gy, _ = players[int(def_goalie)]
        if not np.isnan(gx[release]) and puck_present[release]:
            gpos = np.array([gx[release], gy[release]]); ppos = np.array([px[release], py[release]])
            u = gpos - ppos; nu = np.linalg.norm(u)
            if nu > 1e-6:
                u = u / nu
                foot = np.array([gl_x, gpos[1]])
                goalie_depth_rel = float(abs(np.dot(gpos - foot, u)))
        gls = kinematics.lateral_speed_series(gy)
        if not np.isnan(gy[release]):
            goalie_lat_speed_rel = float(gls[release])

    # scorer speeds at reception (start of terminal scorer possession) and at release
    scorer_speed_rel = scorer_speed_recep = release_clock = None
    recep_frame = None
    if scorer:
        sc_segs = [sg for sg in segs if sg[0] == scorer and sg[2] <= release]
        if sc_segs:
            recep_frame = sc_segs[-1][2]
            release_clock = (release - recep_frame) / config.HZ
        sp = players.get(int(scorer))
        if sp is not None:
            ss = kinematics.speed_series(sp[0], sp[1])[0]
            if not np.isnan(sp[0][release]):
                scorer_speed_rel = float(ss[release])
            if recep_frame is not None and not np.isnan(sp[0][recep_frame]):
                scorer_speed_recep = float(ss[recep_frame])

    # ================= clip-quality inputs =================
    # a: scorer within 5.5ft of puck at any frame in final 1.5s pre-release
    q_a = False
    if scorer and int(scorer) in players:
        sx_, sy_, _ = players[int(scorer)]
        for f in range(max(0, release - 15), release + 1):
            if not np.isnan(sx_[f]) and puck_present[f] and np.hypot(sx_[f] - px[f], sy_[f] - py[f]) <= CARRY:
                q_a = True; break
    # b: no puck gap > 0.5s (5 frames) in the final 5.0s ending at arrival
    w = puck_present[max(0, arrival - 50):arrival + 1]
    maxgap = run_len = 0
    for v in w:
        run_len = 0 if v else run_len + 1
        maxgap = max(maxgap, run_len)
    q_b = maxgap <= 5
    # c_crowd: non-goalie bodies within 5.5ft of puck at release
    q_c_crowd = 0
    for pid, (xa, ya, tm) in players.items():
        if pid in goalies or np.isnan(xa[release]) or not puck_present[release]:
            continue
        if np.hypot(xa[release] - px[release], ya[release] - py[release]) <= CROWD:
            q_c_crowd += 1
    q_d = flight_detected

    return {
        "n_frames": n, "attack_sign": attack_sign, "smooth_method": smeth, "reconstruction_ok": True,
        "arrival_frame": arrival, "arrival_x": float(px[arrival]) if puck_present[arrival] else None,
        "arrival_y": float(py[arrival]) if puck_present[arrival] else None,
        "release_frame": release, "release_x": float(px[release]) if puck_present[release] else None,
        "release_y": float(py[release]) if puck_present[release] else None,
        "release_arrival_gap": rel_gap, "flight_detected": flight_detected,
        "segments": [{"player_id": a, "team_id": t, "start_frame": s0, "end_frame": e0} for a, t, s0, e0 in segs],
        "passes": passes, "entry": entry, "n_passes": len(passes),
        "release_entities": rel_ent, "arrival_entities": arr_ent,
        "ew_disp_2s": ew_disp_2s, "screen_opp": screen_opp, "screen_own": screen_own,
        "screen_count_rel": screen_count_rel, "nd_scorer_rel": nd_scorer_rel, "nd_scorer_1s": nd_scorer_1s,
        "goalie_depth_rel": goalie_depth_rel, "goalie_lat_speed_rel": goalie_lat_speed_rel,
        "scorer_speed_recep": scorer_speed_recep, "scorer_speed_rel": scorer_speed_rel,
        "release_clock": release_clock, "entry_to_goal": entry_to_goal, "rush_flag": bool(rush_flag),
        "q_a": bool(q_a), "q_b": bool(q_b), "q_c_crowd": int(q_c_crowd), "q_d": bool(q_d),
        "recep_frame": recep_frame,
    }
