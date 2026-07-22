"""Gap Control · PHASE A0 — derive the data-internal knobs (§2c of the spec). Produces DISTRIBUTIONS and derived
cuts ONLY: no coupling on the full set, no gap, no per-player profile. Each knob is derived by labeling two
modes with geometry INDEPENDENT of the quantity being cut, then reporting where the labeled distributions
separate (clean = trust; smeared = weak condition, rethink). STOP for owner review of the derived knobs.

Knobs: (1) backward-posture depth-velocity cutoff · (2) lateral min-motion floor · (3) separation-rate bound ·
(4) |Δlateral-velocity| agreement bound · (5) near-center/ambiguous band for D side · (6) thin-sample cutoff.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe
from .meta import load as load_meta
from .tracks import TRACKS

HZ = 10.0
GEP = ["game_id", "event_id", "player_id"]


def base() -> pl.DataFrame:
    t = pl.read_parquet(TRACKS).join(universe().select("game_id", "event_id", "attack_sign"),
                                     on=["game_id", "event_id"], how="inner")
    t = t.with_columns(depth_D=89.0 - pl.col("attack_sign") * pl.col("def_x"), lat_D=pl.col("attack_sign") * pl.col("def_y"),
                       depth_A=89.0 - pl.col("attack_sign") * pl.col("att_x"), lat_A=pl.col("attack_sign") * pl.col("att_y"),
                       dist=pl.col("dist_near_atk")).sort("game_id", "event_id", "player_id", "frame_index")

    def cdiff(col):
        return (pl.col(col).shift(-1).over(GEP) - pl.col(col).shift(1).over(GEP)) * HZ / 2.0
    return t.with_columns(vDepthD=cdiff("depth_D"), vLatD=cdiff("lat_D"), vDepthA=cdiff("depth_A"),
                          vLatA=cdiff("lat_A"), vDist=cdiff("dist"), goalside=pl.col("depth_D") < pl.col("depth_A"))


def _auc(x, lab):
    x = np.asarray(x, float); lab = np.asarray(lab, bool)
    a, b = x[lab], x[~lab]
    if len(a) < 5 or len(b) < 5:
        return float("nan")
    r = np.argsort(np.argsort(np.concatenate([a, b]))) + 1
    ra = r[:len(a)].sum()
    return (ra - len(a) * (len(a) + 1) / 2) / (len(a) * len(b))


def _youden(x, lab, direction):
    """cut on x; direction=-1 means 'x <= cut' is the positive (label) class. returns cut maximizing TPR-FPR."""
    x = np.asarray(x, float); lab = np.asarray(lab, bool)
    qs = np.quantile(x[np.isfinite(x)], np.linspace(0.02, 0.98, 60))
    best, bcut = -1, None
    for c in qs:
        pred = (x <= c) if direction < 0 else (x >= c)
        tpr = (pred & lab).sum() / max(lab.sum(), 1); fpr = (pred & ~lab).sum() / max((~lab).sum(), 1)
        if tpr - fpr > best:
            best, bcut = tpr - fpr, c
    return round(float(bcut), 2), round(float(best), 2)


def _verdict(auc):
    a = abs(auc - 0.5) * 2  # 0..1 separation strength
    return "CLEAN" if a >= 0.5 else ("MODERATE" if a >= 0.24 else "SMEARED/WEAK")


def _row(name, target, lab, direction):
    x = np.asarray(target, float); m = np.isfinite(x)
    x, lab = x[m], np.asarray(lab, bool)[m]
    auc = _auc(x, lab)
    cut, j = _youden(x, lab, direction)
    a, b = x[lab], x[~lab]
    return {"knob": name, "n_pos": int(lab.sum()), "n_neg": int((~lab).sum()),
            "pos_med_iqr": [round(float(np.median(a)), 1), round(float(np.quantile(a, .25)), 1), round(float(np.quantile(a, .75)), 1)],
            "neg_med_iqr": [round(float(np.median(b)), 1), round(float(np.quantile(b, .25)), 1), round(float(np.quantile(b, .75)), 1)],
            "auc": round(float(auc), 3), "cut": cut, "youden_j": j, "verdict": _verdict(auc)}


def knobs() -> dict:
    b = base()
    out = {}
    # (1) backward-posture: defending (goal-side + carrier advancing to net) vs with-play (up-ice + carrier going up-ice)
    k1 = b.filter(pl.col("vDepthA").abs() > 5).with_columns(
        defending=pl.col("goalside") & (pl.col("vDepthA") < -5),
        withplay=(~pl.col("goalside")) & (pl.col("vDepthA") > 5))
    k1 = k1.filter(pl.col("defending") | pl.col("withplay")).drop_nulls(["vDepthD"])
    out["1_backward_posture_vDepthD"] = _row("backward-posture: defender depth-velocity (ft/s); defending should be LOW",
                                             k1["vDepthD"], k1["defending"], direction=-1)
    # (2) lateral min-motion floor: label track straight/cutting by NET lateral displacement, target = per-frame |vLatA|
    trk = b.group_by(GEP).agg(net_lat=(pl.col("lat_A").last() - pl.col("lat_A").first()).abs(), nfr=pl.len())
    lo, hi = trk["net_lat"].quantile(0.33), trk["net_lat"].quantile(0.66)
    trk = trk.with_columns(cutting=pl.col("net_lat") > hi, straight=pl.col("net_lat") < lo)
    k2 = b.join(trk.filter(pl.col("cutting") | pl.col("straight")).select(*GEP, "cutting"), on=GEP, how="inner").drop_nulls(["vLatA"]).with_columns(av=pl.col("vLatA").abs())
    out["2_lateral_min_motion_absVLatA"] = _row("lateral min-motion floor: |attacker lateral velocity| (ft/s); cutting should be HIGH",
                                                k2["av"], k2["cutting"], direction=1)
    # (3) separation-rate bound: pair engaged (end dist<10) vs beaten (end>30) by END distance; target = mid vDist
    pr = b.group_by(GEP).agg(end_d=pl.col("dist").last(), mid_vdist=pl.col("vDist").median(), nfr=pl.len()).filter(pl.col("nfr") >= 5)
    pr = pr.with_columns(engaged=pl.col("end_d") < 10, beaten=pl.col("end_d") > 30).filter(pl.col("engaged") | pl.col("beaten")).drop_nulls(["mid_vdist"])
    out["3_separation_rate_vDist"] = _row("separation-rate bound: d(distance)/dt (ft/s); BEATEN should be HIGH (separating)",
                                          pr["mid_vdist"], pr["beaten"], direction=1)
    # (4) |Δlateral-velocity| bound: same-man (own pair, close+goalside) vs different-man (decoy: other defender's attacker)
    samp = b.select("game_id", "event_id").unique().sample(fraction=0.15, seed=20260714)
    bs = b.join(samp, on=["game_id", "event_id"], how="inner")
    same = bs.filter((pl.col("dist") < 10) & pl.col("goalside")).drop_nulls(["vLatD", "vLatA"]).with_columns(dv=(pl.col("vLatD") - pl.col("vLatA")).abs())
    # decoy: within (game,event,frame) pair a defender's vLatD with a DIFFERENT defender's vLatA (a different man)
    L = bs.select("game_id", "event_id", "frame_index", p1="player_id", vLatD="vLatD").drop_nulls(["vLatD"])
    R = bs.select("game_id", "event_id", "frame_index", p2="player_id", vLatA_o="vLatA", na2="near_att_id").drop_nulls(["vLatA_o"])
    dec = (L.join(R, on=["game_id", "event_id", "frame_index"], how="inner").filter(pl.col("p1") != pl.col("p2"))
           .with_columns(dv=(pl.col("vLatD") - pl.col("vLatA_o")).abs()))
    dv = np.concatenate([same["dv"].to_numpy(), dec["dv"].to_numpy()])
    lab = np.concatenate([np.zeros(same.height, bool), np.ones(dec.height, bool)])  # different-man = positive
    out["4_dLatVel_agreement"] = _row("|Δlateral-velocity| (ft/s); DIFFERENT-man should be HIGH, same-man LOW", dv, lab, direction=1)

    # (5) near-center band for D side: per-D mean lateral; find the overlap between left/right clusters
    isdef = set(load_meta().filter(pl.col("is_def"))["player_id"].to_list())
    perD = b.filter(pl.col("player_id").is_in(list(isdef))).group_by("player_id").agg(mean_lat=pl.col("lat_D").mean(), nfr=pl.len()).filter(pl.col("nfr") >= 100)
    ml = perD["mean_lat"].to_numpy()
    left, right = ml[ml < 0], ml[ml > 0]
    # ambiguous band = where left's upper tail and right's lower tail overlap: [ -p_overlap_right , p_overlap_left ]
    band_hi = float(np.quantile(left, 0.90)) if len(left) else 0.0   # 90th pct of left cluster (its right tail)
    band_lo = float(np.quantile(right, 0.10)) if len(right) else 0.0  # 10th pct of right cluster (its left tail)
    out["5_near_center_band"] = {"n_D": perD.height, "left_cluster_n": int((ml < 0).sum()), "right_cluster_n": int((ml > 0).sum()),
                                 "left_med": round(float(np.median(left)), 1), "right_med": round(float(np.median(right)), 1),
                                 "ambiguous_band_ft": [round(band_hi, 1), round(band_lo, 1)],
                                 "bimodal_dip": round(float(np.mean((ml > band_hi) & (ml < band_lo))), 3),
                                 "note": "|mean_lat| inside [%.1f, %.1f] = ambiguous → defer to handedness" % (band_hi, band_lo)}
    # (6) thin-sample cutoff: how many frames until a D's mean-lat estimate reliably sides (SE < half the band)
    within_sd = float(np.median(b.filter(pl.col("player_id").is_in(list(isdef))).group_by("player_id").agg(sd=pl.col("lat_D").std())["sd"].drop_nulls().to_numpy()))
    half_band = max(abs(band_hi), abs(band_lo), 1.0)
    n_cut = int(np.ceil((within_sd / half_band) ** 2))
    out["6_thin_sample_cutoff"] = {"within_D_lat_sd_ft": round(within_sd, 1), "half_band_ft": round(half_band, 1),
                                   "frame_cutoff": n_cut, "note": "below ~%d tracked frames a D's mean-lat SE exceeds half the ambiguous band → treat as thin, defer to handedness" % n_cut}
    return out


def write() -> dict:
    K = knobs()
    L = []; W = L.append
    W("# Gap Control · Phase A0 — derived data-internal knobs (distributions + cuts only; nothing built)\n")
    W("Each knob labeled by geometry INDEPENDENT of the quantity being cut, then the cut is placed where the "
      "labeled distributions separate (Youden). Verdict CLEAN = trust the knob; SMEARED/WEAK = the condition is "
      "weak and must be reconsidered, not forced. No coupling on the full set, no gap, no profile.\n")
    W("## Knobs 1-4 (coupling conditions) — labeled-mode distributions + derived cut\n")
    W("| knob | pos n | neg n | pos med[IQR] | neg med[IQR] | AUC | derived cut | verdict |")
    W("|---|---|---|---|---|---|---|---|")
    for k in ["1_backward_posture_vDepthD", "2_lateral_min_motion_absVLatA", "3_separation_rate_vDist", "4_dLatVel_agreement"]:
        v = K[k]
        W(f"| {v['knob']} | {v['n_pos']} | {v['n_neg']} | {v['pos_med_iqr'][0]} [{v['pos_med_iqr'][1]},{v['pos_med_iqr'][2]}] | "
          f"{v['neg_med_iqr'][0]} [{v['neg_med_iqr'][1]},{v['neg_med_iqr'][2]}] | **{v['auc']}** | **{v['cut']}** | {v['verdict']} |")
    W("\n(pos/neg = the two independent-label modes; the cut is the derived §4.2 threshold. AUC≈0.5 ⇒ smeared.)\n")
    W("## Knob 5 — near-center / ambiguous D-side band\n")
    v = K["5_near_center_band"]
    W(f"- {v['n_D']} D (≥100 tracked frames); left-cluster {v['left_cluster_n']} (med {v['left_med']} ft), "
      f"right-cluster {v['right_cluster_n']} (med {v['right_med']} ft). **Ambiguous band = |mean-lat| in "
      f"[{v['ambiguous_band_ft'][0]}, {v['ambiguous_band_ft'][1]}] ft** (fraction of D in the dip: {v['bimodal_dip']}). {v['note']}")
    W("\n## Knob 6 — thin-sample cutoff for the tracking-derived side\n")
    v = K["6_thin_sample_cutoff"]
    W(f"- within-D lateral SD {v['within_D_lat_sd_ft']} ft; half-band {v['half_band_ft']} ft → **frame cutoff ≈ {v['frame_cutoff']}**. {v['note']}")
    W("\n## STOP — owner review of the derived knobs before Phase A coupling on the full set. Nothing built.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "gapcontrol_a0.md").write_text("\n".join(L))
    return K


if __name__ == "__main__":
    import json
    K = write()
    print(json.dumps(K, indent=1, default=str))
