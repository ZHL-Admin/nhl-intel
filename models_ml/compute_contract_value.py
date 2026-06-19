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
    """Latest-snapshot player contracts (one row per player) with the cap schedule."""
    sql = f"""
    select player_id, season, as_of_date, season_start_year, contract_start_year, contract_pos,
           cap_hit, aav, remaining_years, expiry_year
    from `{bq.project()}.nhl_mart.mart_player_contracts`
    where as_of_date = (select max(as_of_date) from `{bq.project()}.nhl_mart.mart_player_contracts`)
      and remaining_years >= 1
    """
    return bq.query_df(sql)


def pull_war() -> pd.DataFrame:
    """Current-season WAR for skaters (player_gar) and goalies (goalie_gar), one table."""
    sql = f"""
    select player_id, position, war, war_sd, games
    from `{bq.project()}.nhl_models.player_gar` where season_window = '{SEASON}'
    union all
    select goalie_id as player_id, 'G' as position, war, war_sd, games_played as games
    from `{bq.project()}.nhl_models.goalie_gar` where season_window = '{SEASON}'
    """
    df = bq.query_df(sql)
    for c in ["war", "war_sd", "games"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    return df


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


def fit_market_curves(market: pd.DataFrame) -> dict:
    """Per-position MONOTONE expected-CAP-SHARE(WAR) market curve — the ERA-NEUTRAL benchmark.

    The target is cap_share = actual_cap_hit / current-season cap, so the curve is independent of
    which season's dollars the cap is in. Same monotone, non-plateaued form as the recalibration:
    log(share) = a + b·WAR (b>0) so it rises multiplicatively and never plateaus; the intercept is
    shifted to the MARKET_QUANTILE conditional quantile (the going rate a well-paid player commands),
    then a smooth soft-cap asymptotes the top to the CBA max-contract share. Pools all skaters for a
    position group too sparse to fit on its own; the band is widened at the sparse top (in compute()).
    """
    market = market.copy()
    market["war"] = pd.to_numeric(market["war"]).astype("float64")
    market["cap_share"] = pd.to_numeric(market["cap_share"]).astype("float64")
    ceil = float(market["cap_share"].max()) * CV["MARKET_CEIL_MULT"]
    knee = ceil * CV["MARKET_KNEE_FRAC"]
    skater = market[market.pg.isin(["F", "D"])]
    fits: dict[str, tuple[float, float, float]] = {}
    top_war: dict[str, float] = {}
    for pg in ["F", "D", "G"]:
        g = market[market.pg == pg]
        if len(g) < CV["MARKET_MIN_N"] and pg in ("F", "D"):
            g = skater
        war = pd.to_numeric(g["war"]).to_numpy(dtype="float64")
        share = pd.to_numeric(g["cap_share"]).to_numpy(dtype="float64")
        b, a = np.polyfit(war, np.log(share), 1)               # log-linear OLS (b = log-share per WAR)
        b = max(b, 1e-6)                                       # guarantee monotone-increasing
        shift = float(np.quantile(np.log(share) - (a + b * war), CV["MARKET_QUANTILE"]))
        fits[pg] = (float(a), float(b), shift)
        top_war[pg] = float(np.quantile(market[market.pg == pg]["war"], 0.9)) if (market.pg == pg).any() else 99.0
    return {"fits": fits, "ceil": ceil, "knee": knee, "top_war": top_war}


def market_cap_share(market: dict, pg: str, war: float) -> float:
    """Expected CAP SHARE for a production level: log-linear, then a smooth soft-cap to the CBA-max
    share. The soft-cap keeps a positive slope everywhere (asymptotes, never a hard plateau)."""
    a, b, shift = market["fits"][pg]
    raw = float(np.exp(a + b * war + shift))
    ceil, knee = market["ceil"], market["knee"]
    if raw < knee:
        return raw
    return knee + (ceil - knee) * (1.0 - np.exp(-(raw - knee) / (ceil - knee)))


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
                      "surplus_share": round(exp_share - act_share, 4)})
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
    war = pull_war().sort_values("games", ascending=False).drop_duplicates("player_id")
    bio = pull_bio_age(0)
    arch = pull_archetypes()
    curves = pull_curves()

    df = (contracts
          .merge(war, on="player_id", how="left")
          .merge(bio, on="player_id", how="left")
          .merge(arch, on="player_id", how="left"))

    # base age at the snapshot season start (Oct 1 of season_start_year)
    def base_age(row) -> int | None:
        if pd.isna(row["birth_date"]):
            return None
        anchor = date(int(row["season_start_year"]), 10, 1)
        return int((pd.Timestamp(anchor) - row["birth_date"]).days // 365.25)
    df["age"] = df.apply(base_age, axis=1)
    df["pg"] = df.apply(lambda r: pos_group(r.get("position"), r.get("contract_pos")), axis=1)

    cap_ceilings = build_cap_ceilings()
    flat_ceilings = {y: CAP_CURRENT for y in cap_ceilings}   # cap frozen at current — before/after baseline

    # market curve fit on GROUNDED matched players, in CAP SHARE = actual cap hit / current-season cap
    market_src = df[df["war"].notna() & df["aav"].notna()][["pg", "war", "aav", "cap_hit"]].copy()
    market_src["cap_share"] = pd.to_numeric(market_src["cap_hit"]) / CAP_CURRENT
    market = fit_market_curves(market_src)

    rows = []
    for _, r in df.iterrows():
        pg = r["pg"]
        cap_hit = float(r["cap_hit"]) if pd.notna(r["cap_hit"]) else 0.0
        remaining = int(r["remaining_years"])
        age = int(r["age"]) if pd.notna(r["age"]) else 27   # league-ish default if bio missing
        curve = curves.get(r.get("primary_archetype")) or curves.get(CV["AGE_FALLBACK"].get(pg))

        grounded = pd.notna(r["war"])
        games = float(r["games"]) if pd.notna(r["games"]) else 0.0
        if grounded:
            war = float(r["war"])
            sd = float(r["war_sd"]) if pd.notna(r["war_sd"]) else CV["PROXY_WAR_BAND"]
            band = CV["BAND_SDS"] * sd
            high_conf = games >= CV["GROUNDED_MIN_GAMES"]
            confidence = "high" if (high_conf and pg != "G") else "medium"
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
            "war_now": round(war, 3), "war_sd": round(band, 3), "games_now": games,
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
    # (1) the market curve is monotone & rising at the top in CAP-SHARE space (no plateau)
    grid = np.arange(-1.0, 6.01, 0.25)
    for pg in ["F", "D", "G"]:
        curve = np.array([market_cap_share(market, pg, w) for w in grid])
        assert np.all(np.diff(curve) >= -1e-9), f"{pg} cap-share curve not monotone"
        assert curve[-1] > curve[len(grid) // 2] * 1.05, f"{pg} cap-share curve plateaus (top <= mid)"

    # (2) top-decile production prices within a realistic band of OBSERVED elite AAVs (share x cap)
    print("\n=== Cap-share market curve (top decile tracks elite AAVs, not a plateau) ===")
    for pg in ["F", "D"]:
        g = market_src[market_src.pg == pg]
        thr = float(np.quantile(g["war"], 0.9))
        obs_elite = float(g[g["war"] >= thr]["aav"].mean())
        pred = market_cap_share(market, pg, thr) * CAP_CURRENT
        ratio = pred / obs_elite
        print(f"  {pg}: war>={thr:.1f}  predicted ${pred/1e6:4.1f}M  vs observed-elite mean "
              f"${obs_elite/1e6:4.1f}M  (x{ratio:.2f})")
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
