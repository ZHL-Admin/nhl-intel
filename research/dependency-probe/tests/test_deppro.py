"""dependency-probe tests — inputs, event->stint join, behavior axes, and the Link A finding
(shot-share moves by partner; shot rate does not). Fast checks on real frozen inputs; no data writes.
"""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from deppro import config, behavior as B, linkA as LA, qaxes as Q  # noqa: E402

SEASON = "2024-25"


def test_frozen_and_enriched_inputs_present():
    for p in ("stints.parquet", "events.parquet", "rapm_variant.parquet"):
        assert (config.ATLAS_PARQUET / p).exists(), p
    # this probe STOPs without the role-fit enriched attribution
    assert (config.ENRICH_DIR / "event_players.parquet").exists()


def test_event_stint_time_join_high_coverage():
    st = B._stints(SEASON)
    ev = B._actor_events(SEASON)
    j = B._locate_in_stint(ev, st)
    assert j.height / ev.height > 0.98            # events locate into their stint


def test_shot_share_is_symmetric():
    b = B.build_behavior(SEASON, write=False).filter(pl.col("shared_toi") >= 6000)
    assert abs(b["A_shot_share"].mean() - 0.5) < 0.02    # directed share averages 0.5 by construction


def test_shot_share_moves_by_partner_but_shot_rate_does_not():
    d = pl.concat([B.build_behavior(s, write=False)
                   for s in ("2022-23", "2023-24", "2024-25")], how="vertical_relaxed")
    d = d.filter(pl.col("shared_toi") >= 6000)
    keep = d.group_by("A", "season_label").len().filter(pl.col("len") >= LA.MIN_PARTNERS)
    d = d.join(keep.select("A", "season_label"), on=["A", "season_label"], how="inner")

    def rel(axis):
        s = d.drop_nulls([f"{axis}_odd", f"{axis}_even"]).with_columns(
            do=pl.col(f"{axis}_odd") - pl.col(f"{axis}_odd").mean().over("A", "season_label"),
            de=pl.col(f"{axis}_even") - pl.col(f"{axis}_even").mean().over("A", "season_label"))
        return LA._wcorr(s["do"].to_numpy(), s["de"].to_numpy(), s["shared_toi"].to_numpy().astype(float))
    assert rel("A_shot_share") > 0.25             # deference genuinely moves by partner
    assert abs(rel("A_sh60")) < 0.12              # shot RATE does not (volume is the player's own)


# ---- Round 2 (Link Q): quality/location are the player's own, not partner tendencies ----
def test_frozen_events_lack_reason_and_exit_events():
    # settles the Q5 icing / Q6 zone-exit drops
    ev = pl.scan_parquet(config.ATLAS_PARQUET / "events.parquet")
    assert "reason" not in ev.collect_schema().names()          # can't identify icing
    types = ev.select("type_desc_key").unique().collect()["type_desc_key"].to_list()
    assert not [t for t in types if any(k in t.lower() for k in ("exit", "entry", "carry", "dump"))]


def test_shot_quality_does_not_move_by_partner():
    d = pl.concat([Q.build_qaxes(s, write=False)
                   for s in ("2023-24", "2024-25")], how="vertical_relaxed").filter(pl.col("shared_toi") >= 6000)
    keep = d.group_by("A", "season_label").len().filter(pl.col("len") >= 3)
    d = d.join(keep.select("A", "season_label"), on=["A", "season_label"], how="inner")

    def rel(ax):
        s = d.drop_nulls([f"{ax}_odd", f"{ax}_even"]).with_columns(
            do=pl.col(f"{ax}_odd") - pl.col(f"{ax}_odd").mean().over("A", "season_label"),
            de=pl.col(f"{ax}_even") - pl.col(f"{ax}_even").mean().over("A", "season_label"))
        return LA._wcorr(s["do"].to_numpy(), s["de"].to_numpy(), s["shared_toi"].to_numpy().astype(float))
    assert rel("xg_per_unb") < 0.15               # shot quality is the player's own, not the partner's
    assert rel("slot_share") < 0.15               # shot location too


# ---- Link B: dependence is real but not a stable buildable trait ----
def test_dependence_is_not_a_stable_trait():
    from deppro import linkB as LB
    dep = LB.build_dependence(LB._load())
    sh = LB._z(LB._z(dep.drop_nulls(["dep_odd", "dep_even"]), "dep_odd"), "dep_even")
    r = LA._wcorr(sh["dep_odd_z"].to_numpy(), sh["dep_even_z"].to_numpy(), np.ones(sh.height))
    assert 0.0 < r < 0.40                          # real (>0) but well below the 0.40 usability bar
    assert dep.drop_nulls("dep")["dep"].median() < 0.10   # dependence magnitude in share-points, modest
