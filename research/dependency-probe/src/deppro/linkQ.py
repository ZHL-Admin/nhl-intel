"""Link Q (GATE) — do quality/location/decision axes move by partner, beyond deployment+opponent?

Reuses the Round-1 test: reliability of A's partner-specific deviation d(A,B) = x − mean_B x, via
split-half of the shared games (odd/even), TOI-weighted, vs a within-player partner-shuffle placebo.
The Round-2 control is SHARPER: residualize each axis on OZ-start share, score-state mix, AND
OPPONENT strength (opp_rapm) during the shared minutes before re-running the test.

Q.VERDICT (pre-stated), per axis: PASS as a real partner-tendency iff raw reliability >= 0.30 AND
placebo p<0.05 AND the deployment+opponent-controlled reliability STAYS >= 0.30 (retains material
movement). Axes that clear raw but drop below 0.30 under the control are deployment-in-disguise; axes
with ~0 reliability are player-constant (a tidy null). Denominator disclosed for every ratio.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import config
from . import qaxes as Q
from .linkA import _wcorr

FLOOR = 6000
MIN_PARTNERS = 3
N_PERM = 500
BAR = 0.30
CTXQ = ["oz_start_share", "share_lead", "share_trail", "opp_rapm"]   # + OPPONENT strength (Round 2)


def _load(floor: int = FLOOR) -> pl.DataFrame:
    d = pl.concat([pl.read_parquet(p) for p in sorted(Q.QDIR.glob("*.parquet"))],
                  how="vertical_relaxed").filter(pl.col("shared_toi") >= floor)
    keep = d.group_by("A", "season_label").len().filter(pl.col("len") >= MIN_PARTNERS)
    return d.join(keep.select("A", "season_label"), on=["A", "season_label"], how="inner")


def _context() -> pl.DataFrame:
    p = pl.read_parquet(config.CHEM_ROOT / "data" / "parquet" / "frozen" / "pairs_corpus.parquet")
    return (p.group_by("season_label", "a", "b").agg(
        oz_start_share=(pl.col("oz_start_share") * pl.col("toi")).sum() / pl.col("toi").sum(),
        share_lead=(pl.col("share_lead") * pl.col("toi")).sum() / pl.col("toi").sum(),
        share_trail=(pl.col("share_trail") * pl.col("toi")).sum() / pl.col("toi").sum(),
        opp_rapm=(pl.col("opp_rapm") * pl.col("toi")).sum() / pl.col("toi").sum()))


def _attach(d: pl.DataFrame) -> pl.DataFrame:
    d = d.with_columns(lo=pl.min_horizontal("A", "B"), hi=pl.max_horizontal("A", "B"))
    return d.join(_context().rename({"a": "lo", "b": "hi"}), on=["season_label", "lo", "hi"], how="left")


def _reliability(d: pl.DataFrame, odd: str, even: str) -> dict:
    s = d.drop_nulls([odd, even])
    s = s.with_columns(do=pl.col(odd) - pl.col(odd).mean().over("A", "season_label"),
                       de=pl.col(even) - pl.col(even).mean().over("A", "season_label"))
    x, y = s["do"].to_numpy(), s["de"].to_numpy()
    w = s["shared_toi"].to_numpy().astype(float)
    r = _wcorr(x, y, w)
    cell = s.select(pl.concat_str([pl.col("A").cast(pl.Utf8), pl.lit("|"), pl.col("season_label")]))
    _, cid = np.unique(cell.to_series().to_numpy(), return_inverse=True)
    rng = np.random.default_rng(config.SEED)
    n = len(y); slot = np.lexsort((np.arange(n), cid)); perms = np.empty(N_PERM)
    for k in range(N_PERM):
        src = np.lexsort((rng.random(n), cid)); p = np.empty(n, dtype=np.int64); p[slot] = src
        perms[k] = _wcorr(x, y[p], w)
    return {"n": s.height, "reliability": r, "placebo_mean": float(np.mean(perms)),
            "p": float((np.sum(perms >= r) + 1) / (N_PERM + 1))}


def _resid_halves(d: pl.DataFrame, ax: str) -> pl.DataFrame:
    sub = d.drop_nulls([f"{ax}_odd", f"{ax}_even"] + CTXQ)
    X = np.column_stack([np.ones(sub.height)] + [sub[c].to_numpy() for c in CTXQ])
    out = sub
    for h in ("odd", "even"):
        y = sub[f"{ax}_{h}"].to_numpy(); beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        out = out.with_columns(pl.Series(f"{ax}_{h}_rax", y - X @ beta))
    return out


def _magnitude(d: pl.DataFrame, ax: str) -> dict:
    """Absolute across-partner spread (median over focal players of the SD of A's axis across partners)
    + the median denominator (denominator-trap disclosure)."""
    sp = d.group_by("A", "season_label").agg(sd=pl.col(ax).std()).drop_nulls()["sd"].median()
    dn = float(d[Q.AXIS_DENOM[ax]].median())
    return {"across_partner_sd_median": float(sp) if sp is not None else None,
            "median_denominator": dn, "denominator_col": Q.AXIS_DENOM[ax],
            "thin_denominator": dn < 20}


def run(floor: int = FLOOR) -> dict:
    d = _attach(_load(floor))
    out = {"seed": config.SEED_TAG, "floor_min": floor // 60, "n_perm": N_PERM, "bar": BAR,
           "dropped_axes": {"Q5_icing": "no `reason` col in frozen events; icing team-only -> not "
                            "individually attributable", "Q6_zone_exit": "no exit/entry/carry event "
                            "type; recovery needs timing-inference (Round-1 lesson) -> dropped"},
           "n_focal_partner_rows": d.height, "axes": {}}
    for ax in Q.AXES:
        raw = _reliability(d, f"{ax}_odd", f"{ax}_even")
        ctrl = _reliability(_resid_halves(d, ax), f"{ax}_odd_rax", f"{ax}_even_rax")
        mag = _magnitude(d, ax)
        passes = (raw["reliability"] >= BAR and raw["p"] < 0.05 and ctrl["reliability"] >= BAR)
        classify = ("real_partner_tendency" if passes else
                    "deployment_in_disguise" if (raw["reliability"] >= BAR and raw["p"] < 0.05
                                                 and ctrl["reliability"] < BAR) else "player_constant")
        out["axes"][ax] = {"raw": raw, "deployment_opp_controlled": ctrl, "magnitude": mag,
                           "passes": passes, "classification": classify}
    out["verdict"] = {"real": [a for a, v in out["axes"].items() if v["passes"]],
                      "deployment_in_disguise": [a for a, v in out["axes"].items()
                                                 if v["classification"] == "deployment_in_disguise"],
                      "player_constant": [a for a, v in out["axes"].items()
                                          if v["classification"] == "player_constant"]}
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "linkQ_analysis.json", "w") as f:
        json.dump(out, f, indent=2)
    return out


if __name__ == "__main__":
    r = run()
    print(f"(A,B) rows: {r['n_focal_partner_rows']}  (Q5 icing / Q6 zone-exit DROPPED — see report)")
    for ax, v in r["axes"].items():
        raw, ctrl, m = v["raw"], v["deployment_opp_controlled"], v["magnitude"]
        thin = " THIN-DENOM" if m["thin_denominator"] else ""
        print(f"  {ax:14s} raw={raw['reliability']:+.3f}(p={raw['p']:.3f}) "
              f"-> +opp-ctrl={ctrl['reliability']:+.3f}  [{v['classification']}]  "
              f"across-SD~{m['across_partner_sd_median']:.3f} denom~{m['median_denominator']:.0f}{thin}")
    print("REAL:", r["verdict"]["real"], "| DEPLOYMENT:", r["verdict"]["deployment_in_disguise"])
