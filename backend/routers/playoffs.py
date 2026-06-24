"""Playoff bracket predictor endpoint.

Builds a leakage-free bracket prediction: it pulls each team's power rating AS OF the last
regular-season game date (team_ratings stores a season-to-date snapshot per game_date, so that row
is computed only from regular-season games), the regular-season standings points (seeding / home
ice), and the identity-fingerprint percentiles (style matchup). The deterministic math + Monte-Carlo
simulation live in insight_engine.templates.playoff_bracket. No playoff results are ever read.
"""
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from models.schemas import (
    PlayoffBracket, PlayoffSeries, PlayoffTeamRef, PlayoffOdds, PlayoffPairwise,
)
from services.bigquery import bq_service
from services.cache import cache
from routers.teams import IDENTITY_METRIC_KEYS

router = APIRouter()

# Fallback first-round matchups, in BRACKET ORDER, used only if seeding can't be derived from
# standings for a season. The bracket is normally derived from stg_standings (_derive_bracket).
BRACKETS = {
    "2025-26": [
        ("COL", "LAK"), ("DAL", "MIN"), ("VGK", "UTA"), ("EDM", "ANA"),  # Western Conference
        ("BUF", "BOS"), ("TBL", "MTL"), ("CAR", "OTT"), ("PIT", "PHI"),  # Eastern Conference
    ],
}

_ROUND_LABELS = {1: "First Round", 2: "Second Round", 3: "Conference Final", 4: "Stanley Cup Final"}


def _derive_bracket(season: str) -> Optional[List[tuple]]:
    """Derive the 8 first-round matchups (bracket order, Western conf first) from standings seeds.

    NHL format per conference: each division's top 3 qualify + 2 wild cards; the conference's top
    division winner plays WC2, the other division winner plays WC1, and each division's 2-seed plays
    its 3-seed. Adjacent series in the returned list share a division winner's half (they meet in
    round 2). Returns None if the standings don't yield a clean 16-team bracket (caller falls back).
    """
    standings_tbl = bq_service.get_full_table_id('stg_standings')
    try:
        rows = bq_service.query(f"""
            WITH latest AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY team_abbrev ORDER BY standings_date DESC) AS rn
                FROM {standings_tbl}
            )
            SELECT team_abbrev, conference_name, division_name,
                   division_rank, wildcard_rank, conference_rank
            FROM latest WHERE rn = 1
        """)
    except Exception:
        return None

    by_conf: dict = defaultdict(list)
    for r in rows:
        if r.get('conference_name'):
            by_conf[r['conference_name']].append(r)

    pairs: List[tuple] = []
    for conf in sorted(by_conf, key=lambda c: (c != 'Western', c)):  # Western half first
        cr = by_conf[conf]
        dws = sorted([r for r in cr if r['division_rank'] == 1],
                     key=lambda r: (r['conference_rank'] if r['conference_rank'] is not None else 99))
        wc = {r['wildcard_rank']: r for r in cr if r['wildcard_rank'] in (1, 2)}
        if len(dws) < 2 or 1 not in wc or 2 not in wc:
            return None

        def two_three(div: str):
            d = {r['division_rank']: r for r in cr if r['division_name'] == div}
            if 2 not in d or 3 not in d:
                raise KeyError(div)
            return (d[2]['team_abbrev'], d[3]['team_abbrev'])

        try:
            dw_top, dw_bot = dws[0], dws[1]
            pairs += [
                (dw_top['team_abbrev'], wc[2]['team_abbrev']), two_three(dw_top['division_name']),
                (dw_bot['team_abbrev'], wc[1]['team_abbrev']), two_three(dw_bot['division_name']),
            ]
        except KeyError:
            return None

    return pairs if len(pairs) == 8 else None


def _norm_pctile(v) -> float:
    """Fingerprint percentiles may be stored 0-1 or 0-100; normalise to 0-1 for the style model."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    return f / 100.0 if f > 1.5 else f


@router.get("/bracket", response_model=PlayoffBracket)
@cache(ttl=3600)
async def get_bracket(
    season: Optional[str] = Query(None, description="Season (default: latest with a known bracket)"),
) -> PlayoffBracket:
    """Predicted playoff bracket: favorite tree + Monte-Carlo championship odds (no future data)."""
    from insight_engine.templates import playoff_bracket as pb

    mart = bq_service.get_full_table_id('mart_team_game_stats')
    ratings_tbl = bq_service.get_models_table_id('team_ratings')
    identity_tbl = bq_service.get_full_table_id('mart_team_identity')
    standings_tbl = bq_service.get_full_table_id('stg_standings')

    if not season:
        srows = bq_service.query(f"SELECT MAX(season) AS s FROM {ratings_tbl}")
        season = srows[0]['s'] if srows and srows[0].get('s') else None
    pairs = _derive_bracket(season) or BRACKETS.get(season)
    if not pairs:
        raise HTTPException(status_code=404, detail=f"No playoff bracket available for season {season}")
    abbrevs = [a for pair in pairs for a in pair]

    # Leakage cutoff: the last regular-season ('02') game date for the season.
    cut = bq_service.query(f"""
        SELECT MAX(game_date) AS d, AVG(goals_for) AS g
        FROM {mart}
        WHERE season = '{season}' AND substr(cast(game_id as string), 5, 2) = '02'
    """)
    if not cut or not cut[0].get('d'):
        raise HTTPException(status_code=404, detail="No regular-season games found for the season")
    cutoff = str(cut[0]['d'])
    g_avg = float(cut[0]['g']) if cut[0].get('g') else 3.05

    # Power rating snapshot AS OF the cutoff (season-to-date through the last regular-season game).
    rating_rows = bq_service.query(f"""
        WITH abbr AS (
            SELECT team_abbrev, ANY_VALUE(team_id) AS team_id
            FROM {mart} WHERE season = '{season}' GROUP BY team_abbrev
        ),
        snap AS (
            SELECT team_id, total_rating, rating_se, trajectory_15d,
                   contrib_play_5v5, contrib_finishing, contrib_goaltending, contrib_special_teams,
                   ROW_NUMBER() OVER (
                PARTITION BY team_id ORDER BY game_date DESC) AS rn
            FROM {ratings_tbl}
            WHERE season = '{season}' AND game_date <= DATE '{cutoff}'
        )
        SELECT a.team_abbrev, a.team_id, s.total_rating, s.rating_se, s.trajectory_15d,
               s.contrib_play_5v5, s.contrib_finishing, s.contrib_goaltending, s.contrib_special_teams
        FROM snap s JOIN abbr a USING (team_id)
        WHERE s.rn = 1
    """)
    rating_by_abbr = {r['team_abbrev']: r for r in rating_rows}

    # Regular-season standings points (seeding / home ice) + conference.
    std_rows = bq_service.query(f"""
        WITH latest AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY team_abbrev ORDER BY standings_date DESC) AS rn
            FROM {standings_tbl}
        )
        SELECT team_abbrev, points, conference_name FROM latest WHERE rn = 1
    """)
    std_by_abbr = {r['team_abbrev']: r for r in std_rows}

    # Identity fingerprint percentiles (season window) for the style matchup.
    ident_rows = bq_service.query(f"""
        SELECT * FROM {identity_tbl}
        WHERE season = '{season}' AND window_kind = 'season'
    """)
    fp_by_id = {
        r['team_id']: {k: _norm_pctile(r.get(f"{k}_pctile")) for k in IDENTITY_METRIC_KEYS}
        for r in ident_rows
    }

    # Assemble the team table the pure model consumes.
    teams: dict = {}
    for ab in abbrevs:
        rr = rating_by_abbr.get(ab)
        if not rr:
            raise HTTPException(status_code=404, detail=f"No rating snapshot for {ab} in {season}")
        tid = rr['team_id']
        teams[ab] = {
            "team_id": tid,
            "rating": float(rr['total_rating']),
            "rating_se": float(rr['rating_se']) if rr.get('rating_se') is not None else 0.0,
            "trajectory": float(rr['trajectory_15d']) if rr.get('trajectory_15d') is not None else 0.0,
            # Components for the playoff-specific re-weighting (keys match playoff_weights.json).
            "components": {
                "play_5v5": float(rr.get('contrib_play_5v5') or 0.0),
                "finishing": float(rr.get('contrib_finishing') or 0.0),
                "goaltending": float(rr.get('contrib_goaltending') or 0.0),
                "special_teams": float(rr.get('contrib_special_teams') or 0.0),
            },
            "points": float(std_by_abbr.get(ab, {}).get('points') or 0),
            "conference": std_by_abbr.get(ab, {}).get('conference_name'),
            "fp": fp_by_id.get(tid, {}),
        }

    tree = pb.predicted_tree(teams, pairs, g_avg)
    odds = pb.simulate(teams, pairs, g_avg)

    def ref(ab: str) -> PlayoffTeamRef:
        return PlayoffTeamRef(team_id=teams[ab]["team_id"], abbrev=ab)

    rounds_out: List[List[PlayoffSeries]] = []
    for ri, rnd in enumerate(tree):
        rno = ri + 1
        series_out = []
        for s in rnd:
            hi, lo = s["high"], s["low"]
            # favorite agrees with the tree pick: near-ties go to the higher seed (home-ice tiebreak)
            fav = s["winner"]
            conf = teams[hi]["conference"] if teams[hi]["conference"] == teams[lo]["conference"] else None
            series_out.append(PlayoffSeries(
                round=rno,
                round_label=_ROUND_LABELS.get(rno, f"Round {rno}"),
                conference=None if rno == 4 else conf,
                high=ref(hi), low=ref(lo),
                high_rating=round(teams[hi]["rating"], 3),
                low_rating=round(teams[lo]["rating"], 3),
                high_seed_winprob=round(s["p_high"], 4),
                high_seed_winprob_lo=round(s["p_high_lo"], 4),
                high_seed_winprob_hi=round(s["p_high_hi"], 4),
                favorite=fav,
                favorite_winprob=round(s["p_high"] if fav == hi else 1 - s["p_high"], 4),
                winner=s["winner"],
                coin_flip=bool(s.get("coin_flip", False)),
                style_modifier=round(s["style"], 3),
                recent_form_modifier=round(s["recent_form"], 3),
                style_reasons=s["reasons"],
            ))
        rounds_out.append(series_out)

    # Pairwise series probabilities for every possible matchup among the 16 teams, so the frontend
    # can score user-built "what-if" paths (incl. upsets the model didn't predict). Home ice is
    # handled inside series() by seed.
    pairwise_out: List[PlayoffPairwise] = []
    for i in range(len(abbrevs)):
        for j in range(i + 1, len(abbrevs)):
            a, b = abbrevs[i], abbrevs[j]
            sp = pb.series(a, b, teams, g_avg)
            a_win = sp["p_high"] if sp["high"] == a else 1 - sp["p_high"]
            pairwise_out.append(PlayoffPairwise(
                a=a, b=b, a_winprob=round(a_win, 4), higher_seed=sp["high"]))

    champ = tree[-1][0]["winner"]
    odds_out = sorted(
        (PlayoffOdds(
            team_id=teams[ab]["team_id"], abbrev=ab,
            reach_round2=round(o["r2"], 4), reach_conf_final=round(o["cf"], 4),
            reach_final=round(o["final"], 4), win_cup=round(o["cup"], 4),
        ) for ab, o in odds.items()),
        key=lambda x: x.win_cup, reverse=True,
    )

    return PlayoffBracket(
        season=season,
        as_of_date=cutoff,
        league_avg_goals=round(g_avg, 3),
        rounds=rounds_out,
        champion=ref(champ),
        champion_winprob=round(odds[champ]["cup"], 4),
        odds=odds_out,
        pairwise=pairwise_out,
    )
