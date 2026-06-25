"""
Futures value — prospects and draft picks valued in the SAME currency as player contracts (Trade
tool P6), so a future trade engine can net a prospect or a pick against a rostered player cleanly.

These are explicit PROXIES, always carried with a wide band and a `proxy` confidence tag, never a
bare precise number. The spine is a SLOT CURVE: expected career WAR-above-replacement as a function
of overall draft pick. As of Handoff 5 (Phase C) this is the EMPIRICAL curve fit on our own draft
outcomes (nhl_models.pick_value_curve, career-extrapolated from its 7-year window), not the old
hand-set power-law — which remains as a fallback if the curve table is unavailable. Either way:
round-1 picks dominate, value decays, late picks regress to replacement, busts already priced into
the expectation. From there:

  prospect value = slot(draft_overall)  [undrafted -> floored near replacement]
                   x development decay if lingering past NHL-ready age without an NHL footprint
                   x time-value discount over the years until they are NHL-ready
  pick value     = slot(round midpoint)  x time-value discount over (years_out + draft-to-NHL)

Value is expressed in BOTH WAR and dollars (config.FUTURES['DOLLARS_PER_WAR'], a proxy market price
of a win). Cost is ~0 — the appeal of futures is that they are cheap — so surplus ≈ value. Pick
rows carry the own-picks ownership note so the UI never presents the assumption as fact.

Output nhl_models.futures_value, one row per prospect and per pick, with the common asset interface
(asset_kind, asset_id, label, org, value+band, cost, surplus, confidence).

Run:  python -m models_ml.compute_futures_value [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

F = config.FUTURES

# Empirical pick-value curve (Handoff 5, Phase C): replaces the hand-set power-law. Loaded once from
# nhl_models.pick_value_curve as {overall_pick: career-extrapolated WAR}. The curve is published as a
# WINDOWED (7yr) quantity; the trade engine values picks in whole-career WAR, so we apply the curve's
# stored career-extrapolation factor (decision 2.5). Falls back to the documented power-law if the
# table is unavailable (e.g. before fit_pick_value has run), so this job never hard-depends on it.
_CURVE: dict | None = None
_CURVE_LOADED = False


def _load_curve() -> dict | None:
    global _CURVE, _CURVE_LOADED
    if _CURVE_LOADED:
        return _CURVE
    _CURVE_LOADED = True
    try:
        df = bq.query_df(f"""
            select overall_pick, ev_mean_smooth, career_extrap_factor
            from `{bq.project()}.nhl_models.pick_value_curve`
            order by overall_pick
        """)
        if df.empty:
            return None
        factor = float(df["career_extrap_factor"].iloc[0] or 1.0)
        _CURVE = {int(r.overall_pick): float(r.ev_mean_smooth) * factor for _, r in df.iterrows()}
        print(f"  pick-value curve: {len(_CURVE)} slots, career-extrap x{factor:.2f} (empirical, Handoff 5)")
    except Exception as e:  # noqa: BLE001
        print(f"  pick-value curve unavailable ({str(e)[:60]}); using power-law fallback")
        _CURVE = None
    return _CURVE


def _power_law(overall: float) -> float:
    v = F["SLOT_A"] / (overall + F["SLOT_C"]) ** F["SLOT_B"]
    return float(max(v, F["SLOT_FLOOR_WAR"]))


def slot_war(overall: float) -> float:
    """Expected whole-career WAR above replacement at a given overall pick.

    Empirical (career-extrapolated nhl_models.pick_value_curve) when available, else the documented
    power-law proxy. Clamped to the curve's domain; floored at the replacement floor."""
    if overall is None or not np.isfinite(overall) or overall <= 0:
        return F["UNDRAFTED_WAR"]
    curve = _load_curve()
    if curve:
        ov = int(round(overall))
        if ov not in curve:                      # clamp to the curve's domain (1..max sampled)
            keys = curve.keys()
            ov = min(max(ov, min(keys)), max(keys))
        return float(max(curve[ov], F["SLOT_FLOOR_WAR"]))
    return _power_law(overall)


def _band(value: float) -> tuple[float, float]:
    """Wide multiplicative band — every futures point estimate is a proxy."""
    return value * F["BAND_LO"], value * F["BAND_HI"]


def _row(asset_kind, asset_id, player_id, label, org, pos_or_slot, value_war, note):
    lo_w, hi_w = _band(value_war)
    d = F["DOLLARS_PER_WAR"]
    return {
        "asset_kind": asset_kind,
        "asset_id": asset_id,
        "player_id": player_id,
        "label": label,
        "org_team": org,
        "pos_or_slot": pos_or_slot,
        "value_war": round(value_war, 2),
        "value_war_low": round(lo_w, 2),
        "value_war_high": round(hi_w, 2),
        "value_dollars": round(value_war * d),
        "value_dollars_low": round(lo_w * d),
        "value_dollars_high": round(hi_w * d),
        "cost_dollars": 0,                       # futures are cheap; ELC cost is negligible vs the band
        "surplus_dollars": round(value_war * d),  # cost ≈ 0 -> surplus ≈ value
        "confidence": "proxy",
        "ownership_note": note,
        "model_version": F["MODEL_VERSION"],
    }


# ------------------------------------------------------------------------------------- prospects
def compute_prospects() -> pd.DataFrame:
    p = bq.query_df(f"""
        select player_id, full_name, pos_group, age, org_team, draft_overall, is_undrafted
        from `{bq.project()}.nhl_staging.stg_prospects`
    """)
    p["age"] = pd.to_numeric(p["age"], errors="coerce")
    rows = []
    for _, r in p.iterrows():
        overall = float(r["draft_overall"]) if pd.notna(r["draft_overall"]) else None
        base = F["UNDRAFTED_WAR"] if (overall is None) else slot_war(overall)
        age = float(r["age"]) if pd.notna(r["age"]) else 20.0

        # development decay: a prospect lingering past NHL-ready age without breaking through is
        # more bust-like the older they get (the slot curve's expectation assumed an on-time arrival)
        if age > F["NHL_READY_AGE"]:
            base *= F["DEV_DECAY_PER_YEAR"] ** (age - F["NHL_READY_AGE"])
        # time value: discount over the seasons until they are expected to be NHL-ready
        ttn = max(0.0, F["NHL_READY_AGE"] - age)
        value_war = base * (F["DISCOUNT"] ** ttn)

        slot_lbl = "undrafted" if overall is None else f"#{int(overall)} overall"
        rows.append(_row("prospect", f"prospect:{int(r['player_id'])}", int(r["player_id"]),
                         r["full_name"], r["org_team"], f"{r['pos_group']} · {slot_lbl}",
                         value_war, None))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------- draft picks
def compute_picks() -> pd.DataFrame:
    q = bq.query_df(f"""
        select draft_year, round, owner_team, original_team, years_out, ownership_source, note
        from `{bq.project()}.nhl_staging.stg_draft_picks`
    """)
    ppr = F["PICKS_PER_ROUND"]
    rows = []
    for _, r in q.iterrows():
        rnd = int(r["round"])
        rep_overall = (rnd - 1) * ppr + ppr // 2          # round midpoint slot (within-round spread -> band)
        years_out = float(r["years_out"]) if pd.notna(r["years_out"]) else 1.0
        # a pick becomes an NHL contributor ~DRAFT_TO_NHL_YEARS after the draft, plus years until the draft
        ttn = max(0.0, years_out) + F["DRAFT_TO_NHL_YEARS"]
        value_war = slot_war(rep_overall) * (F["DISCOUNT"] ** ttn)

        own = r["ownership_source"]
        note = ("Assumed own pick — pick trades are not in any feed; verify before relying."
                if own == "assumed_own" else f"Ownership override: {r['note']}")
        if own == "assumed_own" and str(r["owner_team"]) != str(r["original_team"]):
            note = f"Override -> {r['owner_team']}"
        label = f"{int(r['draft_year'])} R{rnd} ({r['owner_team']})"
        rows.append(_row("pick", f"pick:{r['owner_team']}:{int(r['draft_year'])}:R{rnd}", None,
                         label, r["owner_team"], f"Round {rnd} · ~#{rep_overall}", value_war, note))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------- main
def _report(df: pd.DataFrame) -> None:
    pr = df[df.asset_kind == "prospect"]
    pk = df[df.asset_kind == "pick"]
    print(f"\nfutures_value: {len(df)} assets ({len(pr)} prospects, {len(pk)} picks); all proxy-tagged")
    print("\n=== Top prospects by value (career WAR, wide band) ===")
    for _, r in pr.sort_values("value_war", ascending=False).head(10).iterrows():
        print(f"  {r.label:24s} {r.pos_or_slot:18s} "
              f"{r.value_war:4.1f} WAR  (${r.value_dollars/1e6:.1f}M, band {r.value_war_low:.1f}-{r.value_war_high:.1f})")
    print("\n=== Pick value by round (first future draft) ===")
    yr = int(df.label.str.extract(r"(\d{4})")[0].dropna().astype(int).min())
    one = pk[pk.label.str.startswith(str(yr))].drop_duplicates("pos_or_slot").sort_values("pos_or_slot")
    for _, r in one.iterrows():
        print(f"  {yr} {r.pos_or_slot:18s} {r.value_war:4.2f} WAR  (${r.value_dollars/1e6:.2f}M)")
    print("\n  Pick ownership: all assumed-own unless overridden (see draft_pick_overrides.csv) — flagged per row.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df = pd.concat([compute_prospects(), compute_picks()], ignore_index=True)
    _report(df)

    if args.dry_run:
        print("\n[dry-run] not written")
        return
    bq.write_df(df, "futures_value", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["asset_kind", "org_team"])
    print(f"\nWrote {len(df)} rows to nhl_models.futures_value.")


if __name__ == "__main__":
    main()
