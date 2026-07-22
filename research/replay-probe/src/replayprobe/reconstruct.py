"""Confirmation build-probe (descriptive, no claims): reconstruct the connective tissue of a goal
buildup from the materialized 10 Hz frames, and validate it by eye against the recorded scorer/assists.

The premise of Goal Anatomy is that the trajectories yield what play-by-play lacks — puck-carrier by
frame, passes (possession moving between same-team players), zone entries, and the shot release/arrival.
The decisive eye-check: the reconstructed FINAL carrier before the shot should be the recorded SCORER,
and the carriers immediately before should be the recorded ASSISTERS. If those match on known goals,
the reconstruction is faithful.

Reads the nhl_staging views (read-only), caches the sample locally. Reconstruction is heuristic — its
honest error modes (possession ambiguity in scrums, deflections, no true carrier during loose pucks)
are reported. Needs BQ creds; run with a BigQuery-capable interpreter.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"
CARRY_RADIUS_FT = 4.5        # a skater "carries" the puck when it is within this of him (stick reach)
RELEASE_RADIUS_FT = 5.5      # slightly looser: last stick contact before the shot flight
FLIGHT_SPEED = 3.5           # ft/frame (35 ft/s) -- the puck is in shot flight, not being carried
LOOSE_GAP_MAX = 4            # frames (0.4 s) of loose puck bridged within one possession
BLUE_LINE = 25.0            # offensive blue line at x_std = +/-25
NET_X = 88.5                # goal line |x_std|~89; the net box is GOAL_LINE..NET_BACK, |y|<=NET_Y_HALF
NET_BACK = 93.0            # back of the net ~40in behind the line; beyond this = behind-net/end boards
NET_Y_HALF = 3.5
CROWD_RADIUS_FT = 8.0        # skaters within this of the puck at arrival = net-front crowd


def _client():
    import sys
    ROOT = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(ROOT / "research" / "deployment-atlas" / "src"))
    from atlas import sources
    from google.cloud import bigquery
    return bigquery.Client.from_service_account_json(str(sources.SA_KEYFILE), project=sources.BQ_PROJECT), sources.BQ_PROJECT


def pull_sample(n_per_season: int = 5) -> pl.DataFrame:
    """Sample goals with assists (5v5), spread across seasons, + their frames + scorer/assists."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_f = CACHE / "reconstruct_sample.parquet"
    meta_f = CACHE / "reconstruct_meta.json"
    if cache_f.exists() and meta_f.exists():
        return pl.read_parquet(cache_f)
    c, P = _client()
    # goals with 2 assists, 5v5, regular season only (game_id digits 5-6 = '02'), spread across seasons
    goals = list(c.query(f"""
      select season, game_id, event_id, scoring_player_id, assist1_player_id, assist2_player_id
      from `{P}.nhl_staging.stg_play_by_play`
      where type_desc_key='goal' and situation_code='1551'
        and assist1_player_id is not null and assist2_player_id is not null
        and season in ('2023-24','2024-25','2025-26')
        and substr(cast(game_id as string), 5, 2) = '02'
      qualify row_number() over (partition by season order by game_id, event_id) <= {n_per_season}
    """).result())
    meta = {f"{g.game_id}-{g.event_id}": {"season": g.season, "scorer": g.scoring_player_id,
            "a1": g.assist1_player_id, "a2": g.assist2_player_id} for g in goals}
    keys = ",".join(f"({g.game_id},{g.event_id})" for g in goals)
    frames = c.query(f"""
      select game_id, event_id, frame_index, frame_seconds, is_puck, player_id, team_id, team_abbrev, x_std, y_std
      from `{P}.nhl_staging.stg_ppt_tracking_frames`
      where (game_id, event_id) in ({keys})
    """).result().to_arrow()
    df = pl.from_arrow(frames)
    df.write_parquet(cache_f); meta_f.write_text(json.dumps(meta))
    return df


def _meta() -> dict:
    return json.loads((CACHE / "reconstruct_meta.json").read_text())


def reconstruct_goal(g: pl.DataFrame) -> dict:
    """One goal's frames -> carrier timeline, passes, entry, release/arrival. g sorted by frame_index.

    Arrival = start of the FINAL in-net run (the puck's last, resting entry into the goal mouth) --
    this ignores behind-the-net excursions (|y| wide of the posts) and the post-goal net-sit. Release =
    the last frame before arrival where a skater was within stick reach and the puck then flew to the
    net with no carrier; shooter = that skater. Net-front crowd = skaters clustered on the puck at
    arrival, the tell for a scramble goal that has no clean carrier.
    """
    empty = {"n_frames": 0, "arrival_frame": None, "attack_sign": None, "n_segments": 0,
             "n_passes": 0, "shooter": None, "release_frame": None, "entry_frame": None,
             "atk_chain_last3": [], "passes": [], "crowd": None, "scorer_min_dist": None,
             "scoring_cluster": []}
    g = g.sort("frame_index").drop_nulls(["x_std", "y_std"])
    frames = sorted(g["frame_index"].unique().to_list())
    puck = g.filter(pl.col("is_puck")).sort("frame_index")
    if puck.height == 0 or not frames:
        return {**empty}
    px_l = puck["x_std"].to_list(); py_l = puck["y_std"].to_list(); pf_l = puck["frame_index"].to_list()
    # in the NET MOUTH: between the goal line and the back of the net (NOT behind it against the boards)
    in_net = [NET_X <= abs(x) <= NET_BACK and abs(y) <= NET_Y_HALF for x, y in zip(px_l, py_l)]
    dn = [min(abs(x - 89), abs(x + 89)) for x in px_l]
    spd_l = [0.0] + [((px_l[i] - px_l[i - 1]) ** 2 + (py_l[i] - py_l[i - 1]) ** 2) ** 0.5 for i in range(1, len(px_l))]
    flight = [i for i in range(1, len(px_l)) if spd_l[i] >= FLIGHT_SPEED and dn[i] <= dn[i - 1] + 1.0]
    net_idx = [i for i in range(len(in_net)) if in_net[i]]
    # arrival = the goal moment. Prefer the FIRST in-net frame reached by a real shot flight (a fast,
    # net-ward run within the prior ~6 frames) -- this ties the goal to a shot and skips both pre-buildup
    # grazes and post-goal net-sits. Fall back: first in-net frame a skater worked the puck into (jam-in);
    # then nearest-net if the puck never reads in-net at all.
    shot_in = [i for i in net_idx if any(j in flight for j in range(max(1, i - 6), i + 1))]
    if shot_in:
        ai = shot_in[0]
    elif net_idx:
        worked = [i for i in net_idx if any(
            (g.filter((pl.col("frame_index") == pf_l[k]) & ~pl.col("is_puck") & pl.col("player_id").is_not_null())
             .with_columns(d=((pl.col("x_std") - px_l[k]) ** 2 + (pl.col("y_std") - py_l[k]) ** 2).sqrt())["d"].min() or 99) <= CARRY_RADIUS_FT
            for k in range(max(0, i - 3), i + 1))]
        ai = worked[0] if worked else net_idx[0]
    else:
        ai = dn.index(min(dn))
    arrival_frame = pf_l[ai]
    ax = px_l[ai]
    attack_sign = 1.0 if ax > 0 else -1.0
    # carrier per frame (nearest skater within CARRY_RADIUS)
    carrier = []                      # (frame, player_id, team_abbrev, dist) or None
    puck_xy = dict(zip(pf_l, zip(px_l, py_l)))
    for fr in frames:
        if fr not in puck_xy:
            carrier.append(None); continue
        px, py = puck_xy[fr]
        sk = (g.filter((pl.col("frame_index") == fr) & ~pl.col("is_puck") & pl.col("player_id").is_not_null())
              .with_columns(d=((pl.col("x_std") - px) ** 2 + (pl.col("y_std") - py) ** 2).sqrt()).sort("d"))
        if sk.height == 0:
            carrier.append(None); continue
        n = sk.head(1)
        carrier.append((fr, int(n["player_id"][0]), n["team_abbrev"][0], float(n["d"][0]))
                       if n["d"][0] <= CARRY_RADIUS_FT else None)
    # possession segments (bridge <=LOOSE_GAP_MAX loose frames within one player's run)
    segs = []                          # [player_id, team, start_frame, end_frame]
    for c in carrier:
        if c is None:
            continue
        _, pid, team, _ = c
        if segs and segs[-1][0] == pid and (c[0] - segs[-1][3]) <= LOOSE_GAP_MAX + 1:
            segs[-1][3] = c[0]
        else:
            segs.append([pid, team, c[0], c[0]])
    pre = [s for s in segs if s[2] <= arrival_frame]
    # release/shooter via SHOT-FLIGHT detection. Walk back from arrival through the puck's final flight
    # -- consecutive frames where it moves fast (>=FLIGHT_SPEED) and net-ward (dnet not increasing) --
    # and place the release at the flight's first frame. A skater merely near the puck DURING the flight
    # is a coincidental fly-by (a screen the shot passed); the shooter is whoever the puck left FROM.
    # No fast flight (a crease jam-in) => release is the arrival frame itself.
    dnet_at = {pf_l[i]: min(abs(px_l[i] - 89), abs(px_l[i] + 89)) for i in range(len(pf_l))}
    up_to = [f for f in pf_l if f <= arrival_frame]
    ridx = up_to.index(arrival_frame)
    rel_i = ridx
    while rel_i > 0:
        f_cur, f_prev = up_to[rel_i], up_to[rel_i - 1]
        cx, cy = puck_xy[f_cur]; qx, qy = puck_xy[f_prev]
        spd = ((cx - qx) ** 2 + (cy - qy) ** 2) ** 0.5
        toward = dnet_at[f_cur] <= dnet_at[f_prev] + 1.0
        if spd >= FLIGHT_SPEED and toward:
            rel_i -= 1
        else:
            break
    release_frame = up_to[rel_i]
    rpx, rpy = puck_xy[release_frame]
    rsk = (g.filter((pl.col("frame_index") == release_frame) & ~pl.col("is_puck") & pl.col("player_id").is_not_null())
           .with_columns(d=((pl.col("x_std") - rpx) ** 2 + (pl.col("y_std") - rpy) ** 2).sqrt()).sort("d").head(1))
    shooter = shooter_team = None
    if rsk.height and rsk["d"][0] <= RELEASE_RADIUS_FT + 1.0:
        shooter = int(rsk["player_id"][0]); shooter_team = rsk["team_abbrev"][0]
    else:
        # puck already deep in the net at release (a walked-in/tucked goal, no clean flight): fall back
        # to the last frame it was under a skater's control before the arrival.
        for fr in [f for f in up_to if f <= release_frame][::-1]:
            px, py = puck_xy[fr]
            sk = (g.filter((pl.col("frame_index") == fr) & ~pl.col("is_puck") & pl.col("player_id").is_not_null())
                  .with_columns(d=((pl.col("x_std") - px) ** 2 + (pl.col("y_std") - py) ** 2).sqrt()).sort("d").head(1))
            if sk.height and sk["d"][0] <= CARRY_RADIUS_FT:
                shooter = int(sk["player_id"][0]); shooter_team = sk["team_abbrev"][0]; release_frame = fr
                break
    # net-front crowd + scorer proximity at arrival (scramble tell)
    apx, apy = puck_xy.get(arrival_frame, (None, None))
    crowd = None; sc = None
    if apx is not None:
        arr = (g.filter((pl.col("frame_index") == arrival_frame) & ~pl.col("is_puck") & pl.col("player_id").is_not_null())
               .with_columns(d=((pl.col("x_std") - apx) ** 2 + (pl.col("y_std") - apy) ** 2).sqrt()))
        crowd = int((arr["d"] <= CROWD_RADIUS_FT).sum())
        sc = arr.sort("d")
    # passes = consecutive segments, same team, different player
    passes = []
    for i in range(1, len(segs)):
        a, b = segs[i - 1], segs[i]
        if a[1] == b[1] and a[0] != b[0]:
            passes.append((a[0], b[0], a[1]))
    # zone entry: last puck crossing of the attacking blue line before arrival
    entry_frame = None
    for i in range(1, len(px_l)):
        if pf_l[i] > arrival_frame:
            break
        crossed = (px_l[i - 1] - BLUE_LINE * attack_sign) * (px_l[i] - BLUE_LINE * attack_sign) < 0
        if crossed and (px_l[i] * attack_sign > BLUE_LINE):
            entry_frame = pf_l[i]
    # attacking-team carriers in order (buildup chain); scoring cluster = last 3 attacking carriers
    atk_chain = [s[0] for s in pre if s[1] == shooter_team] if shooter_team else []
    return {"n_frames": len(frames), "arrival_frame": arrival_frame, "attack_sign": attack_sign,
            "n_segments": len(segs), "n_passes": len(passes), "shooter": shooter,
            "release_frame": release_frame, "entry_frame": entry_frame,
            "atk_chain_last3": atk_chain[-3:], "passes": passes[-4:], "crowd": crowd,
            "scorer_min_dist": None, "scoring_cluster": atk_chain[-3:]}


def _scorer_min_dist(g: pl.DataFrame, scorer: int, arrival_frame: int) -> float | None:
    """Closest the recorded scorer ever got to the puck, up to & including arrival (crease-scramble tell)."""
    puck = g.filter(pl.col("is_puck")).select("frame_index", px="x_std", py="y_std")
    sc = g.filter((~pl.col("is_puck")) & (pl.col("player_id") == scorer)).select("frame_index", "x_std", "y_std")
    j = sc.join(puck, on="frame_index").filter(pl.col("frame_index") <= arrival_frame)
    if j.height == 0:
        return None
    return float(j.select(d=((pl.col("x_std") - pl.col("px")) ** 2 + (pl.col("y_std") - pl.col("py")) ** 2).sqrt())["d"].min())


def run(n_per_season: int = 5) -> dict:
    df = pull_sample(n_per_season)
    meta = _meta()
    results = []
    exact = cluster = ever_near = a_any = 0
    for key, m in meta.items():
        gid, eid = key.split("-")
        g = df.filter((pl.col("game_id") == int(gid)) & (pl.col("event_id") == int(eid)))
        if g.height == 0:
            continue
        r = reconstruct_goal(g)
        assisters = {m["a1"], m["a2"]}
        cl = set(r["scoring_cluster"])
        exact_match = (r["shooter"] == m["scorer"])
        in_cluster = m["scorer"] in cl
        smind = _scorer_min_dist(g, m["scorer"], r["arrival_frame"]) if r["arrival_frame"] is not None else None
        near = smind is not None and smind <= RELEASE_RADIUS_FT
        assist_overlap = len(cl & assisters)
        exact += int(exact_match); cluster += int(in_cluster); ever_near += int(bool(near))
        a_any += int(assist_overlap >= 1)
        results.append({"key": key, "season": m["season"], "scorer": m["scorer"],
                        "recon_shooter": r["shooter"], "exact_match": exact_match,
                        "scorer_in_cluster": in_cluster, "scorer_min_dist": smind, "crowd": r["crowd"],
                        "assisters": list(assisters), "scoring_cluster": r["scoring_cluster"],
                        "assist_overlap": assist_overlap, "n_passes": r["n_passes"],
                        "entry_frame": r["entry_frame"], "release_frame": r["release_frame"],
                        "arrival_frame": r["arrival_frame"], "n_frames": r["n_frames"]})
    n = len(results)
    return {"n_goals": n, "carry_radius_ft": CARRY_RADIUS_FT,
            "exact_shooter_rate": exact / n if n else None,
            "scorer_in_cluster_rate": cluster / n if n else None,
            "scorer_ever_near_puck_rate": ever_near / n if n else None,
            "assist_overlap_rate": a_any / n if n else None, "goals": results}


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    r = run(n)
    print(f"reconstructed {r['n_goals']} goals (carry radius {r['carry_radius_ft']} ft)")
    print(f"  exact shooter == recorded scorer:        {r['exact_shooter_rate']*100:.0f}%")
    print(f"  scorer in reconstructed scoring cluster: {r['scorer_in_cluster_rate']*100:.0f}%")
    print(f"  scorer ever within stick-reach of puck:  {r['scorer_ever_near_puck_rate']*100:.0f}%")
    print(f"  scoring cluster overlaps a recorded assister: {r['assist_overlap_rate']*100:.0f}%")
    for g in r["goals"]:
        tag = "EXACT" if g["exact_match"] else ("clust" if g["scorer_in_cluster"] else "MISS")
        sm = f"{g['scorer_min_dist']:.1f}ft" if g["scorer_min_dist"] is not None else "n/a"
        print(f"  {g['key']} {g['season']}: [{tag}] shooter={g['recon_shooter']} scorer={g['scorer']} "
              f"crowd={g['crowd']} scorer_min={sm} | cluster{g['scoring_cluster']} vs assists{g['assisters']} "
              f"(ovl {g['assist_overlap']}) | passes={g['n_passes']} entry@{g['entry_frame']} rel@{g['release_frame']} arr@{g['arrival_frame']}")
