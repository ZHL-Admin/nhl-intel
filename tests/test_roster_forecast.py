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
    shrink_skater_gar, isolate_finishing, make_player_proj, is_negligible,
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
    p = make_player_proj(555, "Rookie", "C", gar_rows={}, goalie_rows={},
                         aging={}, ages={}, archetypes={}, project_value=True)
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


# ---------------------------------------------------------------- regression toward the stable lens
def test_finishing_residual_is_shrunk_hardest():
    # two skaters with equal ev_offense, but one's production is all finishing luck (goals >> ixg)
    lucky = {"ev_offense": 4.0, "pp": 0.0, "ev_defense": 0.0, "pk": 0.0, "penalty": 0.0,
             "faceoff": 0.0, "goals": 4.0, "ixg": 1.0}     # 3.0 of finishing luck
    skilled = {"ev_offense": 4.0, "pp": 0.0, "ev_defense": 0.0, "pk": 0.0, "penalty": 0.0,
               "faceoff": 0.0, "goals": 1.0, "ixg": 4.0}   # sustainable, negative finishing luck
    # the lucky finisher projects below the skilled one despite identical raw ev_offense
    assert shrink_skater_gar(lucky) < shrink_skater_gar(skilled)
    # and a depth player at ~replacement is NOT inflated above replacement by the shrink
    scrub = {"ev_offense": 0.0, "pp": 0.0, "ev_defense": 0.0, "pk": 0.0, "penalty": 0.0,
             "faceoff": 0.0, "goals": 0.0, "ixg": 0.0}
    assert abs(shrink_skater_gar(scrub)) < 1e-9


def test_finishing_isolation_split():
    sust, fin = isolate_finishing(ev_offense=5.0, goals=3.0, ixg=1.0)
    assert fin == 2.0 and sust == 3.0


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
