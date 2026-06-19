"""
Team need profiles for the Player Fit tool — by ROLE x COMPONENT, vs the team's OWN current depth.

A team's need at a (role, component) is how WEAK its current depth is there relative to the league:

  team_strength[role][component] = sum over the team's current players at that role of their
      composite component value (goals-scale; the sum captures BOTH quality and depth — a team with
      several good centers sums high, a team with one good center and scrubs sums low).
  league_pctile = percent_rank of that strength across the 32 teams at the same (role, component).
  need          = 1 - league_pctile   (weak own depth -> high need), in [0, 1].

Roles: C / W (L+R wings) / D for skaters; G for goalies (single component 'goaltending', from the
composite goalie GSAx). This REPLACES the old top-8 archetype/component benchmark: need is now
own-depth, role-aware, and it ABSORBS POSITION entirely — a center is measured against the team's
center depth, a winger against its wing depth, so a player only scores need at his own role.

Output nhl_models.team_needs (long): one row per (team_id, season, role, component) with
team_strength, league_pctile, need, label, model_version. Consumed by models_ml.score_team_fit.

Run:  python -m models_ml.compute_team_needs [--season 2025-26] [--dry-run]
"""

from __future__ import annotations

import argparse

import pandas as pd

from models_ml import bq

SKATER_COMPONENTS = ["ev_offense", "ev_defense", "pp", "pk", "finishing"]
COMPONENT_LABEL = {
    "ev_offense": "Even-strength offense", "ev_defense": "Even-strength defense",
    "pp": "Power play", "pk": "Penalty kill", "finishing": "Finishing",
    "goaltending": "Goaltending",
}
ROLE_LABEL = {"C": "center", "W": "wing", "D": "defense", "G": "goaltending"}


def components_for_role(role: str) -> list[str]:
    """Skater components scored at a role. Finishing is a forward skill — excluded for defensemen
    (for D it's a tiny, shrunk shot sample whose percentile is noise)."""
    if role == "D":
        return [c for c in SKATER_COMPONENTS if c != "finishing"]
    return list(SKATER_COMPONENTS)


def role_of(position) -> str | None:
    """Map a position code to a depth-chart role. Wings (L/R) collapse to W; centers and D stay
    distinct (the center premium); goalies are G. Unknown/blank -> None (dropped, not guessed)."""
    if not isinstance(position, str):
        return None
    p = position.strip().upper()
    if p in ("C",):
        return "C"
    if p in ("L", "R", "LW", "RW"):
        return "W"
    if p in ("D",):
        return "D"
    if p in ("G",):
        return "G"
    return None


def _latest_season(p: str) -> str:
    return bq.query_df(f"select max(season) as s from `{p}.nhl_models.team_ratings`").iloc[0]["s"]


def pull_players(p: str, season: str) -> pd.DataFrame:
    """Every player's composite components + position + current NHL team that season.

    Current team uses the roster trick filtered to NHL game types ('01'/'02'/'03') so 2026 Olympic /
    4-Nations games (national team_ids) never pick a player's 'current team'."""
    df = bq.query_df(f"""
        with comp as (
            select player_id, position, toi_5v5, goalie_gsax, {', '.join(SKATER_COMPONENTS)}
            from `{p}.nhl_models.player_composite` where season_window = '{season}'
        ),
        team as (
            select player_id,
                array_agg(team_id order by game_id desc limit 1)[offset(0)] as team_id
            from `{p}.nhl_staging.stg_rosters`
            where season = '{season}' and substr(cast(game_id as string), 5, 2) in ('01', '02', '03')
            group by 1
        )
        select c.*, t.team_id from comp c join team t using (player_id)
    """)
    df = df[df["team_id"].notna()].copy()
    df["team_id"] = df["team_id"].astype("int64")
    for col in SKATER_COMPONENTS + ["goalie_gsax", "toi_5v5"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["role"] = df["position"].map(role_of)
    return df[df["role"].notna()].copy()


def compute(players: pd.DataFrame, season: str) -> pd.DataFrame:
    """Per (team, role, component): summed depth strength -> league percentile -> need = 1 - pctile."""
    rows = []
    for (team_id, role), sub in players.groupby(["team_id", "role"]):
        if role == "G":
            rows.append((team_id, "G", "goaltending", float(sub["goalie_gsax"].sum())))
        else:
            # finishing is a forward skill — for defensemen it's a tiny, shot-volume-shrunk sample
            # whose percentile is mostly noise, so it's excluded from D need (it otherwise spikes a
            # lucky-goal depth D's need_score). C/W keep all five components.
            for comp in components_for_role(role):
                rows.append((team_id, role, comp, float(sub[comp].sum())))
    df = pd.DataFrame(rows, columns=["team_id", "role", "component", "team_strength"])
    # league percentile of depth strength within each (role, component); need = how weak that is
    df["league_pctile"] = df.groupby(["role", "component"])["team_strength"].rank(pct=True)
    df["need"] = (1.0 - df["league_pctile"]).clip(0.0, 1.0)
    df["season"] = season
    df["label"] = df.apply(lambda r: f"{ROLE_LABEL[r['role']]} · {COMPONENT_LABEL[r['component']]}", axis=1)
    df["model_version"] = "team_needs_v2"
    return df[["team_id", "season", "role", "component", "label",
               "team_strength", "league_pctile", "need", "model_version"]]


def _abbrev(p: str, season: str) -> dict:
    df = bq.query_df(f"""select team_id, any_value(team_abbrev) a
                         from `{p}.nhl_mart.mart_team_game_stats`
                         where season = '{season}' group by 1""")
    return dict(zip(df["team_id"], df["a"]))


def report(out: pd.DataFrame, p: str, season: str) -> None:
    abbrev = _abbrev(p, season)
    print(f"\n=== Biggest role-and-component needs (sample teams), {season} ===")
    for team_id in sorted(out["team_id"].unique())[:4]:
        sub = out[out.team_id == team_id].sort_values("need", ascending=False).head(3)
        needs = ", ".join(f"{r.label} (need {r.need:.2f})" for r in sub.itertuples())
        print(f"  {abbrev.get(team_id, team_id)}: {needs}")
    # the single weakest center-depth and goaltending teams (smell test)
    for role, comp in (("C", "ev_offense"), ("G", "goaltending")):
        s = out[(out.role == role) & (out.component == comp)].sort_values("need", ascending=False).head(3)
        names = ", ".join(f"{abbrev.get(r.team_id, r.team_id)} ({r.need:.2f})" for r in s.itertuples())
        print(f"  weakest {ROLE_LABEL[role]}/{COMPONENT_LABEL[comp]}: {names}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    p = bq.project()
    season = args.season or _latest_season(p)

    players = pull_players(p, season)
    out = compute(players, season)
    report(out, p, season)

    if args.dry_run:
        print(f"\n[dry-run] {len(out)} rows not written")
        return
    out["team_id"] = out["team_id"].astype("int64")
    bq.write_df(out, "team_needs", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season", "team_id"])
    print(f"\nWrote {len(out)} rows to nhl_models.team_needs (team_needs_v2).")


if __name__ == "__main__":
    main()
