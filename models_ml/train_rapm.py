"""
Isolated impact: RAPM on the in-house xG layer (Phase 4.1, blueprint 4.2).

Regularized adjusted plus-minus. Unit of observation = a 5v5 stint (int_shift_segments x
int_segment_context). Each stint becomes TWO rows, one per attacking direction:

  target = the attacking team's xGF per 60 during the stint (xG from nhl_models.shot_xg via
           int_on_ice_events), weighted by stint duration.
  design = a two-sided indicator set: +1 in each of the 5 attacking skaters' OFFENCE columns
           and +1 in each of the 5 defending skaters' DEFENCE columns, plus controls
           (attacker score state, zone start, home, back-to-back, season fixed effects).

Ridge regression recovers, for every skater, an offence coefficient (raises own team's xGF/60)
and a defence coefficient (raises the opponent's xGF/60 while defending). We report
off_impact = centred offence coef and def_impact = -(centred defence coef) so that higher is
better for both. Lambda is chosen by game-grouped out-of-sample xG prediction. Uncertainty is
a game-resample bootstrap (reusing the design, reweighting by each game's draw count).

Outputs nhl_models.player_impact (player_id, season_window, off/def/pp/pk impact + sd + TOI).
Special teams (PP offence on 5v4, PK defence on 4v5) use the same machinery, unit indicators
only, with wider uncertainty.

Run:
  python -m models_ml.train_rapm --season 2024-25 --no-bootstrap   # quick single-season test
  python -m models_ml.train_rapm                                    # full: 3yr window + singles
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge

from models_ml import bq, config

MODEL_VERSION = "rapm_v1"
METHODOLOGY = Path(__file__).parent.parent / "docs" / "methodology" / "isolated-impact.md"

MIN_SEGMENT_SECONDS = 4
ALPHAS = [250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0]
DEFAULT_BOOTSTRAP = 100
SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
WINDOW_WEIGHTS = [0.3, 0.6, 1.0]   # oldest -> newest for the 3-season rolling window
SCORE_STATES = ["leading", "tied", "trailing"]
ZONE_CATS = ["O", "D", "N"]        # faceoff start zone; on-the-fly = reference

# Per-5v5-stint pull: on-ice skaters per side, xGF per side, and controls. Aggregated within
# (game, segment) already by the join; one row per segment.
PULL_SQL = """
with seg as (
  select sc.game_id, sc.segment_index, sc.season, sc.segment_duration,
         sc.home_team_id, sc.away_team_id, sc.home_score_state, sc.zone_start_code
  from `{p}.nhl_staging.int_segment_context` sc
  where sc.strength_state in ({strengths}) and sc.segment_duration >= {minsec}
    and sc.season in ({seasons})
),
sk as (
  select s.game_id, s.segment_index,
    array_agg(if(s.team_id = seg.home_team_id, s.player_id, null) ignore nulls) as home_sk,
    array_agg(if(s.team_id = seg.away_team_id, s.player_id, null) ignore nulls) as away_sk
  from `{p}.nhl_staging.int_shift_segments` s
  join seg on s.game_id = seg.game_id and s.segment_index = seg.segment_index
  where s.is_goalie = 0
  group by 1, 2
),
xg as (
  select e.game_id, e.segment_index,
    sum(if(e.event_owner_team_id = seg.home_team_id, s.xg, 0)) as home_xg,
    sum(if(e.event_owner_team_id = seg.away_team_id, s.xg, 0)) as away_xg
  from `{p}.nhl_staging.int_on_ice_events` e
  join seg on e.game_id = seg.game_id and e.segment_index = seg.segment_index
  join `{p}.nhl_models.shot_xg` s on e.game_id = s.game_id and e.event_id = s.event_id
  where s.xg is not null
  group by 1, 2
)
select seg.game_id, seg.season, seg.segment_duration as dur,
       seg.home_team_id, seg.away_team_id, seg.home_score_state, seg.zone_start_code,
       sk.home_sk, sk.away_sk,
       coalesce(xg.home_xg, 0) as home_xg, coalesce(xg.away_xg, 0) as away_xg
from seg
join sk on seg.game_id = sk.game_id and seg.segment_index = sk.segment_index
left join xg on seg.game_id = xg.game_id and seg.segment_index = xg.segment_index
"""


def pull(seasons: list[str], strengths: list[str]) -> pd.DataFrame:
    sql = PULL_SQL.format(p=bq.project(), minsec=MIN_SEGMENT_SECONDS,
                          strengths=", ".join(f"'{s}'" for s in strengths),
                          seasons=", ".join(f"'{s}'" for s in seasons))
    df = bq.query_df(sql)
    df["dur"] = pd.to_numeric(df["dur"]).astype("float64")
    df["home_xg"] = pd.to_numeric(df["home_xg"]).astype("float64")
    df["away_xg"] = pd.to_numeric(df["away_xg"]).astype("float64")
    return df


def back_to_back(seasons: list[str]) -> dict:
    """Map (game_id, team_id) -> 1 if the team played the previous calendar day."""
    games = bq.query_df(f"""
        select game_id, game_date, home_team_id, away_team_id
        from `{bq.project()}.nhl_staging.stg_games`
        where season in ({", ".join(f"'{s}'" for s in seasons)})
          and substr(cast(game_id as string), 5, 2) in ('02', '03')
    """)
    games["game_date"] = pd.to_datetime(games["game_date"])
    long = pd.concat([
        games[["game_id", "game_date", "home_team_id"]].rename(columns={"home_team_id": "team_id"}),
        games[["game_id", "game_date", "away_team_id"]].rename(columns={"away_team_id": "team_id"}),
    ])
    long = long.sort_values(["team_id", "game_date"])
    long["prev"] = long.groupby("team_id")["game_date"].shift(1)
    long["b2b"] = ((long["game_date"] - long["prev"]).dt.days == 1).astype("float64")
    return {(int(r.game_id), int(r.team_id)): r.b2b for r in long.itertuples()}


def expand_rows(df: pd.DataFrame, b2b: dict, season_weights: dict | None):
    """Turn each stint into two attacking-direction rows. Returns a frame with the player
    sets, target, weight, controls, and game_id (for bootstrap)."""
    rows = []
    flip = {"leading": "trailing", "trailing": "leading", "tied": "tied"}
    for r in df.itertuples():
        home_sk, away_sk = list(r.home_sk), list(r.away_sk)
        if len(home_sk) != 5 or len(away_sk) != 5:
            continue  # data noise (too many/few skaters) — documented exclusion
        sw = 1.0 if season_weights is None else season_weights.get(r.season, 1.0)
        w = r.dur * sw
        zone = r.zone_start_code if r.zone_start_code in ZONE_CATS else None
        # home attacking
        rows.append((r.game_id, home_sk, away_sk, r.home_xg / r.dur * 3600.0, w,
                     r.home_score_state, zone, 1.0,
                     b2b.get((int(r.game_id), int(r.home_team_id)), 0.0), r.season))
        # away attacking (flip score state to the away attacker's perspective)
        rows.append((r.game_id, away_sk, home_sk, r.away_xg / r.dur * 3600.0, w,
                     flip[r.home_score_state], zone, 0.0,
                     b2b.get((int(r.game_id), int(r.away_team_id)), 0.0), r.season))
    return rows


def expand_special(df: pd.DataFrame, b2b: dict, season_weights: dict | None):
    """One row per power-play segment: the man-up team attacks. offence = the PP unit,
    defence = the PK unit, target = PP-team xGF/60. A two-sided fit then yields PP-offence
    (off coef) and PK-defence (def coef) impacts from one model."""
    rows = []
    flip = {"leading": "trailing", "trailing": "leading", "tied": "tied"}
    for r in df.itertuples():
        home_sk, away_sk = list(r.home_sk), list(r.away_sk)
        # PP team = the side with more skaters (5 on 5v4 / 4v5); need a clean 5-on-4
        if {len(home_sk), len(away_sk)} != {4, 5}:
            continue
        home_pp = len(home_sk) > len(away_sk)
        pp_sk, pk_sk = (home_sk, away_sk) if home_pp else (away_sk, home_sk)
        pp_xg = r.home_xg if home_pp else r.away_xg
        sw = 1.0 if season_weights is None else season_weights.get(r.season, 1.0)
        w = r.dur * sw
        zone = r.zone_start_code if r.zone_start_code in ZONE_CATS else None
        ss = r.home_score_state if home_pp else flip[r.home_score_state]
        pp_team = r.home_team_id if home_pp else r.away_team_id
        rows.append((r.game_id, pp_sk, pk_sk, pp_xg / r.dur * 3600.0, w, ss, zone,
                     1.0 if home_pp else 0.0,
                     b2b.get((int(r.game_id), int(pp_team)), 0.0), r.season))
    return rows


def build_design(rows, two_sided: bool = True):
    """Build the sparse design X, target y, weights w, game ids, and the player index.
    two_sided gives every player an offence AND a defence column (5v5; and PP-off/PK-def for
    special teams)."""
    players = sorted({p for row in rows for p in row[1] + row[2]})
    pidx = {p: i for i, p in enumerate(players)}
    n_players = len(players)
    seasons = sorted({row[9] for row in rows})
    sidx = {s: i for i, s in enumerate(seasons)}

    # column layout: [off players | def players (two_sided) | controls]
    off_base = 0
    def_base = n_players
    ctrl_base = 2 * n_players if two_sided else n_players
    # controls: score_state(2 dummies vs tied) + zone(O,D,N) + home + b2b + season dummies(-1)
    n_ctrl = 2 + 3 + 1 + 1 + max(len(seasons) - 1, 0)

    n_rows = len(rows)
    y = np.empty(n_rows)
    w = np.empty(n_rows)
    games = np.empty(n_rows, dtype=np.int64)
    ri, ci, dv = [], [], []
    for i, row in enumerate(rows):
        gid, off, deff, target, weight, ss, zone, home, b2b, season = row
        y[i] = target
        w[i] = weight
        games[i] = gid
        for p in off:
            ri.append(i); ci.append(off_base + pidx[p]); dv.append(1.0)
        for p in deff:
            ri.append(i); ci.append((def_base if two_sided else off_base) + pidx[p]); dv.append(1.0)
        c = ctrl_base
        if ss == "leading":
            ri.append(i); ci.append(c); dv.append(1.0)
        elif ss == "trailing":
            ri.append(i); ci.append(c + 1); dv.append(1.0)
        c += 2
        if zone in ZONE_CATS:
            ri.append(i); ci.append(c + ZONE_CATS.index(zone)); dv.append(1.0)
        c += 3
        if home:
            ri.append(i); ci.append(c); dv.append(1.0)
        c += 1
        if b2b:
            ri.append(i); ci.append(c); dv.append(1.0)
        c += 1
        s_i = sidx[season]
        if s_i < len(seasons) - 1:  # last season is reference
            ri.append(i); ci.append(c + s_i); dv.append(1.0)
    n_cols = ctrl_base + n_ctrl
    X = sparse.csr_matrix((dv, (ri, ci)), shape=(n_rows, n_cols))
    return X, y, w, games, players, n_players, two_sided


def cv_alpha(X, y, w, games):
    """Pick alpha by game-grouped 80/20 holdout weighted MSE."""
    rng = np.random.default_rng(0)
    uniq = np.unique(games)
    val_games = set(rng.choice(uniq, size=max(1, len(uniq) // 5), replace=False).tolist())
    val = np.array([g in val_games for g in games])
    best, best_mse = ALPHAS[0], np.inf
    for a in ALPHAS:
        m = Ridge(alpha=a, solver="lsqr", fit_intercept=True, max_iter=2000)
        m.fit(X[~val], y[~val], sample_weight=w[~val])
        pred = m.predict(X[val])
        mse = float(np.average((pred - y[val]) ** 2, weights=w[val]))
        if mse < best_mse:
            best, best_mse = a, mse
    return best, best_mse


def fit_coefs(X, y, w, alpha):
    m = Ridge(alpha=alpha, solver="lsqr", fit_intercept=True, max_iter=3000)
    m.fit(X, y, sample_weight=w)
    return m.coef_


def player_impacts(coef, players, n_players, two_sided):
    off = coef[:n_players]
    off_c = off - off.mean()
    if two_sided:
        deff = coef[n_players:2 * n_players]
        def_c = deff - deff.mean()
        def_impact = -def_c  # higher = suppresses opponent xGF = better defence
    else:
        def_impact = np.full(n_players, np.nan)
    return pd.DataFrame({"player_id": players, "off_impact": off_c, "def_impact": def_impact})


def bootstrap_sd(X, y, w, games, alpha, players, n_players, two_sided, B):
    uniq = np.unique(games)
    game_to_rows = pd.Series(range(len(games))).groupby(games).apply(list)
    offs, defs = [], []
    rng = np.random.default_rng(7)
    for b in range(B):
        draw = rng.multinomial(len(uniq), np.full(len(uniq), 1 / len(uniq)))
        mult = dict(zip(uniq, draw))
        wb = w * np.array([mult[g] for g in games], dtype="float64")
        coef = fit_coefs(X, y, wb, alpha)
        offs.append(coef[:n_players] - coef[:n_players].mean())
        if two_sided:
            d = coef[n_players:2 * n_players]
            defs.append(-(d - d.mean()))
        if (b + 1) % 25 == 0:
            print(f"    bootstrap {b + 1}/{B}")
    off_sd = np.std(np.array(offs), axis=0)
    def_sd = np.std(np.array(defs), axis=0) if two_sided else np.full(n_players, np.nan)
    return off_sd, def_sd


def toi_minutes(seasons, strength_filter=None):
    """Per-player 5v5 TOI minutes over the seasons (denominator)."""
    extra = ""
    df = bq.query_df(f"""
        select s.player_id, sum(s.segment_duration) / 60.0 as toi_min
        from `{bq.project()}.nhl_staging.int_shift_segments` s
        join `{bq.project()}.nhl_staging.int_segment_context` c
          on s.game_id = c.game_id and s.segment_index = c.segment_index
        where s.is_goalie = 0 and c.strength_state = '{strength_filter or '5v5'}'
          and s.season in ({", ".join(f"'{x}'" for x in seasons)})
        group by 1
    """)
    return dict(zip(df["player_id"], df["toi_min"]))


def fit_ev(seasons, window_label, season_weights, b2b, bootstrap):
    """Even-strength (5v5) two-sided RAPM -> off_impact / def_impact (+ sd)."""
    print(f"[{window_label}] pulling 5v5 stints for {seasons} ...")
    df = pull(seasons, ["5v5"])
    rows = expand_rows(df, b2b, season_weights)
    print(f"[{window_label}] {len(df):,} stints -> {len(rows):,} direction-rows")
    X, y, w, games, players, n_players, two_sided = build_design(rows, two_sided=True)
    alpha, mse = cv_alpha(X, y, w, games)
    print(f"[{window_label}] chosen alpha={alpha} (val wMSE={mse:.4f}); fitting ...")
    coef = fit_coefs(X, y, w, alpha)
    out = player_impacts(coef, players, n_players, two_sided)
    if bootstrap:
        print(f"[{window_label}] EV bootstrap x{bootstrap} ...")
        off_sd, def_sd = bootstrap_sd(X, y, w, games, alpha, players, n_players, two_sided, bootstrap)
        out["off_sd"], out["def_sd"] = off_sd, def_sd
    else:
        out["off_sd"], out["def_sd"] = np.nan, np.nan
    out["toi_min"] = out["player_id"].map(toi_minutes(seasons, "5v5"))
    out["season_window"] = window_label
    out["alpha"] = alpha
    return out


def fit_special(seasons, window_label, season_weights, b2b, bootstrap):
    """Power-play segments (5v4/4v5) -> pp_impact (PP offence) + pk_impact (PK defence)."""
    df = pull(seasons, ["5v4", "4v5"])
    rows = expand_special(df, b2b, season_weights)
    if not rows:
        return pd.DataFrame(columns=["player_id", "pp_impact", "pp_sd", "pk_impact", "pk_sd"])
    print(f"[{window_label}] special teams: {len(df):,} segs -> {len(rows):,} PP rows")
    X, y, w, games, players, n_players, _ = build_design(rows, two_sided=True)
    alpha, _ = cv_alpha(X, y, w, games)
    coef = fit_coefs(X, y, w, alpha)
    imp = player_impacts(coef, players, n_players, True)  # off=PP, def_impact=-(PK def coef)
    out = pd.DataFrame({"player_id": imp["player_id"],
                        "pp_impact": imp["off_impact"], "pk_impact": imp["def_impact"]})
    if bootstrap:
        print(f"[{window_label}] ST bootstrap x{bootstrap} ...")
        pp_sd, pk_sd = bootstrap_sd(X, y, w, games, alpha, players, n_players, True, bootstrap)
        out["pp_sd"], out["pk_sd"] = pp_sd, pk_sd
    else:
        out["pp_sd"], out["pk_sd"] = np.nan, np.nan
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None, help="fit one single season (quick test)")
    ap.add_argument("--no-bootstrap", action="store_true")
    ap.add_argument("--bootstrap", type=int, default=DEFAULT_BOOTSTRAP)
    ap.add_argument("--dry-run", action="store_true", help="don't write to BigQuery")
    args = ap.parse_args()
    B = 0 if args.no_bootstrap else args.bootstrap

    if args.season:
        b2b = back_to_back([args.season])
        out = fit_ev([args.season], args.season, None, b2b, B)
        report(out, args.season)
        if not args.dry_run:
            write([_with_special(out, [args.season], None, b2b, B)])
        return

    # full run: latest 3-season weighted window (headline, full bootstrap) + recent single
    # seasons (reduced bootstrap to keep the job tractable).
    single_B = min(B, 40)
    win = SINGLE_SEASONS[-3:]
    sw = dict(zip(win, WINDOW_WEIGHTS))
    win_label = f"{win[0]}_{win[-1]}"
    b2b_all = back_to_back(SINGLE_SEASONS)
    frames = []
    frames.append(_with_special(fit_ev(win, win_label, sw, b2b_all, B), win, sw, b2b_all, B))
    for s in SINGLE_SEASONS:
        frames.append(_with_special(fit_ev([s], s, None, b2b_all, single_B), [s], None, b2b_all, single_B))
    report(frames[0], win_label)
    if not args.dry_run:
        write(frames)


def _with_special(ev_out, seasons, season_weights, b2b, B):
    """Attach PP-offence and PK-defence impacts to the even-strength impact frame."""
    label = ev_out["season_window"].iloc[0]
    try:
        st = fit_special(seasons, label, season_weights, b2b, max(B // 2, 0) if B else 0)
    except Exception as e:
        print(f"  special-teams fit skipped for {label}: {e}")
        st = pd.DataFrame(columns=["player_id", "pp_impact", "pp_sd", "pk_impact", "pk_sd"])
    for col in ["pp_impact", "pp_sd", "pk_impact", "pk_sd"]:
        m = dict(zip(st["player_id"], st[col])) if col in st else {}
        ev_out[col] = ev_out["player_id"].map(m)
    return ev_out


def report(out: pd.DataFrame, label: str) -> None:
    print(f"\n=== RAPM {label} ===")
    print(f"off_impact mean={out['off_impact'].mean():.4f} sd={out['off_impact'].std():.3f}")
    qual = out[out["toi_min"] >= 200]
    names = _names(qual["player_id"].tolist())
    top_o = qual.sort_values("off_impact", ascending=False).head(10)
    top_d = qual.sort_values("def_impact", ascending=False).head(10)
    print("Top-10 offence:")
    for _, r in top_o.iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} {r['off_impact']:+.3f}")
    print("Top-10 defence:")
    for _, r in top_d.iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} {r['def_impact']:+.3f}")


def _names(ids):
    if not ids:
        return {}
    df = bq.query_df(f"""
        select player_id, any_value(first_name || ' ' || last_name) as name
        from `{bq.project()}.nhl_staging.stg_rosters`
        where player_id in ({", ".join(str(int(i)) for i in ids)}) group by 1
    """)
    return dict(zip(df["player_id"], df["name"]))


def write(frames: list[pd.DataFrame]) -> None:
    out = pd.concat(frames, ignore_index=True)
    cols = ["player_id", "season_window", "off_impact", "off_sd", "def_impact", "def_sd",
            "pp_impact", "pp_sd", "pk_impact", "pk_sd", "toi_min", "alpha"]
    out = out[[c for c in cols if c in out.columns]].copy()
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = MODEL_VERSION
    bq.write_df(out, "player_impact", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "player_id"])
    print(f"\nWrote {len(out):,} rows to nhl_models.player_impact.")


if __name__ == "__main__":
    main()
