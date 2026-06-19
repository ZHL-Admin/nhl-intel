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
from datetime import date

import numpy as np
import pandas as pd

from models_ml import bq, config

CV = config.CONTRACT_VALUE
SEASON = "2025-26"


# --------------------------------------------------------------------------------------------- pulls
def pull_contracts() -> pd.DataFrame:
    """Latest-snapshot player contracts (one row per player) with the cap schedule."""
    sql = f"""
    select player_id, season, as_of_date, season_start_year, contract_pos,
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
    """Per-position MONOTONE AAV(WAR) market curve.

    log(AAV) = a + b·WAR (b>0) so the curve rises multiplicatively and never plateaus; the intercept
    is shifted to the MARKET_QUANTILE conditional quantile (the going rate a well-paid player at that
    production commands), then a smooth soft-cap asymptotes the top to the CBA max-contract ceiling.
    Pools all skaters for a position group that is too sparse to fit on its own.
    """
    market = market.copy()
    market["war"] = pd.to_numeric(market["war"]).astype("float64")
    market["aav"] = pd.to_numeric(market["aav"]).astype("float64")
    ceil = float(market["aav"].max()) * CV["MARKET_CEIL_MULT"]
    knee = ceil * CV["MARKET_KNEE_FRAC"]
    skater = market[market.pg.isin(["F", "D"])]
    fits: dict[str, tuple[float, float, float]] = {}
    top_war: dict[str, float] = {}
    for pg in ["F", "D", "G"]:
        g = market[market.pg == pg]
        if len(g) < CV["MARKET_MIN_N"] and pg in ("F", "D"):
            g = skater
        war = pd.to_numeric(g["war"]).to_numpy(dtype="float64")
        aav = pd.to_numeric(g["aav"]).to_numpy(dtype="float64")
        b, a = np.polyfit(war, np.log(aav), 1)                 # log-linear OLS (b = log-$ per WAR)
        b = max(b, 1e-6)                                       # guarantee monotone-increasing
        shift = float(np.quantile(np.log(aav) - (a + b * war), CV["MARKET_QUANTILE"]))
        fits[pg] = (float(a), float(b), shift)
        top_war[pg] = float(np.quantile(market[market.pg == pg]["war"], 0.9)) if (market.pg == pg).any() else 99.0
    return {"fits": fits, "ceil": ceil, "knee": knee, "top_war": top_war}


def market_aav(market: dict, pg: str, war: float) -> float:
    """Expected market AAV for a production level: log-linear, then a smooth soft-cap to the CBA max.
    The soft-cap keeps a positive slope everywhere (asymptotes to the ceiling, never a hard plateau)."""
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
                curve: dict[int, float] | None, cap_hit: float,
                market: dict, discount: float) -> dict:
    """Project WAR -> market AAV -> surplus over remaining years, discounted. Returns aggregates."""
    goalie_flat = pg == "G" and CV["GOALIE_AGING_FLAT"]
    war_path, aav_path, surplus_path, disc = [], [], [], []
    for k in range(remaining):
        age_k = base_age + k
        r = 1.0 if goalie_flat else aging_ratio(curve, base_age, age_k)
        wk = war * r
        ek = market_aav(market, pg, wk)
        war_path.append(wk)
        aav_path.append(ek)
        surplus_path.append(ek - cap_hit)
        disc.append(discount ** k)
    disc = np.array(disc)
    return {
        "value_war": float(np.dot(war_path, disc)),
        "value_dollars": float(np.dot(aav_path, disc)),
        "cost_dollars": float(cap_hit * disc.sum()),
        "expected_aav_now": float(aav_path[0]),
        "surplus_current": float(surplus_path[0]),
        "total_surplus": float(np.sum(surplus_path)),
        "total_discounted_surplus": float(np.dot(surplus_path, disc)),
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

    # market curve fit on GROUNDED matched players (have both current WAR and an AAV)
    market_src = df[df["war"].notna() & df["aav"].notna()][["pg", "war", "aav"]].copy()
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

        mid = project_one(war, age, remaining, pg, curve, cap_hit, market, CV["DISCOUNT"])
        lo = project_one(war - band, age, remaining, pg, curve, cap_hit, market, CV["DISCOUNT"])
        hi = project_one(war + band, age, remaining, pg, curve, cap_hit, market, CV["DISCOUNT"])

        rows.append({
            "player_id": int(r["player_id"]),
            "season": r["season"], "as_of_date": r["as_of_date"],
            "pos_group": pg, "age": age, "primary_archetype": r.get("primary_archetype"),
            "cap_hit": int(cap_hit), "aav": int(r["aav"]) if pd.notna(r["aav"]) else None,
            "remaining_years": remaining,
            "war_now": round(war, 3), "war_sd": round(band, 3), "games_now": games,
            "expected_aav_now": round(mid["expected_aav_now"]),
            "surplus_current": round(mid["surplus_current"]),
            "value_war": round(mid["value_war"], 2),
            "value_war_low": round(lo["value_war"], 2), "value_war_high": round(hi["value_war"], 2),
            "value_dollars": round(mid["value_dollars"]),
            "cost_dollars": round(mid["cost_dollars"]),
            "total_surplus": round(mid["total_surplus"]),
            "total_discounted_surplus": round(mid["total_discounted_surplus"]),
            "surplus_low": round(lo["total_discounted_surplus"]),
            "surplus_high": round(hi["total_discounted_surplus"]),
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


def _acceptance(df: pd.DataFrame, market: dict, market_src: pd.DataFrame) -> None:
    """Assert + print the recalibration acceptance checks (monotone, non-plateaued top that tracks
    elite AAVs, and the three sample stars reading as roughly fairly paid)."""
    # (1) monotone & rising at the top — no plateau — per position group
    grid = np.arange(-1.0, 6.01, 0.25)
    for pg in ["F", "D", "G"]:
        curve = np.array([market_aav(market, pg, w) for w in grid])
        assert np.all(np.diff(curve) >= -1.0), f"{pg} market curve not monotone"
        assert curve[-1] > curve[len(grid) // 2] * 1.05, f"{pg} market curve plateaus (top <= mid)"

    # (2) top-decile production prices within a realistic band of OBSERVED elite AAVs (not below)
    print("\n=== Market curve recalibration (top decile tracks elite AAVs, not a plateau) ===")
    for pg in ["F", "D"]:
        g = market_src[market_src.pg == pg]
        thr = float(np.quantile(g["war"], 0.9))
        obs_elite = float(g[g["war"] >= thr]["aav"].mean())
        pred_at_thr = market_aav(market, pg, thr)
        ratio = pred_at_thr / obs_elite
        print(f"  {pg}: war>={thr:.1f}  predicted ${pred_at_thr/1e6:4.1f}M  vs observed-elite mean "
              f"${obs_elite/1e6:4.1f}M  (x{ratio:.2f})")
        assert 0.75 <= ratio <= 1.6, f"{pg} top-decile price ${pred_at_thr/1e6:.1f}M off elite ${obs_elite/1e6:.1f}M"

    # (3) the three sample stars read near-zero to modest surplus (not multi-million negative)
    stars = {8478864: "Kaprizov", 8477934: "Draisaitl", 8478403: "Eichel"}
    print("\n=== Star sanity (per-year surplus = expected market AAV - cap hit) ===")
    print(f"  {'player':12s} {'WAR':>5s} {'cap$M':>6s} {'exp.AAV$M':>9s} {'surplus/yr$M':>12s} {'conf':>7s}")
    for pid, nm in stars.items():
        row = df[df.player_id == pid]
        if row.empty:
            print(f"  {nm:12s}  (not in contract set)")
            continue
        r = row.iloc[0]
        print(f"  {nm:12s} {r.war_now:5.1f} {r.cap_hit/1e6:6.1f} {r.expected_aav_now/1e6:9.1f} "
              f"{r.surplus_current/1e6:+12.1f} {r.confidence:>7s}")
        assert r.surplus_current / 1e6 >= -4.0, f"{nm} reads {r.surplus_current/1e6:.1f}M/yr (too negative)"

    # mid + low reference players so the WHOLE range stays sane
    ref = df[df.is_grounded].copy()
    ref["d1"] = (ref.war_now - 1.0).abs(); ref["d0"] = (ref.war_now + 0.3).abs()
    mid = ref.nsmallest(1, "d1").iloc[0]; low = ref.nsmallest(1, "d0").iloc[0]
    print("  --- reference mid / low tier ---")
    for tag, r in [("mid", mid), ("low", low)]:
        print(f"  {tag:12s} {r.war_now:5.1f} {r.cap_hit/1e6:6.1f} {r.expected_aav_now/1e6:9.1f} "
              f"{r.surplus_current/1e6:+12.1f} {r.confidence:>7s}")


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
