"""Side project — PUCK-PATH HEATMAP. Overlay the ~10s puck trajectory before every 5v5 goal onto one rink,
as a density heatmap, so heavily-traveled lanes glow. Direction-normalized so all attacks point the SAME way
(flip BOTH x and y by attack_sign). Visualization only — no gates, no stats.

Coords: x_std in ±100 (end boards), y_std in ±42.5 (side boards), scored-on net at x_std = attack_sign·89.
Normalize: x_norm = attack_sign·x_std, y_norm = attack_sign·y_std  → scored-on net always at (+89, 0); attacks
flow left→right; right wing overlays right wing. Sanity: at the shot the puck should cluster near (+89, 0).
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe

WIN = 100          # frames (~10s) of buildup before the shot
SEASON_FILES = ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]


def _accumulate():
    u = universe().select("game_id", "event_id", "season", "attack_sign", "goal_frame")
    xs, ys, shot_x, shot_y = [], [], [], []
    ngoals = 0
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        gids = us["game_id"].unique().to_list()
        pk = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "x_std", "y_std"])
              .filter(pl.col("is_puck") & pl.col("game_id").is_in(gids))
              .join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(xn=pl.col("attack_sign") * pl.col("x_std"), yn=pl.col("attack_sign") * pl.col("y_std")))
        xs.append(pk["xn"].to_numpy()); ys.append(pk["yn"].to_numpy())
        sh = pk.filter(pl.col("frame_index") == pl.col("goal_frame"))
        shot_x.append(sh["xn"].to_numpy()); shot_y.append(sh["yn"].to_numpy())
        ngoals += us.height
    return (np.concatenate(xs), np.concatenate(ys), np.concatenate(shot_x), np.concatenate(shot_y), ngoals)


def _rink(ax, c="white", lw=1.0, af=1.0, red="#e33", blue="#39f"):
    """Standard NHL sheet to scale (feet, center at 0): boards ±100/±42.5, goal lines ±89, blue lines ±25,
    center line 0, faceoff circles r15 at (±69,±22) + center, creases + nets. af = alpha factor (dim underlay)."""
    from matplotlib.patches import Arc, Circle, Rectangle
    a = dict(color=c, lw=lw, alpha=.55 * af)
    for (x0, x1) in [(-100, 100)]:
        ax.plot([x0 + 28, x1 - 28], [42.5, 42.5], **a); ax.plot([x0 + 28, x1 - 28], [-42.5, -42.5], **a)
        ax.plot([100, 100], [-42.5 + 28, 42.5 - 28], **a); ax.plot([-100, -100], [-42.5 + 28, 42.5 - 28], **a)
    for cx, cy, t1, t2 in [(72, 14.5, 0, 90), (-72, 14.5, 90, 180), (72, -14.5, 270, 360), (-72, -14.5, 180, 270)]:
        ax.add_patch(Arc((cx, cy), 56, 56, theta1=t1, theta2=t2, color=c, lw=lw, alpha=.55 * af))
    ax.plot([0, 0], [-42.5, 42.5], color=red, lw=lw, alpha=.5 * af)
    for bx in (-25, 25):
        ax.plot([bx, bx], [-42.5, 42.5], color=blue, lw=lw + .3, alpha=.6 * af)
    for gx in (-89, 89):
        ax.plot([gx, gx], [-40, 40], color=red, lw=lw, alpha=.5 * af)
        ax.add_patch(Rectangle((gx - (3 if gx > 0 else -3) - (3 if gx < 0 else 0), -3), 3 if gx < 0 else 3, 6,
                               fill=False, color=c, lw=lw, alpha=.5 * af))
    ax.add_patch(Circle((0, 0), 15, fill=False, color=blue, lw=lw, alpha=.5 * af))
    for cx in (-69, 69):
        for cy in (-22, 22):
            ax.add_patch(Circle((cx, cy), 15, fill=False, color=red, lw=lw, alpha=.45 * af))
            ax.add_patch(Circle((cx, cy), 1, color=red, alpha=.6 * af))
    for cx in (-20, 20):
        for cy in (-22, 22):
            ax.add_patch(Circle((cx, cy), 1, color=red, alpha=.5 * af))
    for gx, th1, th2 in [(89, 90, 270), (-89, 270, 450)]:
        ax.add_patch(Arc((gx, 0), 12, 12, theta1=th1, theta2=th2, color=blue, lw=lw, alpha=.5 * af))
    ax.set_xlim(-101, 101); ax.set_ylim(-43.5, 43.5); ax.set_aspect("equal"); ax.axis("off")


def write() -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import PowerNorm
    from scipy.ndimage import gaussian_filter
    x, y, sx, sy, ngoals = _accumulate()
    # 2D density, 1 ft bins, smoothed (KDE-like)
    xe = np.arange(-100, 101, 1.0); ye = np.arange(-42.5, 43.5, 1.0)
    H, _, _ = np.histogram2d(x, y, bins=[xe, ye])
    Hs = gaussian_filter(H, sigma=2.0)
    Hs = Hs / Hs.max()
    fig, ax = plt.subplots(figsize=(15, 6.6))
    fig.patch.set_facecolor("#05060a"); ax.set_facecolor("#05060a")
    im = ax.imshow(Hs.T, origin="lower", extent=[-100, 100, -42.5, 42.5], cmap="inferno",
                   norm=PowerNorm(gamma=0.45), interpolation="bilinear", aspect="equal")
    _rink(ax, c="white", lw=1.1)
    ax.set_title(f"Puck-path density → 5v5 goals  ·  {ngoals:,} goals, ~10s buildup each  ·  "
                 "all attacks normalized left→right (scored-on net at right)",
                 color="white", fontsize=11, pad=8)
    cb = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cb.set_label("relative puck-frame density", color="white"); cb.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="white")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(C.REPORTS / "puck_heatmap.png", dpi=150, facecolor="#05060a", bbox_inches="tight")
    plt.close(fig)
    return {"n_goals": int(ngoals), "n_puck_frames": int(len(x)),
            "shot_mean_xnorm": round(float(np.mean(sx)), 1), "shot_mean_ynorm": round(float(np.mean(sy)), 1),
            "shot_median_xnorm": round(float(np.median(sx)), 1),
            "frac_shot_in_attacking_third_xnorm_gt25": round(float(np.mean(sx > 25)), 3)}


NX, NY = 200, 85           # 1-ft grid over x[-100,100], y[-42.5,42.5]


def _raster(xs, ys, H, npts=24):
    """Rasterize one goal's polyline onto the grid, interpolating each segment so fast pucks draw a continuous
    line; DEDUPE cells within the goal (a lingering puck counts a cell once). Increments each crossed cell by 1."""
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    if len(xs) < 2:
        return
    t = np.linspace(0, 1, npts)
    px = (xs[:-1, None] + (xs[1:] - xs[:-1])[:, None] * t).ravel()
    py = (ys[:-1, None] + (ys[1:] - ys[:-1])[:, None] * t).ravel()
    ix = np.floor(px + 100).astype(int); iy = np.floor(py + 42.5).astype(int)
    m = (ix >= 0) & (ix < NX) & (iy >= 0) & (iy < NY)
    flat = np.unique(ix[m] * NY + iy[m])          # dedupe cells for THIS goal
    H.reshape(-1)[flat] += 1                        # +1 per goal whose path crossed the cell


def _paths():
    u = universe().select("game_id", "event_id", "season", "attack_sign", "goal_frame")
    H = np.zeros((NX, NY), float)
    ngoals = 0; shot_x, shot_y = [], []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        gids = us["game_id"].unique().to_list()
        pk = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "x_std", "y_std"])
              .filter(pl.col("is_puck") & pl.col("game_id").is_in(gids))
              .join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(xn=pl.col("attack_sign") * pl.col("x_std"), yn=pl.col("attack_sign") * pl.col("y_std"))
              .sort("game_id", "event_id", "frame_index"))
        grp = pk.group_by("game_id", "event_id", maintain_order=True).agg(
            xn=pl.col("xn"), yn=pl.col("yn"),
            sx=pl.col("xn").filter(pl.col("frame_index") == pl.col("goal_frame")).first(),
            sy=pl.col("yn").filter(pl.col("frame_index") == pl.col("goal_frame")).first())
        for row in grp.iter_rows(named=True):
            _raster(row["xn"], row["yn"], H)
            ngoals += 1
            if row["sx"] is not None:
                shot_x.append(row["sx"]); shot_y.append(row["sy"])
    return H, ngoals, np.array(shot_x), np.array(shot_y)


def write_path() -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import PowerNorm
    from scipy.ndimage import gaussian_filter
    H, ngoals, sx, sy = _paths()
    Hs = gaussian_filter(H, sigma=1.0)             # light smooth for line continuity; value ≈ #goals crossing
    peak = float(H.max())
    Hn = Hs / Hs.max()
    fig, ax = plt.subplots(figsize=(15, 6.6))
    fig.patch.set_facecolor("#05060a"); ax.set_facecolor("#05060a")
    im = ax.imshow(Hn.T, origin="lower", extent=[-100, 100, -42.5, 42.5], cmap="inferno",
                   norm=PowerNorm(gamma=0.5), interpolation="bilinear", aspect="equal")
    _rink(ax, c="white", lw=1.1)
    ax.set_title(f"Puck ROUTE density → 5v5 goals  ·  {ngoals:,} goals, each path counted once per cell  ·  "
                 "attacks normalized left→right (scored-on net at right)", color="white", fontsize=11, pad=8)
    cb = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cb.set_label(f"share of goals whose path crossed (peak ≈ {int(peak):,} goals)", color="white")
    cb.ax.yaxis.set_tick_params(color="white"); plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="white")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(C.REPORTS / "puck_path_heatmap.png", dpi=150, facecolor="#05060a", bbox_inches="tight")
    plt.close(fig)
    return {"n_goals": int(ngoals), "peak_cell_goals": int(peak),
            "shot_mean_xnorm": round(float(np.mean(sx)), 1), "shot_mean_ynorm": round(float(np.mean(sy)), 1),
            "shot_median_xnorm": round(float(np.median(sx)), 1),
            "frac_shot_xnorm_gt25": round(float(np.mean(sx > 25)), 3)}


def _smooth(a, k=3):
    """light moving-average to de-jitter a path coordinate (keeps endpoints)."""
    a = np.asarray(a, float)
    if len(a) < k:
        return a
    ker = np.ones(k) / k
    s = np.convolve(a, ker, mode="same")
    s[0], s[-1] = a[0], a[-1]
    return s


def _goal_paths():
    u = universe().select("game_id", "event_id", "season", "attack_sign", "goal_frame")
    paths, sx, sy = [], [], []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        gids = us["game_id"].unique().to_list()
        pk = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "x_std", "y_std"])
              .filter(pl.col("is_puck") & pl.col("game_id").is_in(gids))
              .join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(xn=pl.col("attack_sign") * pl.col("x_std"), yn=pl.col("attack_sign") * pl.col("y_std"))
              .sort("game_id", "event_id", "frame_index"))
        grp = pk.group_by("game_id", "event_id", maintain_order=True).agg(
            xn=pl.col("xn"), yn=pl.col("yn"),
            s_x=pl.col("xn").filter(pl.col("frame_index") == pl.col("goal_frame")).first(),
            s_y=pl.col("yn").filter(pl.col("frame_index") == pl.col("goal_frame")).first())
        for row in grp.iter_rows(named=True):
            if len(row["xn"]) < 2:
                continue
            paths.append(np.column_stack([_smooth(row["xn"]), _smooth(row["yn"])]))
            if row["s_x"] is not None:
                sx.append(row["s_x"]); sy.append(row["s_y"])
    return paths, np.array(sx), np.array(sy)


def write_trails(alpha=0.03, lw=0.45) -> dict:
    """Light-trails: every goal's puck path as an additive translucent polyline; overlaps accumulate to bright
    lanes. NO binning, NO KDE — thousands of thin strokes layered on near-black (over-compositing ≈ additive)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    paths, sx, sy = _goal_paths()
    fig, ax = plt.subplots(figsize=(24, 10.2))
    bg = "#03040a"
    fig.patch.set_facecolor(bg); ax.set_facecolor(bg)
    _rink(ax, c="#7a8aa8", lw=1.0, af=0.5, red="#7a5560", blue="#4a6a99")     # dim reference underneath
    lc = LineCollection(paths, colors=[(0.55, 0.85, 1.0, alpha)], linewidths=lw, capstyle="round", joinstyle="round")
    ax.add_collection(lc)                                                      # ~22.8k translucent cyan strokes
    ax.set_title(f"Puck light-trails → 5v5 goals  ·  {len(paths):,} paths, additive α={alpha}, width={lw}px  ·  "
                 "attacks normalized left→right (net at right)", color="#cfe6ff", fontsize=12, pad=10)
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(C.REPORTS / "puck_trails.png", dpi=200, facecolor=bg, bbox_inches="tight")
    plt.close(fig)
    return {"n_goals": len(paths), "alpha": alpha, "linewidth": lw, "dpi": 200,
            "shot_mean_xnorm": round(float(np.mean(sx)), 1), "shot_mean_ynorm": round(float(np.mean(sy)), 1),
            "shot_median_xnorm": round(float(np.median(sx)), 1),
            "frac_shot_xnorm_gt25": round(float(np.mean(sx > 25)), 3)}


def write_tracers(ppf=10, widen_px=3.0, gamma=1.8, bloom_px=7.0, bloom_str=0.4, norm_pct=98.5, floor=0.10,
                  rush_only=True, oz_line=26.0, net_near=60.0) -> dict:
    """Glowing TRACER lanes: rasterize each goal's route ADDITIVELY (dedupe per goal) into a float accumulation
    buffer, WIDEN (gaussian) so near-parallel routes reinforce into solid lanes, gamma tone-map so mid lanes pop,
    add a soft BLOOM for the light-tracer glow, colorize on near-black. True additive (integer route count), not
    matplotlib over-composite. Effective stroke ≈ widen FWHM = %.1f px ≈ %.2f ft.""" % (2.355 * widen_px, 2.355 * widen_px / ppf)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from scipy.ndimage import gaussian_filter
    paths, _, _ = _goal_paths()
    n_all = len(paths)
    if rush_only:      # RUSH goals: puck path STARTS outside the scoring team's offensive zone (x<+26) AND ends at
        paths = [p for p in paths if p[0, 0] < oz_line and p[-1, 0] > net_near]   # the net (drops ~2.4% anomalies)
    sx = np.array([p[-1, 0] for p in paths]); sy = np.array([p[-1, 1] for p in paths])
    NXP, NYP = int(200 * ppf), int(85 * ppf)
    A = np.zeros((NXP, NYP), float)
    for p in paths:                                    # additive route deposit (deduped per goal)
        xs, ys = p[:, 0], p[:, 1]
        t = np.linspace(0, 1, 24)
        px = (xs[:-1, None] + (xs[1:] - xs[:-1])[:, None] * t).ravel()
        py = (ys[:-1, None] + (ys[1:] - ys[:-1])[:, None] * t).ravel()
        fin = np.isfinite(px) & np.isfinite(py)
        px, py = px[fin], py[fin]
        ix = np.floor((px + 100) * ppf).astype(int); iy = np.floor((py + 42.5) * ppf).astype(int)
        m = (ix >= 0) & (ix < NXP) & (iy >= 0) & (iy < NYP)
        flat = np.unique(ix[m] * NYP + iy[m])
        A.reshape(-1)[flat] += 1
    Aw = gaussian_filter(A, sigma=widen_px)            # widen: near-parallel routes reinforce into lanes
    F0 = Aw / np.percentile(Aw[Aw > 0], norm_pct)
    F0 = np.clip((F0 - floor) / (1 - floor), 0, 1)     # subtract the diffuse-fog pedestal to black
    F = F0 ** gamma                                    # gamma>1 compresses the low floor so LANES pop, not fog
    bloom = gaussian_filter(F, sigma=bloom_px)         # soft glow
    F = np.clip(F + bloom_str * bloom / bloom.max(), 0, 1)
    cmap = LinearSegmentedColormap.from_list("tracer", [
        (0.00, (0.010, 0.015, 0.040)), (0.10, (0.00, 0.09, 0.24)), (0.32, (0.05, 0.42, 0.72)),
        (0.58, (0.22, 0.80, 1.00)), (0.82, (0.72, 0.97, 1.00)), (1.00, (1.0, 1.0, 1.0))])
    fig, ax = plt.subplots(figsize=(24, 10.2))
    bg = "#03040a"; fig.patch.set_facecolor(bg); ax.set_facecolor(bg)
    ax.imshow(F.T, origin="lower", extent=[-100, 100, -42.5, 42.5], cmap=cmap, vmin=0, vmax=1,
              interpolation="bilinear", aspect="equal")
    _rink(ax, c="#9fb3d0", lw=1.0, af=0.32, red="#8a6570", blue="#5a7aa9")     # subtle reference over the glow
    tag = "RUSH goals (puck starts OUTSIDE the offensive zone → net)" if rush_only else "all 5v5 goals"
    ax.set_title(f"Puck TRACER lanes → {tag}  ·  {len(paths):,} routes  ·  additive, widen≈{2.355*widen_px/ppf:.2f}ft, "
                 f"γ={gamma}, bloom  ·  normalized left→right (net at right)", color="#cfe6ff", fontsize=12, pad=10)
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    fname = "puck_tracers_rush.png" if rush_only else "puck_tracers.png"
    fig.savefig(C.REPORTS / fname, dpi=200, facecolor=bg, bbox_inches="tight")
    plt.close(fig)
    return {"n_goals_all": n_all, "n_rush_kept": len(paths), "rush_only": rush_only,
            "buffer_px": [NXP, NYP], "widen_px": widen_px,
            "effective_stroke_ft": round(2.355 * widen_px / ppf, 2), "gamma": gamma,
            "bloom_px": bloom_px, "bloom_strength": bloom_str, "norm_pct": norm_pct, "dpi": 200,
            "peak_route_count": int(A.max()),
            "shot_median_xnorm": round(float(np.median(sx)), 1), "shot_mean_ynorm": round(float(np.mean(sy)), 1)}


def write_three() -> dict:
    """SANITY: draw exactly 3 goals' puck paths, full opacity, each a distinct color, with start (~10s before)
    and shot markers, to confirm we're literally tracing the puck frame-by-frame over the buildup."""
    import hashlib
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    u = universe().select("game_id", "event_id", "season", "attack_sign", "goal_frame")
    u = u.with_columns(h=pl.struct("game_id", "event_id").map_elements(
        lambda s: hashlib.md5(f"{s['game_id']}-{s['event_id']}".encode()).hexdigest(), return_dtype=pl.Utf8)).sort("h")
    picks = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        if not us.height:
            continue
        gids = us["game_id"].unique().to_list()
        pk = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "x_std", "y_std"])
              .filter(pl.col("is_puck") & pl.col("game_id").is_in(gids))
              .join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(xn=pl.col("attack_sign") * pl.col("x_std"), yn=pl.col("attack_sign") * pl.col("y_std"))
              .sort("h", "game_id", "event_id", "frame_index"))
        for (g, e), gp in pk.group_by(["game_id", "event_id"], maintain_order=True):
            xs = gp["xn"].to_numpy(); ys = gp["yn"].to_numpy()
            if len(xs) >= 60:
                picks.append((g, e, xs, ys, gp["h"][0]))
        if len(picks) >= 6:
            break
    picks = sorted(picks, key=lambda r: r[4])[:3]
    colors = ["#ff4d5e", "#41f0a0", "#ffd23f"]
    fig, ax = plt.subplots(figsize=(20, 8.6))
    bg = "#05060a"; fig.patch.set_facecolor(bg); ax.set_facecolor(bg)
    _rink(ax, c="#8fa2c0", lw=1.1, af=0.55, red="#a06070", blue="#5a7aa9")
    for (g, e, xs, ys, _), col in zip(picks, colors):
        ax.plot(xs, ys, "-", color=col, lw=2.0, alpha=1.0, solid_capstyle="round", zorder=5)
        ax.plot(xs, ys, ".", color=col, ms=5, alpha=0.9, zorder=6)                 # every frame as a dot
        ax.plot(xs[0], ys[0], "o", mfc="none", mec=col, mew=2.2, ms=15, zorder=7)   # start (~10s before)
        ax.plot(xs[-1], ys[-1], "*", color=col, ms=26, mec="white", mew=0.8, zorder=8,
                label=f"{g}-{e}  ({len(xs)} frames, {len(xs)/10:.1f}s)")             # shot
    leg = ax.legend(loc="lower left", facecolor="#0c0f16", edgecolor="#333", labelcolor="white", fontsize=11)
    ax.set_title("3 goals' puck paths (full opacity) — ○ = start (~10s before) · ★ = shot · dots = per-frame puck position · "
                 "normalized left→right (net at right)", color="white", fontsize=12, pad=10)
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(C.REPORTS / "puck_three.png", dpi=150, facecolor=bg, bbox_inches="tight")
    plt.close(fig)
    return {"goals": [f"{g}-{e}" for g, e, *_ in picks],
            "shot_points": [[round(float(r[2][-1]), 1), round(float(r[3][-1]), 1)] for r in picks],
            "start_points": [[round(float(r[2][0]), 1), round(float(r[3][0]), 1)] for r in picks]}


if __name__ == "__main__":
    import json, sys
    if "--three" in sys.argv:
        print(json.dumps(write_three(), indent=1))
    elif "--tracers" in sys.argv:
        print(json.dumps(write_tracers(), indent=1))
    elif "--trails" in sys.argv:
        print(json.dumps(write_trails(), indent=1))
    elif "--path" in sys.argv:
        print(json.dumps(write_path(), indent=1))
    else:
        r = write()
        print(json.dumps(r, indent=1))
