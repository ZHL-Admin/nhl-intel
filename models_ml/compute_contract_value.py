"""
Contract surplus — the dollar value of a player's PROJECTED on-ice production versus the fixed
cap hit they cost, over the remaining years of their deal (Trade tool P4).

Every number traces to a computed column, in one chain:
  current WAR (nhl_models.player_gar / goalie_gar, season 2025-26)
    -> aged forward each remaining season by the per-archetype aging curve (nhl_models.aging_curves,
       a points/82 LEVEL by age, used as a RATIO vs the player's current age)
    -> priced by a per-position MONOTONE market curve (isotonic AAV-as-a-function-of-WAR fit on the
       league's matched contracts) into an expected AAV the open market would pay for that production
    -> surplus_y = expected_aav_y - cap_hit, summed over remaining years and discounted to present
       value (config.CONTRACT_VALUE['DISCOUNT'] per year).

Grounding rule (no fabricated point estimates): a player with no current-season WAR (injured, just
called up, too few games) is floored NEAR REPLACEMENT with a WIDE band and a `proxy` confidence tag,
never given an invented value. Goalies have no aging curve here (curves are skater points/82), so
goalie WAR is held flat across remaining years and tagged lower-confidence — a documented gap.

Output nhl_models.player_contract_value, one row per matched player on the latest snapshot, carrying
value in BOTH currencies (discounted projected WAR and discounted market dollars) plus surplus and a
confidence band, so the unified tradeable-asset layer can net it cleanly against prospects and picks.

Run:  python -m models_ml.compute_contract_value [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date

import numpy as np
import pandas as pd

from models_ml import bq, config

CV = config.CONTRACT_VALUE
SEASON = "2025-26"
CAP = config.CAP_UPPER_LIMIT_BY_SEASON
CAP_CURRENT = float(CAP[SEASON])            # the season the WAR + market sample are anchored in


def season_str(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[2:]}"


def build_cap_ceilings(horizon: int = 14) -> dict[int, float]:
    """{season_start_year: cap upper limit} — announced values, then CAP_GROWTH_BEYOND_KNOWN beyond.

    The cap is the single biggest long-deal lever: a flat dollar cap hit shrinks as a share of this
    rising ceiling, so a long deal looks better on the cost side once the cap is projected forward.
    """
    known = {int(k[:4]): float(v) for k, v in CAP.items()}
    out = dict(known)
    last = max(known)
    for y in range(min(known), last + horizon + 1):
        if y not in out:
            out[y] = out[y - 1] * (1.0 + config.CAP_GROWTH_BEYOND_KNOWN)
    return out


# --------------------------------------------------------------------------------------------- pulls
def pull_contracts() -> pd.DataFrame:
    """Latest-snapshot player contracts (one row per player) with the cap schedule.

    Sources both SIGNED contracts and PENDING RFAs (mart_player_contracts unions them; an RFA carries
    his PROJECTED next deal as the contract, remaining_years = proj_term, contract_status =
    'rfa_projected'). Both have remaining_years >= 1, so the same valuation runs for both — an RFA's
    cost is just his projected next deal. The projected (vs signed) cost caps RFA confidence at medium
    (handled in compute)."""
    sql = f"""
    select player_id, season, as_of_date, season_start_year, contract_start_year, contract_pos,
           cap_hit, aav, remaining_years, expiry_year, contract_status, is_elc
    from `{bq.project()}.nhl_mart.mart_player_contracts`
    where as_of_date = (select max(as_of_date) from `{bq.project()}.nhl_mart.mart_player_contracts`)
      and remaining_years >= 1
    """
    return bq.query_df(sql)


def pull_war_multi(n_back: int = 5) -> tuple[pd.DataFrame, dict[str, int]]:
    """Up to `n_back` single-season WAR windows (current heaviest) for skaters + goalies, long form.
    Returns (rows, windows) where windows maps season_window -> years_ago (0 = current). The multi-
    season blend (blended_war_rate) keeps one down year from defining a player's projection."""
    y = int(SEASON[:4])
    windows = {season_str(y - k): k for k in range(n_back)}
    inlist = ",".join(f"'{w}'" for w in windows)
    sql = f"""
    select player_id, season_window, position, war, war_sd, games
    from `{bq.project()}.nhl_models.player_gar` where season_window in ({inlist})
    union all
    select goalie_id as player_id, season_window, 'G' as position, war, war_sd, games_played as games
    from `{bq.project()}.nhl_models.goalie_gar` where season_window in ({inlist})
    """
    df = bq.query_df(sql)
    for c in ["war", "war_sd", "games"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    return df, windows


def pull_toi() -> dict[int, float]:
    """All-situations TOI per game for the current season -> {player_id: toi_per_game} (the role axis
    of caliber). Defenders' usage runs high (top-pair ~24-26 min); forwards lower."""
    df = bq.query_df(f"""select player_id, safe_divide(toi_minutes, games) tpg
        from `{bq.project()}.nhl_models.player_situation_toi`
        where season = '{SEASON}' and situation = 'all' and games > 0""")
    return {int(r.player_id): float(r.tpg) for r in df.itertuples() if pd.notna(r.tpg)}


def pull_caliber_contracts() -> pd.DataFrame:
    """Real non-ELC deals (signed, latest snapshot) used to FIT the caliber price curve — ELCs are
    excluded because their cap hit is CBA-capped, not market-set."""
    return bq.query_df(f"""select player_id, cap_hit
        from `{bq.project()}.nhl_mart.mart_player_contracts`
        where as_of_date = (select max(as_of_date) from `{bq.project()}.nhl_mart.mart_player_contracts`)
          and remaining_years >= 1 and not is_elc and cap_hit is not null""")


def build_war_profiles(wdf: pd.DataFrame, windows: dict[str, int]) -> pd.DataFrame:
    """One row per player: blended multi-season WAR + current-season war/sd/games + position group.
    The blended WAR is the projection base; current-season war/sd anchor the market fit and the band."""
    rows = []
    for pid, g in wdf.groupby("player_id"):
        seasons = []; war_cur = sd_cur = None; games_cur = 0.0; pos_cur = None; recent = None
        for _, r in g.iterrows():
            k = windows.get(r["season_window"])
            if k is None or pd.isna(r["war"]):
                continue
            seasons.append((k, float(r["war"]), float(r["games"] or 0)))
            if k == 0:
                war_cur = float(r["war"]); games_cur = float(r["games"] or 0); pos_cur = r["position"]
                sd_cur = float(r["war_sd"]) if pd.notna(r["war_sd"]) else None
            if recent is None or k < recent[0]:
                recent = (k, r["position"])
        if not seasons:
            continue
        bw, gtot = blended_war_rate(seasons)
        pos = pos_cur or (recent[1] if recent else None)
        rows.append({"player_id": int(pid), "pg": pos_group(pos, None),
                     "blended_war": bw, "war_cur": war_cur, "war_sd_cur": sd_cur,
                     "games_cur": games_cur, "games_blended": gtot})
    return pd.DataFrame(rows)


def pull_bio_age(season_start_year_default: int) -> pd.DataFrame:
    """Player age at the snapshot season's start (Oct 1), for the aging curve anchor."""
    df = bq.query_df(f"select player_id, birth_date from `{bq.project()}.nhl_staging.stg_player_bio`")
    df["birth_date"] = pd.to_datetime(df["birth_date"])
    return df


def pull_archetypes() -> pd.DataFrame:
    sql = f"""select player_id, primary_archetype from `{bq.project()}.nhl_models.player_archetypes`
              where season = '{SEASON}'"""
    return bq.query_df(sql)


def pull_curves() -> dict[str, dict[int, float]]:
    """aging_curves -> {archetype: {age: curve_value}}."""
    df = bq.query_df(f"select archetype, age, curve_value from `{bq.project()}.nhl_models.aging_curves`")
    df["curve_value"] = pd.to_numeric(df["curve_value"]).astype("float64")
    out: dict[str, dict[int, float]] = {}
    for arch, g in df.groupby("archetype"):
        out[arch] = dict(zip(g["age"].astype(int), g["curve_value"]))
    return out


# --------------------------------------------------------------------------------- model components
def pos_group(position: str, contract_pos: str) -> str:
    p = ("" if position is None or (isinstance(position, float) and pd.isna(position)) else str(position)).upper()
    contract_pos = "" if contract_pos is None or (isinstance(contract_pos, float) and pd.isna(contract_pos)) else str(contract_pos)
    if p == "G":
        return "G"
    if p == "D":
        return "D"
    if p in ("C", "L", "R", "F"):
        return "F"
    # fall back to the contract's listed position when GAR position is missing
    cp = (contract_pos or "").upper().replace(" ", "")
    if "G" in cp:
        return "G"
    return "D" if cp.replace(",", "") == "D" else "F"


def _band_anchor(war: np.ndarray, share: np.ndarray, p_lo: float, p_hi: float) -> dict:
    """Median (WAR, cap_share) of the deals whose WAR sits in the [p_lo, p_hi] percentile BAND — a
    robust anchor point. A band (not a single quantile) so a thin tail isn't pinned by one or two
    contracts; falls back to everything above p_lo if the band itself is too thin."""
    w_lo, w_hi = float(np.quantile(war, p_lo)), float(np.quantile(war, p_hi))
    m = (war >= w_lo) & (war <= w_hi)
    if int(m.sum()) < 3:
        m = war >= w_lo
    return {"war": float(np.median(war[m])), "share": float(np.median(share[m])),
            "n": int(m.sum()), "war_band": (w_lo, w_hi)}


def fit_market_curves(market: pd.DataFrame) -> dict:
    """Per-position MONOTONE expected-CAP-SHARE(WAR) market curve — the ERA-NEUTRAL benchmark.

    Fit by a TWO-ANCHOR PIVOT on the NON-ELC (free-market) sample (ELCs are CBA-capped, not market-
    set, and would drag the curve down). The curve is log-linear, log(share) = a + b·WAR (b>0, so it
    rises multiplicatively and never plateaus), pinned through two empirical points: a LOW anchor (the
    median going rate in a mid-WAR band — so the median market deal's production is worth ~what it is
    paid and grades fair/C) and a HIGH anchor (observed elite pay in a high-WAR band — so stars stay
    priced right and the elite guard passes). The slope is solved from the two anchors, which rotates
    the curve to lower the middle while holding the top — a degree of freedom a uniform intercept shift
    lacks. A smooth soft-cap (market_cap_share) asymptotes the very top to the CBA max share. Pools all
    skaters for a position group too sparse to fit on its own. cap_share = cap_hit / current cap.
    """
    market = market.copy()
    market["war"] = pd.to_numeric(market["war"]).astype("float64")
    market["cap_share"] = pd.to_numeric(market["cap_share"]).astype("float64")
    # FREE-AGENT market only: drop ELCs so the going rate reflects market-set, not CBA-capped, pay
    if "is_elc" in market.columns:
        market = market[~market["is_elc"].astype(bool)].copy()
    global_max = float(market["cap_share"].max())
    skater = market[market.pg.isin(["F", "D"])]
    p_lo, p_hi = CV["MARKET_ANCHOR_LO"], CV["MARKET_ANCHOR_HI"]
    fits: dict[str, tuple[float, float, float]] = {}
    top_war: dict[str, float] = {}
    anchors: dict[str, dict] = {}
    ceil: dict[str, float] = {}
    knee: dict[str, float] = {}
    for pg in ["F", "D", "G"]:
        g = market[market.pg == pg]
        if len(g) < CV["MARKET_MIN_N"] and pg in ("F", "D"):
            g = skater
        war = pd.to_numeric(g["war"]).to_numpy(dtype="float64")
        share = pd.to_numeric(g["cap_share"]).to_numpy(dtype="float64")
        lo = _band_anchor(war, share, *p_lo)                  # median going rate (mid-WAR)
        hi = _band_anchor(war, share, *p_hi)                  # observed elite pay (high-WAR)
        b = (math.log(hi["share"]) - math.log(lo["share"])) / max(hi["war"] - lo["war"], 1e-6)
        b = max(b, 1e-6)                                       # guarantee monotone-increasing
        a = math.log(lo["share"]) - b * lo["war"]             # intercept folded in; shift retired -> 0
        fits[pg] = (float(a), float(b), 0.0)
        # PER-POSITION soft-cap: the ceiling is this position's own observed max contract, not the
        # global max (a D should asymptote to the top D deal ~$12M, not a forward's ~$18M). A steep
        # pivot curve now actually reaches its ceiling, so the ceiling must be position-correct.
        own = market[market.pg == pg]["cap_share"]
        pg_max = float(own.max()) if len(own) else global_max
        ceil[pg] = pg_max * CV["MARKET_CEIL_MULT"]
        knee[pg] = ceil[pg] * CV["MARKET_KNEE_FRAC"]
        top_war[pg] = float(np.quantile(own, 0.9)) if len(own) else 99.0
        anchors[pg] = {"lo": lo, "hi": hi}
    return {"fits": fits, "ceil": ceil, "knee": knee, "top_war": top_war, "anchors": anchors}


def market_cap_share(market: dict, pg: str, war: float) -> float:
    """Expected CAP SHARE for a production level: log-linear, then a smooth soft-cap to the position's
    max-contract share. The soft-cap keeps a positive slope everywhere (asymptotes, never a hard
    plateau). ceil/knee may be per-position dicts (production) or scalars (hermetic tests)."""
    a, b, shift = market["fits"][pg]
    raw = float(np.exp(a + b * war + shift))
    ceil, knee = market["ceil"], market["knee"]
    if isinstance(ceil, dict):
        ceil, knee = ceil[pg], knee[pg]
    if raw < knee:
        return raw
    return knee + (ceil - knee) * (1.0 - np.exp(-(raw - knee) / (ceil - knee)))


# ----------------------------------------------------------------- projection base + market-comp v2
# The grade is part "is he worth it" (the player's own projected production) and part "what's the
# going rate for this type of player" (a market-comparables prior). For a young or thin-sample player
# the individual estimate is incomplete (it misses upside/term/role the market prices), so we shrink
# toward the cohort going-rate; for an established player we trust the model. Implemented as an
# "effective WAR" so the existing aging/pricing pipeline (project_one) is untouched.
PROJ = {
    "SEASON_WEIGHTS": [5.0, 4.0, 3.0, 2.0, 1.0],  # up to 5 seasons, current heaviest (one down year dilutes)
    "REGRESS_GAMES": 35,                 # shrink the multi-season rate toward replacement by sample
    "CRED_GAMES": 60,                    # sample at which the model earns ~half its games-credibility
    "AGE_FULL": 26,                      # at/after this age the model's read is treated as complete
    "AGE_FLOOR": 0.35,                   # min age-completeness weight for the youngest players
    "ROLE_TIERS": ("depth", "mid", "top"),
}


def blended_war_rate(seasons: list[tuple[int, float, float]]) -> tuple[float, float]:
    """Recency- and games-weighted, lightly sample-regressed per-82 WAR from up to 3 single seasons.
    seasons = [(years_ago, war_total, games), ...]; years_ago 0 = current. Returns (rate, total_games).
    A single down year no longer defines the projection (the Larkin case)."""
    num = den = g_tot = 0.0
    for yrs_ago, war, games in seasons:
        if games and games > 0 and yrs_ago < len(PROJ["SEASON_WEIGHTS"]):
            rate = war * 82.0 / games                     # per-82 rate
            w = PROJ["SEASON_WEIGHTS"][yrs_ago] * games    # weight by recency AND sample
            num += w * rate; den += w; g_tot += games
    if den <= 0:
        return CV["REPLACEMENT_WAR"], 0.0
    rate = num / den
    reg = g_tot / (g_tot + PROJ["REGRESS_GAMES"])         # shrink thin samples toward replacement
    return rate * reg, g_tot


def credibility(games: float, age: int) -> float:
    """Weight on the MODEL value vs the market-comp prior. Rises with sample size and age — a young or
    thin-sample player leans on the cohort going-rate; an established one leans on his own production."""
    sample = games / (games + PROJ["CRED_GAMES"])
    age_w = max(PROJ["AGE_FLOOR"], min(1.0, (age - 20) / (PROJ["AGE_FULL"] - 20)))
    return sample * age_w


def role_tier(toi_per_game: float | None, thresholds: tuple[float, float]) -> str:
    """'top' | 'mid' | 'depth' from TOI/game against this position's (t1, t2) tercile cuts."""
    if toi_per_game is None:
        return "mid"
    t1, t2 = thresholds
    return "top" if toi_per_game >= t2 else "depth" if toi_per_game < t1 else "mid"


def inverse_market_share(market: dict, pg: str, share: float) -> float:
    """Invert the log-linear market curve (share -> WAR) so a blended cap-share can re-enter the
    WAR-based projection. Inverts the pre-soft-cap form (blended shares sit in the linear range)."""
    a, b, shift = market["fits"][pg]
    return (math.log(max(share, 1e-6)) - a - shift) / max(b, 1e-6)


def effective_war(blended_war: float, pg: str, tier: str, games: float, age: int,
                  market: dict, comp_shares: dict) -> float:
    """Blend the model's WAR-priced cap-share with the cohort going-rate by credibility, then invert
    back to an 'effective WAR' the projection consumes. comp_shares: {(pg, tier): going-rate share}."""
    model_share = market_cap_share(market, pg, blended_war)
    comp_share = comp_shares.get((pg, tier))
    # ONE-SIDED: the market comp is a going-rate FLOOR for this role — it lifts a player the model
    # values BELOW his cohort (young/undervalued), but never drags down one already worth more.
    if comp_share is None or comp_share <= model_share:
        return blended_war
    w = credibility(games, age)
    blended_share = w * model_share + (1.0 - w) * comp_share
    return inverse_market_share(market, pg, blended_share)


# --------------------------------------------------------- caliber-market grade (the live model, v3)
# The grade is part "is he worth it" (intrinsic, his own multi-season production) and part "what's the
# going rate for this caliber of player" (a market-comparables floor). Caliber = a continuous blend of
# role/usage (TOI/game percentile) and production (blended-WAR percentile) within position; the league
# prices that caliber log-linearly from real non-ELC contracts. A player is valued at the HIGHER of
# his intrinsic worth and his caliber's going rate (the floor lifts WAR-underrated players — usually
# young or thin-sample — without compressing the elite, whose intrinsic worth already exceeds it). The
# value is expressed back as an 'effective WAR' so the existing aging/pricing pipeline is untouched.
# These functions are shared by the batch job and the live Contract Grader service so they cannot drift.
W_ROLE, W_PROD = 0.65, 0.35   # caliber = role(usage) + production, slight role lean (the league's vote)


def build_caliber_market(profiles: pd.DataFrame, fit_contracts: pd.DataFrame,
                         cap_current: float) -> dict:
    """Fit the market 'going rate' as a continuous function of caliber, per position.

    profiles: one row per player with [player_id, pg, war (BLENDED multi-season), toi (per-game, may be
      NaN)] — the reference pool whose distributions define each position's caliber percentiles.
    fit_contracts: [player_id, cap_hit] real non-ELC deals; their (caliber -> cap_share) points fit the
      per-position price curve log(cap_share) = a + b·caliber. Returns the ref distributions, the fits,
      per-position elite soft-caps, and a caliber_of() scorer.
    """
    ref = {pg: {"toi": np.sort(g["toi"].values), "war": np.sort(g["war"].values)}
           for pg, g in profiles.dropna(subset=["toi"]).groupby("pg")}

    def caliber_of(pg: str, toi_v, war_v) -> float:
        d = ref.get(pg)
        if not d:
            return 0.5
        rp = (np.searchsorted(d["toi"], toi_v) / max(1, len(d["toi"]))) if toi_v is not None else 0.5
        pp = np.searchsorted(d["war"], war_v) / max(1, len(d["war"]))
        return float(W_ROLE * rp + W_PROD * pp)

    cmap = profiles.drop_duplicates("player_id").set_index("player_id")
    pts: dict = {}
    for _, r in fit_contracts.iterrows():
        pid = r["player_id"]
        if pid not in cmap.index:
            continue
        row = cmap.loc[pid]
        toi_v = row["toi"] if pd.notna(row["toi"]) else None
        cal = caliber_of(row["pg"], toi_v, row["war"])
        pts.setdefault(row["pg"], []).append((cal, float(r["cap_hit"]) / cap_current))
    fits, caps = {}, {}
    for pg, arr in pts.items():
        if len(arr) < 8:
            continue
        cal = np.array([a for a, _ in arr]); share = np.array([s for _, s in arr])
        b, a = np.polyfit(cal, np.log(share), 1)
        fits[pg] = (float(a), max(float(b), 1e-6))
        caps[pg] = float(share.max()) * 1.05      # soft cap at ~5% over the richest comparable
    return {"ref": ref, "fits": fits, "caps": caps, "caliber_of": caliber_of}


def caliber_market_share(cm: dict, pg: str, toi, war: float):
    """Predicted market cap-share for a player's caliber (what his comparable cohort signs for)."""
    if pg not in cm["fits"]:
        return None, None
    cal = cm["caliber_of"](pg, toi, war)
    a, b = cm["fits"][pg]
    raw = math.exp(a + b * cal)
    return min(raw, cm["caps"].get(pg, raw)), cal


def value_effective_war(market: dict, cm: dict, pg: str, blended_war: float, toi) -> float:
    """The grade's value as an effective WAR: the HIGHER of intrinsic worth (his blended WAR priced by
    the market curve) and his caliber's going rate (the floor), inverted back to a WAR the projection
    consumes. Elite players keep their (larger) intrinsic value; underrated ones are lifted to the floor.

    Goalies are exempt from the caliber floor: caliber's role axis is TOI/game, which barely varies
    between goalies (a starter plays ~60 min whenever he starts), so the fit degenerates to a flat floor
    that would pin every goalie to the same inflated WAR. Goalies use their intrinsic blended WAR."""
    if pg == "G":
        return blended_war
    intrinsic = market_cap_share(market, pg, blended_war)
    mkt_share, _cal = caliber_market_share(cm, pg, toi, blended_war)
    return inverse_market_share(market, pg, max(intrinsic, mkt_share or 0.0))


def aging_ratio(curve: dict[int, float] | None, base_age: int, target_age: int) -> float:
    """curve_value(target)/curve_value(base), snapped to the nearest covered age; flat if absent."""
    if not curve:
        return 1.0
    ages = sorted(curve)
    nearest = lambda a: min(ages, key=lambda x: abs(x - a))  # snap over gaps + clamp past the ends
    b = curve[nearest(base_age)]
    t = curve[nearest(target_age)]
    if b <= 0:
        return 1.0
    return float(t / b)


def project_one(war: float, base_age: int, remaining: int, pg: str,
                curve: dict[int, float] | None, cap_hit: float, market: dict, discount: float,
                proj_start_year: int, cap_ceilings: dict[int, float]) -> dict:
    """Project value -> expected cap SHARE -> surplus over the remaining years, with the cap projected
    FORWARD. For each year: actual_cap_share = flat cap_hit / that season's (rising) cap, so it
    declines; expected_cap_share = curve(aged WAR); surplus_y = expected - actual (era-neutral). The
    comparison is done in cap-share, then dollarized per year by that season's cap. Talent WAR is
    unchanged. Returns aggregates + the per-year cap-share schedule."""
    goalie_flat = pg == "G" and CV["GOALIE_AGING_FLAT"]
    war_path, val_dollar_path, sched, surplus_share_path, disc = [], [], [], [], []
    for k in range(remaining):
        age_k = base_age + k
        r = 1.0 if goalie_flat else aging_ratio(curve, base_age, age_k)
        wk = war * r
        cap_y = cap_ceilings[proj_start_year + k]
        exp_share = market_cap_share(market, pg, wk)
        act_share = cap_hit / cap_y
        war_path.append(wk)
        val_dollar_path.append(exp_share * cap_y)              # cap-aware expected $ value of production
        surplus_share_path.append(exp_share - act_share)
        disc.append(discount ** k)
        sched.append({"season": season_str(proj_start_year + k), "cap": round(cap_y),
                      "actual_share": round(act_share, 4), "expected_share": round(exp_share, 4),
                      "surplus_share": round(exp_share - act_share, 4),
                      # per-year detail for the transparency layer (nominal $ that season; no extra modelling)
                      "age": int(age_k), "projected_war": round(wk, 2),
                      "fair_value_dollars": round(exp_share * cap_y),
                      "cap_hit_dollars": round(cap_hit),
                      "surplus_dollars": round(exp_share * cap_y - cap_hit)})
    disc = np.array(disc)
    val_dollar = np.array(val_dollar_path)
    surplus_share = np.array(surplus_share_path)
    surplus_dollar = val_dollar - cap_hit                       # per-year $ surplus (flat cost)
    return {
        "value_war": float(np.dot(war_path, disc)),
        "value_dollars": float(np.dot(val_dollar, disc)),
        "cost_dollars": float(cap_hit * disc.sum()),
        "expected_value_now": float(val_dollar[0]),
        "surplus_current": float(surplus_dollar[0]),
        "total_surplus": float(np.sum(surplus_dollar)),
        "total_discounted_surplus": float(np.dot(surplus_dollar, disc)),
        "surplus_current_share": float(surplus_share[0]),
        "total_discounted_surplus_share": float(np.dot(surplus_share, disc)),
        "schedule": sched,
    }


# --------------------------------------------------------------------------------------------- main
def compute() -> pd.DataFrame:
    contracts = pull_contracts()
    war_multi, windows = pull_war_multi()
    toi = pull_toi()
    bio = pull_bio_age(0)
    arch = pull_archetypes()
    curves = pull_curves()

    # per-player blended multi-season WAR + current-season anchors + position
    prof = build_war_profiles(war_multi, windows)
    prof["toi"] = prof["player_id"].map(toi)

    df = (contracts
          .merge(prof, on="player_id", how="left")
          .merge(bio, on="player_id", how="left")
          .merge(arch, on="player_id", how="left"))

    # base age at the snapshot season start (Oct 1 of season_start_year)
    def base_age(row) -> int | None:
        if pd.isna(row["birth_date"]):
            return None
        anchor = date(int(row["season_start_year"]), 10, 1)
        return int((pd.Timestamp(anchor) - row["birth_date"]).days // 365.25)
    df["age"] = df.apply(base_age, axis=1)
    # position group: from WAR data when present, else fall back to the contract's listed position
    df["pg"] = df.apply(lambda r: r["pg"] if pd.notna(r["pg"]) else pos_group(None, r.get("contract_pos")), axis=1)

    cap_ceilings = build_cap_ceilings()
    flat_ceilings = {y: CAP_CURRENT for y in cap_ceilings}   # cap frozen at current — before/after baseline

    # market curve fit on GROUNDED matched players, in CAP SHARE = actual cap hit / current-season cap
    # (fit on CURRENT-season WAR vs cap_share — the era-neutral price of production this season)
    market_src = df[df["war_cur"].notna() & df["aav"].notna()][["pg", "war_cur", "aav", "cap_hit", "is_elc"]].copy()
    market_src = market_src.rename(columns={"war_cur": "war"})
    market_src["cap_share"] = pd.to_numeric(market_src["cap_hit"]) / CAP_CURRENT
    market = fit_market_curves(market_src)        # fits on NON-ELC deals (is_elc filtered inside)

    # caliber market: the going rate as a function of role(TOI)+production(blended WAR) percentile, fit
    # on real non-ELC deals — a floor that lifts players the WAR model underrates (young/thin-sample)
    cal_profiles = prof[["player_id", "pg", "blended_war", "toi"]].rename(columns={"blended_war": "war"})
    cm = build_caliber_market(cal_profiles, pull_caliber_contracts(), CAP_CURRENT)

    rows = []
    for _, r in df.iterrows():
        pg = r["pg"]
        cap_hit = float(r["cap_hit"]) if pd.notna(r["cap_hit"]) else 0.0
        remaining = int(r["remaining_years"])
        age = int(r["age"]) if pd.notna(r["age"]) else 27   # league-ish default if bio missing
        curve = curves.get(r.get("primary_archetype")) or curves.get(CV["AGE_FALLBACK"].get(pg))

        grounded = pd.notna(r["blended_war"])
        games = float(r["games_blended"]) if pd.notna(r["games_blended"]) else 0.0
        games_now = float(r["games_cur"]) if pd.notna(r["games_cur"]) else games
        if grounded:
            # value = HIGHER of intrinsic worth and his caliber's going rate, as an effective WAR
            toi_v = r["toi"] if pd.notna(r["toi"]) else None
            war = value_effective_war(market, cm, pg, float(r["blended_war"]), toi_v)
            sd = float(r["war_sd_cur"]) if pd.notna(r["war_sd_cur"]) else CV["PROXY_WAR_BAND"]
            band = CV["BAND_SDS"] * sd
            # high confidence needs a real multi-season sample (mirrors the live grader)
            confidence = "high" if (games >= CV["GROUNDED_MIN_GAMES"] * 2 and pg != "G") else "medium"
            # top-decile production: few comparables price it, so widen the band + lower confidence
            if war >= market["top_war"].get(pg, 99.0):
                band *= CV["TOP_DECILE_BAND_MULT"]
                confidence = "medium"
        else:
            # cannot ground -> floor near replacement with a wide band + proxy tag (never invent)
            war = CV["REPLACEMENT_WAR"]
            band = CV["PROXY_WAR_BAND"]
            confidence = "proxy"

        # the deal's seasons run from the later of the snapshot season and the contract's own start
        # (a not-yet-started extension is valued over the seasons it actually covers)
        cstart = int(r["contract_start_year"]) if pd.notna(r["contract_start_year"]) else int(r["season_start_year"])
        proj_start = max(int(r["season_start_year"]), cstart)

        # PENDING RFA: his cost is a PROJECTED next deal (not a signed one), so the cost side is less
        # certain — cap a 'high' confidence at 'medium'. (His talent WAR is unchanged; he is valued by
        # the same projection as a signed player, just over his projected term.)
        if str(r.get("contract_status")) == "rfa_projected" and confidence == "high":
            confidence = "medium"

        args = (age, remaining, pg, curve, cap_hit, market, CV["DISCOUNT"], proj_start, cap_ceilings)
        mid = project_one(war, *args)
        lo = project_one(war - band, *args)
        hi = project_one(war + band, *args)
        # "flat" baseline: the same projection with the cap FROZEN at the current season (no forward
        # growth) — isolates exactly what the cap projection changes, for the before/after report.
        flat = project_one(war, age, remaining, pg, curve, cap_hit, market, CV["DISCOUNT"],
                           proj_start, flat_ceilings)

        rows.append({
            "player_id": int(r["player_id"]),
            "season": r["season"], "as_of_date": r["as_of_date"],
            "pos_group": pg, "age": age, "primary_archetype": r.get("primary_archetype"),
            "cap_hit": int(cap_hit), "aav": int(r["aav"]) if pd.notna(r["aav"]) else None,
            "remaining_years": remaining,
            "war_now": round(war, 3), "war_sd": round(band, 3), "games_now": games_now,
            # talent axis (WAR unchanged; dollars are now cap-aware via the rising-cap projection)
            "value_war": round(mid["value_war"], 2),
            "value_war_low": round(lo["value_war"], 2), "value_war_high": round(hi["value_war"], 2),
            "value_dollars": round(mid["value_dollars"]),
            "value_dollars_low": round(lo["value_dollars"]), "value_dollars_high": round(hi["value_dollars"]),
            "expected_value_now": round(mid["expected_value_now"]),
            # cost axis
            "cost_dollars": round(mid["cost_dollars"]),
            # surplus — DOLLARS (per-year cap-share dollarized by each season's projected cap)
            "surplus_current": round(mid["surplus_current"]),
            "total_surplus": round(mid["total_surplus"]),
            "total_discounted_surplus": round(mid["total_discounted_surplus"]),
            "surplus_low": round(lo["total_discounted_surplus"]),
            "surplus_high": round(hi["total_discounted_surplus"]),
            # surplus — CAP SHARE (era-neutral); the unit the comparison is actually made in
            "surplus_current_share": round(mid["surplus_current_share"], 4),
            "total_discounted_surplus_share": round(mid["total_discounted_surplus_share"], 4),
            "surplus_share_low": round(lo["total_discounted_surplus_share"], 4),
            "surplus_share_high": round(hi["total_discounted_surplus_share"], 4),
            # flat-cap baseline (cap frozen at current) for the before/after report
            "surplus_flat_dollars": round(flat["total_discounted_surplus"]),
            # cap-growth component: how much of the surplus comes purely from a flat $ cap hit shrinking
            # against a rising cap (forward minus frozen-cap). Real asset value, decomposed not stripped.
            "cap_growth_surplus": round(mid["total_discounted_surplus"] - flat["total_discounted_surplus"]),
            # per-year cap-share schedule (declining actual share as the cap rises) — inspectable
            "cap_share_schedule": json.dumps(mid["schedule"]),
            "is_grounded": bool(grounded),
            "confidence": confidence,
            "model_version": CV["MODEL_VERSION"],
        })
    return pd.DataFrame(rows), market, market_src


def _report(df: pd.DataFrame) -> None:
    names = {}
    ids = df["player_id"].tolist()
    if ids:
        nm = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) name
            from `{bq.project()}.nhl_staging.stg_rosters`
            where player_id in ({",".join(str(i) for i in set(ids))}) group by 1""")
        names = dict(zip(nm["player_id"], nm["name"]))
    n = len(df)
    prox = (df["confidence"] == "proxy").sum()
    print(f"\nplayer_contract_value: {n} players  "
          f"(grounded {df['is_grounded'].sum()}, proxy {prox}; "
          f"conf high {sum(df.confidence=='high')}/med {sum(df.confidence=='medium')}/proxy {prox})")

    def fmt(v):  # dollars -> $X.YM
        return f"${v/1e6:+.1f}M"
    top = df.sort_values("total_discounted_surplus", ascending=False).head(10)
    print("\n=== Best surplus (PV of remaining deal) ===")
    for _, r in top.iterrows():
        print(f"  {names.get(r.player_id, r.player_id):22s} [{r.pos_group}] "
              f"surplus {fmt(r.total_discounted_surplus)}  "
              f"(cap ${r.cap_hit/1e6:.1f}M x {r.remaining_years}y, WAR {r.war_now:+.1f}, {r.confidence})")
    bot = df.sort_values("total_discounted_surplus").head(8)
    print("\n=== Worst surplus (overpaid) ===")
    for _, r in bot.iterrows():
        print(f"  {names.get(r.player_id, r.player_id):22s} [{r.pos_group}] "
              f"surplus {fmt(r.total_discounted_surplus)}  "
              f"(cap ${r.cap_hit/1e6:.1f}M x {r.remaining_years}y, WAR {r.war_now:+.1f}, {r.confidence})")


def _names_for(ids) -> dict:
    if not len(ids):
        return {}
    nm = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) name
        from `{bq.project()}.nhl_staging.stg_rosters`
        where player_id in ({",".join(str(int(i)) for i in set(ids))}) group by 1""")
    return dict(zip(nm["player_id"], nm["name"]))


def _acceptance(df: pd.DataFrame, market: dict, market_src: pd.DataFrame) -> None:
    """Assert + print the acceptance checks: the cap-share curve stays monotone/non-plateaued, the
    stars stay sane, and the cap projection (flat-dollar vs cap-share forward) reads as expected."""
    names = _names_for(df["player_id"].tolist())
    # (1) the market curve is monotone & rising across the REAL production range (no hard plateau).
    # The grid tops out at this position's 95th-percentile observed WAR, not a fictional WAR=6 no
    # player reaches — a correct soft-cap is SUPPOSED to saturate before then, so testing the tail at 6
    # asserts a property that cannot hold. Threshold unchanged (top must exceed mid by 1.05x).
    for pg in ["F", "D", "G"]:
        gp = market_src[(market_src.pg == pg) & (~market_src["is_elc"].astype(bool))]
        war95 = float(np.quantile(gp["war"], 0.95)) if len(gp) else 3.5
        grid = np.linspace(-1.0, war95, 29)
        curve = np.array([market_cap_share(market, pg, w) for w in grid])
        assert np.all(np.diff(curve) >= -1e-9), f"{pg} cap-share curve not monotone"
        assert curve[-1] > curve[len(grid) // 2] * 1.05, \
            f"{pg} cap-share curve plateaus (top@war={war95:.1f} <= mid x1.05)"

    # (2) top-decile production prices within a realistic band of OBSERVED elite AAVs (share x cap).
    # Compared on NON-ELC deals only (the market curve is fit on non-ELC; cheap high-WAR ELCs would
    # otherwise deflate the observed-elite benchmark and make the guard pass spuriously).
    print("\n=== Cap-share market curve (top decile tracks elite AAVs, not a plateau) ===")
    anchors = market.get("anchors", {})
    for pg in ["F", "D"]:
        g = market_src[(market_src.pg == pg) & (~market_src["is_elc"].astype(bool))]
        thr = float(np.quantile(g["war"], 0.9))
        obs_elite = float(g[g["war"] >= thr]["aav"].mean())
        pred = market_cap_share(market, pg, thr) * CAP_CURRENT
        ratio = pred / obs_elite
        ac = anchors.get(pg, {})
        lo, hi = ac.get("lo", {}), ac.get("hi", {})
        print(f"  {pg}: war>={thr:.1f}  predicted ${pred/1e6:4.1f}M  vs observed-elite mean "
              f"${obs_elite/1e6:4.1f}M  (x{ratio:.2f})")
        if lo and hi:
            print(f"      anchors: LO war={lo['war']:.2f} share={lo['share']*100:.1f}% (n={lo['n']}, "
                  f"war∈[{lo['war_band'][0]:.2f},{lo['war_band'][1]:.2f}])  "
                  f"HI war={hi['war']:.2f} share={hi['share']*100:.1f}% (n={hi['n']}, "
                  f"war∈[{hi['war_band'][0]:.2f},{hi['war_band'][1]:.2f}])")
        assert 0.75 <= ratio <= 1.6, f"{pg} top-decile price ${pred/1e6:.1f}M off elite ${obs_elite/1e6:.1f}M"

    # (3) before/after — flat-dollar surplus vs cap-share FORWARD surplus (PV of the remaining deal)
    stars = [8478864, 8477934, 8478403]                     # Kaprizov $17M, Draisaitl $14M, Eichel $13.5M
    ref = df[df.is_grounded].copy()
    young_long = ref[(ref.age <= 22) & (ref.remaining_years >= 6)].sort_values("war_now", ascending=False)
    short_vet = ref[(ref.age >= 31) & (ref.remaining_years <= 2)].sort_values("cap_hit", ascending=False)
    picks = list(stars)
    if not young_long.empty: picks.append(int(young_long.iloc[0].player_id))
    if not short_vet.empty: picks.append(int(short_vet.iloc[0].player_id))

    print("\n=== Cap projection: flat-dollar surplus  ->  cap-share forward surplus (PV, remaining deal) ===")
    print(f"  {'player':18s} {'WAR':>4s} {'cap$M':>6s} {'yrs':>4s} {'flat$M':>8s} {'fwd$M':>8s} {'Δ$M':>6s}")
    for pid in picks:
        row = df[df.player_id == pid]
        if row.empty:
            continue
        r = row.iloc[0]
        flat, fwd = r.surplus_flat_dollars / 1e6, r.total_discounted_surplus / 1e6
        print(f"  {names.get(pid, str(pid)):18s} {r.war_now:4.1f} {r.cap_hit/1e6:6.1f} {r.remaining_years:4d} "
              f"{flat:+8.1f} {fwd:+8.1f} {fwd-flat:+6.1f}")
        if pid in stars:                                    # stars stay sane (recalibration handled magnitude)
            assert r.surplus_current / 1e6 >= -4.0, f"{pid} reads {r.surplus_current/1e6:.1f}M/yr (too negative)"
        # the rising cap can only help (or not change) a flat-dollar deal's cost side
        assert fwd >= flat - 0.05, f"{pid} forward surplus below flat ({fwd:.1f} < {flat:.1f})"

    # (4) the per-year cap share declines across a sample long contract (cap rises, cap hit is flat)
    long_row = df[(df.remaining_years >= 6)].sort_values("cap_hit", ascending=False).iloc[0]
    sched = json.loads(long_row.cap_share_schedule)
    print(f"\n=== Per-year cap share — {names.get(long_row.player_id, long_row.player_id)} "
          f"(${long_row.cap_hit/1e6:.1f}M flat, declining as the cap rises) ===")
    print("  " + "  ".join(f"{s['season']}:{s['actual_share']*100:.1f}%" for s in sched))
    shares = [s["actual_share"] for s in sched]
    assert shares == sorted(shares, reverse=True), "actual cap share should decline over the term"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df, market, market_src = compute()
    _report(df)
    _acceptance(df, market, market_src)

    if args.dry_run:
        print("\n[dry-run] not written")
        return
    bq.write_df(df, "player_contract_value", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["pos_group", "player_id"])
    print(f"\nWrote {len(df)} rows to nhl_models.player_contract_value.")


if __name__ == "__main__":
    main()
