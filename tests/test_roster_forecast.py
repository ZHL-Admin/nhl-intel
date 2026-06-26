"""Hermetic tests for the offseason roster forecast (no BigQuery/network).

Everything under test is the PURE CORE of models_ml/project_roster_forecast.py over synthetic
PlayerProj inputs, so the consistency disciplines the rest of the project enforces are guaranteed:
the ledger reconciles, a departed slot is filled at replacement (not dropped, not free), a
no-track-record player never gets a point estimate without a wide band, goalie bands exceed skater
bands, and no /rankings endpoint reads the forecast tables (this is a tool, not a ladder).
"""

import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from models_ml import config                                            # noqa: E402
from models_ml import project_roster_forecast as J                     # noqa: E402
from models_ml.project_roster_forecast import (                        # noqa: E402
    PlayerProj, forecast_team, forecast_band, build_lineup, age_multiplier,
    project_skater_war, project_goalie_war, inflate_arrival_bands, make_player_proj, is_negligible,
)

CFG = config.ROSTER_FORECAST
BASE_COMPONENTS = {"play_5v5": 0.1, "finishing": 0.0, "goaltending": 0.0, "special_teams": 0.0}


def _skater(i, proj, base=None, sd=0.4):
    return PlayerProj(i, f"P{i}", "C", "F", False, base if base is not None else proj, proj, sd, False)


def _full_roster(proj_f=1.5, proj_d=1.2, proj_g=1.0):
    f = [_skater(i, proj_f) for i in range(1, CFG["N_FWD"] + 1)]
    d = [PlayerProj(100 + i, f"D{i}", "D", "D", False, proj_d, proj_d, 0.4, False)
         for i in range(1, CFG["N_DEF"] + 1)]
    g = [PlayerProj(200, "G1", "G", "G", True, proj_g, proj_g, 1.2, False)]
    return f + d + g


def _forecast(base, upd, n_moves, chem=None):
    return forecast_team(base, upd, 0.10, BASE_COMPONENTS, n_moves, xgf_share_delta=chem)


# ---------------------------------------------------------------- ledger reconciliation
def test_ledger_reconciles_to_net_delta():
    base = _full_roster()
    upd = [p for p in base if p.player_id != 1] + [_skater(999, 4.5)]   # swap a depth F for a star
    f = _forecast(base, upd, n_moves=2)
    ledger_sum = sum(m["delta_contribution"] for m in f["ledger"])
    assert abs(ledger_sum - f["net_delta_war"]) < 1e-9, "per-slot contributions must partition the delta"


def test_returning_roster_nets_to_zero_and_is_negligible():
    base = _full_roster()
    upd = [PlayerProj(p.player_id, p.name, p.position, p.pos_group, p.is_goalie,
                      p.base_war, p.projected_war, p.war_sd, p.no_track_record) for p in base]
    f = _forecast(base, upd, n_moves=0)
    assert f["net_delta_war"] == 0.0          # aging cancels for returners (both lineups projected)
    assert f["negligible"] is True            # deep-offseason / quiet-offseason guard fires


# ---------------------------------------------------------------- replacement fill, not zero
def test_departed_slot_filled_at_replacement_not_dropped():
    base = _full_roster()
    departed = next(p for p in base if p.player_id == 1)
    upd = [p for p in base if p.player_id != 1]        # one forward leaves, nobody replaces him
    f = _forecast(base, upd, n_moves=1)
    fwd_slots = [s for s in f["updated_lineup"] if s.pos_group == "F"]
    assert len(fwd_slots) == CFG["N_FWD"], "the lineup keeps its slot count — a hole is never dropped"
    repl = [s for s in fwd_slots if s.replacement]
    assert len(repl) == 1 and repl[0].projected_war == CFG["REPLACEMENT_WAR"], "vacated slot is replacement"
    # the departure COSTS his projected value (not a free hole)
    assert abs(f["net_delta_war"] + departed.projected_war) < 1e-9


# ---------------------------------------------------------------- no-track-record: wide band, no point estimate
def test_no_track_record_gets_replacement_and_wide_band():
    p = make_player_proj(555, "Rookie", "C", {}, {}, {}, {}, {}, True)
    assert p.no_track_record is True
    assert p.projected_war == CFG["REPLACEMENT_WAR"]              # replacement level, never fabricated
    assert p.war_sd == CFG["NO_TRACK_RECORD_WAR_SD"] >= 1.0       # deliberately wide band
    # a roster leaning on no-track value must carry a wider forecast band than a known roster
    known = _full_roster()
    rookie_heavy = [make_player_proj(600 + i, f"R{i}", "C", {}, {}, {}, {}, {}, True)
                    for i in range(CFG["N_FWD"])] + known[CFG["N_FWD"]:]
    assert forecast_band(rookie_heavy, n_moves=12) > forecast_band(known, n_moves=12)


# ---------------------------------------------------------------- goalie band wider than skater band
def test_goalie_band_wider_than_skater_band():
    skater_sd = next(p.war_sd for p in _full_roster() if p.pos_group == "F")
    goalie_sd = next(p.war_sd for p in _full_roster() if p.is_goalie)
    assert goalie_sd > skater_sd, "goalie value is ~3x less reliable by design"
    base = _full_roster()
    with_goalie_move = base[:-1] + [PlayerProj(300, "NewG", "G", "G", True, 2.0, 2.0, 1.2, False)]
    skater_move = base[:-1] + [base[-1], _skater(998, 2.0)]   # add a skater instead
    assert forecast_band(with_goalie_move, 1) > forecast_band(skater_move[:len(base)], 1)


# ---------------------------------------------------------------- multi-season blend (Tier 0)
def test_blend_anchors_projection_to_track_record():
    # a player with a consistent ~0.2 WAR across three full seasons must project NEAR 0.2, not collapse
    # toward replacement (the Byram failure of the old shrink-toward-zero). curve {} -> no aging.
    steady = [(0, 0.20, 82), (1, 0.20, 82), (2, 0.20, 82)]
    proj = project_skater_war(steady, {}, age_t=25)
    assert 0.13 < proj < 0.21, f"established value should be kept, got {proj}"


def test_thin_sample_regresses_harder_than_full_sample():
    # SAME underlying per-82 rate (~0.2), but a 20-game sample is shrunk toward replacement more than a
    # 246-game one — regression is by SAMPLE SIZE, which is what protects depth players automatically.
    thin = [(0, 0.20 * 20 / 82, 20)]                       # 0.2 per-82 over only 20 games
    full = [(0, 0.20, 82), (1, 0.20, 82), (2, 0.20, 82)]   # 0.2 per-82 over 246 games
    assert project_skater_war(thin, {}, 25) < project_skater_war(full, {}, 25)


def test_goalie_projection_is_flat_and_regressed():
    # goalie value is the same blend, held flat (no skater aging curve) and still sample-regressed
    from models_ml.compute_contract_value import blended_war_rate
    seasons = [(0, 0.30, 50), (1, 0.30, 50)]
    blended, _ = blended_war_rate(seasons)
    proj = project_goalie_war(seasons)
    assert proj == blended                       # flat: the shared blend, no skater aging applied
    assert proj < 0.30 * 82 / 50                 # regressed below the raw per-82 rate by sample size


# ---------------------------------------------------------------- Tier 1: arrival band, not point estimate
def test_arrival_band_widens_without_moving_the_projection():
    base = _full_roster()
    arrival = _skater(999, 1.5, sd=0.4)                    # a real player NOT on the base roster
    upd = [p for p in base if p.player_id != 1] + [arrival]
    f = _forecast(base, upd, n_moves=1)
    got = next(p for p in f["updated_lineup"] if p.player_id == 999)
    import math
    assert abs(got.war_sd - math.hypot(0.4, CFG["ARRIVAL_TRANSLATION_SD"])) < 1e-9, "arrival band widened"
    assert got.projected_war == 1.5, "the central projection must be untouched"
    # a holdover (still on the base roster) keeps his raw band
    holdover = next(p for p in f["updated_lineup"] if p.player_id == 2)
    assert holdover.war_sd == 0.4, "holdover band unchanged"


def test_inflate_arrival_bands_is_a_noop_when_disabled():
    lineup = [_skater(11, 1.0, sd=0.5)]
    inflate_arrival_bands(lineup, base_roster_ids=set(), cfg={**CFG, "ARRIVAL_TRANSLATION_SD": 0.0})
    assert lineup[0].war_sd == 0.5


# ---------------------------------------------------------------- aging multiplier is clamped
def test_age_multiplier_clamped():
    blowup = {20: 1.0, 21: 100.0}      # absurd jump
    crash = {30: 100.0, 31: 1.0}       # absurd drop
    assert age_multiplier(blowup, 20) == CFG["AGE_MULT_CEIL"]
    assert age_multiplier(crash, 30) == CFG["AGE_MULT_FLOOR"]
    assert age_multiplier({}, 25) == 1.0           # missing curve -> no aging
    assert age_multiplier({25: -1.0, 26: 1.0}, 25) == 1.0   # non-positive level guarded


# ---------------------------------------------------------------- this is a tool, not a ladder
def test_no_rankings_endpoint_reads_forecast_tables():
    routers = (REPO / "backend" / "routers")
    offenders = []
    for f in routers.glob("rankings*.py"):
        txt = f.read_text()
        if "roster_forecast" in txt or "roster_moves" in txt:
            offenders.append(f.name)
    assert not offenders, f"/rankings must not read the forecast tables: {offenders}"
