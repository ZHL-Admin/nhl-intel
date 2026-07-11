"""Regenerate report figures from the cached Parquet corpus (Phase 6.3, `make report`).

No BigQuery, no network — everything is recomputed from data/parquet/. The
narrative reports/phase*.md are version-controlled prose; this rebuilds the
machine-generated figures they cite.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from . import config, sources


def _toi_hist() -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    shifts = pl.read_parquet(sources.SHIFTS_PARQUET)
    toi = pl.read_parquet(sources.BOXSCORE_TOI_PARQUET)
    ss = shifts.group_by("game_id", "player_id").agg(pl.col("duration_seconds").sum().alias("s"))
    m = ss.join(toi.select("game_id", "player_id", "toi_seconds"), on=["game_id", "player_id"], how="inner")
    d = (m["s"] - m["toi_seconds"]).to_numpy()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(d.clip(-120, 120), bins=121, color="#2b6cb0")
    ax.axvline(-30, color="#c53030", ls="--", lw=1); ax.axvline(30, color="#c53030", ls="--", lw=1)
    ax.set_title("TOI reconciliation delta (shift-sum − boxscore TOI)")
    ax.set_xlabel("seconds (clipped ±120)"); ax.set_ylabel("player-games")
    ax.text(0.02, 0.95, f"within ±30s: {(np.abs(d)<=30).mean():.3%}", transform=ax.transAxes, va="top")
    out = config.REPORTS_DIR / "figures" / "toi_delta_hist.png"
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=110); plt.close(fig)
    return str(out)


def _xg_calibration() -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xg = pl.read_parquet(config.PARQUET_DIR / "shot_xg.parquet").filter(
        pl.col("season_start_year") >= 2022)
    x = xg["xg"].to_numpy(); y = xg["is_goal"].to_numpy()
    edges = np.quantile(x, np.linspace(0, 1, 11)); edges[0], edges[-1] = -1, 2
    idx = np.digitize(x, edges[1:-1])
    pred = [x[idx == b].mean() for b in range(10)]; act = [y[idx == b].mean() for b in range(10)]
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, .25], [0, .25], "--", c="#888", label="perfect")
    ax.plot(pred, act, "o-", c="#2b6cb0", label="production shot_xg (2022-25 reg)")
    ax.set_xlabel("predicted xG (bin mean)"); ax.set_ylabel("actual goal rate")
    ax.set_title("xG calibration (10 quantile bins)"); ax.legend(); ax.grid(alpha=.3)
    out = config.REPORTS_DIR / "figures" / "xg_calibration.png"
    fig.savefig(out, dpi=110); plt.close(fig)
    return str(out)


def main() -> int:
    print("regenerating figures from cache ...")
    print("  ", _toi_hist())
    print("  ", _xg_calibration())
    reports = sorted(config.REPORTS_DIR.glob("phase*.md")) + [config.REPORTS_DIR / "FINDINGS.md",
                                                              config.REPORTS_DIR / "upstream-ledger.md"]
    print("narrative reports present:")
    for r in reports:
        print(f"  {'OK ' if Path(r).exists() else 'MISSING'} {r.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
