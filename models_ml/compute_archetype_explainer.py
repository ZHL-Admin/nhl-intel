"""
Archetype explainer data layer (gallery + player style-map). Reads the v2 archetype artifacts —
NO retrain. Reuses fit_archetypes_v2 (build_v2, the canonical GMM, the universal-trait audit) and
the shipped player_radar spokes.

Writes two tables:
  nhl_models.archetype_gallery   — one row per DISPLAY archetype (12 F + 11 D; D3+D4 merge to
    "Depth Defenseman"): name, family, descriptor, member_count, universal traits, distinctive
    traits, the characteristic CENTROID RADAR (mean of members' radar spokes), and exemplars.
  nhl_models.player_style_map    — one row per tracking-era player-season: 2D PCA coords of the
    clustering feature vector (F and D projected SEPARATELY — different feature spaces), the
    primary archetype, membership strength, and a boundary flag (split membership).

Honest by construction: archetypes are DISCOVERED clusters. The map plots where real players sit;
gaps stay empty. Nothing here lets a user invent an archetype.

Run:  python -m models_ml.compute_archetype_explainer [--dry-run]
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from models_ml import bq, config
from models_ml.archetype_features_v2 import FEATURES_V2
from models_ml.fit_archetypes_v2 import SEASONS, FEATURE_COLS, fit_or_load, _universal
from models_ml.archetype_features_v2 import build_v2

CURRENT = "2025-26"
# orientation: pin PCA so a high-offence player sits to the +x / +y side (sign is otherwise arbitrary)
ORIENT_X = "rapm_off"
ORIENT_Y = "edge_oz_time"


def _latest_teams(ids: list[int]) -> dict[int, str]:
    ids = [int(i) for i in set(ids)]
    if not ids:
        return {}
    df = bq.query_df(f"""
        WITH r AS (
            SELECT player_id, team_id,
                   ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY game_id DESC) AS rn
            FROM `{bq.project()}.nhl_staging.stg_rosters`
            WHERE player_id IN ({", ".join(str(i) for i in ids)})
              AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
        ),
        tm AS (SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev
               FROM `{bq.project()}.nhl_mart.mart_team_game_stats` GROUP BY team_id)
        SELECT r.player_id, tm.abbrev FROM r JOIN tm USING (team_id) WHERE r.rn = 1
    """)
    return {int(r.player_id): r.abbrev for r in df.itertuples()}


def _names(ids: list[int]) -> dict[int, str]:
    ids = [int(i) for i in set(ids)]
    if not ids:
        return {}
    df = bq.query_df(f"""SELECT player_id, ANY_VALUE(first_name||' '||last_name) AS name
                         FROM `{bq.project()}.nhl_staging.stg_rosters`
                         WHERE player_id IN ({", ".join(str(i) for i in ids)}) GROUP BY 1""")
    return dict(zip(df["player_id"], df["name"]))


def _radar_map() -> tuple[dict, list[str]]:
    """(player_id, season) -> [spoke dicts]; plus the canonical spoke ORDER (longest radar seen)."""
    seasons = ", ".join(f"'{s}'" for s in SEASONS)
    df = bq.query_df(f"SELECT player_id, season, spokes FROM `{bq.project()}.nhl_models.player_radar` "
                     f"WHERE season IN ({seasons})")
    m, order = {}, []
    for r in df.itertuples():
        sp = json.loads(r.spokes)
        m[(int(r.player_id), r.season)] = sp
        if len(sp) > len(order):
            order = [s["key"] for s in sp]
    return m, order


def _centroid_radar(members: pd.DataFrame, radar_map: dict, order: list[str]) -> list[dict]:
    acc: dict[str, dict] = {}
    for r in members.itertuples():
        sp = radar_map.get((int(r.player_id), r.season))
        if not sp:
            continue
        for s in sp:
            if s.get("percentile") is None:
                continue
            a = acc.setdefault(s["key"], {"label": s["label"], "tag": s["tag"], "vals": []})
            a["vals"].append(s["percentile"])
    spokes = []
    for key in order:
        a = acc.get(key)
        if not a or len(a["vals"]) < 5:
            continue
        spokes.append({"key": key, "label": a["label"], "tag": a["tag"], "value": None,
                       "percentile": round(float(np.mean(a["vals"])), 1),
                       "sd": round(float(np.std(a["vals"])), 1), "present": True})
    return spokes


def _exemplars(g: pd.DataFrame, mem: np.ndarray, weight: np.ndarray, comp_map: dict,
               names: dict, teams: dict, dominant: dict, arche_name: str, n=4) -> list[dict]:
    """The BEST PLAYERS in the archetype by overall value (composite) — for name recognition —
    not the best pure membership matches. A player only exemplifies the archetype that is his
    CAREER-DOMINANT type (most total membership across his seasons), so a star's one anomalous
    season (e.g. an elite scorer who clustered as a checker once) doesn't surface him under a niche
    type. Among those, one row per player at his highest-value member-season, ranked by that value."""
    best: dict[int, tuple] = {}   # player_id -> (value, season, weight)
    for i in mem:
        pid = int(g.loc[i, "player_id"])
        if dominant.get(pid) != arche_name:
            continue
        season = g.loc[i, "season"]
        val = comp_map.get((pid, season))
        if val is None:
            continue
        if pid not in best or val > best[pid][0]:
            best[pid] = (val, season, float(weight[i]))
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])[:n]
    return [{"player_id": pid, "name": names.get(pid, str(pid)), "season": s,
             "team_abbrev": teams.get(pid), "weight": round(w, 3)}
            for pid, (v, s, w) in ranked]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df = build_v2(SEASONS)
    df = df[df["toi_5v5"] >= config.ARCHETYPE_MIN_5V5_MIN].copy()
    groups = fit_or_load(df)
    radar_map, spoke_order = _radar_map()

    all_ids = df["player_id"].astype(int).tolist()
    names, teams = _names(all_ids), _latest_teams(all_ids)

    # per-(player, season) composite total -> archetype mean value (sorts the gallery: the types whose
    # members are the better players lead). Single-season composites only (member-seasons).
    seasons_sql = ", ".join(f"'{s}'" for s in SEASONS)
    comp = bq.query_df(f"SELECT player_id, season_window AS season, total FROM "
                       f"`{bq.project()}.nhl_models.player_composite` WHERE season_window IN ({seasons_sql})")
    comp_map = {(int(r.player_id), r.season): float(r.total) for r in comp.itertuples()}

    gallery, smap = [], []
    fx = FEATURE_COLS.index(ORIENT_X) if ORIENT_X in FEATURE_COLS else 0
    fy = FEATURE_COLS.index(ORIENT_Y) if ORIENT_Y in FEATURE_COLS else 1

    for pos in ["F", "D"]:
        g, X, resp, hard, k, means, scaler, gmm = groups[pos]
        g = g.reset_index(drop=True)

        # each player's CAREER-DOMINANT display archetype (most total membership across his seasons)
        name_of_cluster = {c: config.ARCHETYPE_NAMES_V2[f"{pos}{c}"] for c in range(k)}
        gp = g.assign(_pid=g["player_id"].astype(int))
        dominant: dict[int, str] = {}
        for pid, grp in gp.groupby("_pid"):
            rws = grp.index.to_numpy()
            agg: dict[str, float] = {}
            for c in range(k):
                agg[name_of_cluster[c]] = agg.get(name_of_cluster[c], 0.0) + float(resp[rws, c].sum())
            dominant[int(pid)] = max(agg, key=agg.get)

        # 2D projection (F and D separate feature spaces). Pin orientation by reference features.
        xy = PCA(n_components=2, svd_solver="full").fit_transform(X)
        comp = PCA(n_components=2, svd_solver="full").fit(X).components_
        if comp[0, fx] < 0:
            xy[:, 0] *= -1
        if comp[1, fy] < 0:
            xy[:, 1] *= -1

        # gallery: clusters grouped by DISPLAY name (D3+D4 -> one card)
        name_to_clusters: dict[str, list[int]] = {}
        order_names: list[str] = []
        for c in range(k):
            nm = config.ARCHETYPE_NAMES_V2[f"{pos}{c}"]
            if nm not in name_to_clusters:
                order_names.append(nm)
            name_to_clusters.setdefault(nm, []).append(c)

        for nm in order_names:
            clusters = name_to_clusters[nm]
            mem = np.where(np.isin(hard, clusters))[0]
            uni = _universal(X, mem)
            ctr = means.iloc[clusters].mean(axis=0)
            dist = ctr.reindex(ctr.abs().sort_values(ascending=False).index).head(6)
            weight = resp[:, clusters].sum(axis=1)
            key = f"{pos}{clusters[0]}" if len(clusters) == 1 else f"{pos}{'_'.join(map(str, clusters))}"
            mvals = [comp_map[(int(g.loc[i, "player_id"]), g.loc[i, "season"])] for i in mem
                     if (int(g.loc[i, "player_id"]), g.loc[i, "season"]) in comp_map]
            mean_value = float(np.mean(mvals)) if mvals else 0.0
            gallery.append({
                "pos_group": pos, "key": key, "name": nm,
                "family": config.ARCHETYPE_FAMILY_V2.get(f"{pos}{clusters[0]}", ""),
                "descriptor": config.ARCHETYPE_DESCRIPTORS_V2.get(f"{pos}{clusters[0]}", ""),
                "member_count": int(len(mem)), "mean_value": round(mean_value, 3),
                "universal_traits": json.dumps([
                    {"label": FEATURES_V2[f], "dir": d, "z": round(float(z), 2), "share": round(float(s), 2)}
                    for f, s, d, z in uni[:8]]),
                "distinctive_traits": json.dumps([
                    {"label": FEATURES_V2[f], "z": round(float(ctr[f]), 2)} for f in dist.index]),
                "centroid_radar": json.dumps(_centroid_radar(g.iloc[mem], radar_map, spoke_order)),
                "exemplars": json.dumps(_exemplars(g, mem, weight, comp_map, names, teams, dominant, nm)),
            })

        # style-map rows
        for i in range(len(g)):
            c = int(hard[i])
            smap.append({
                "player_id": int(g.loc[i, "player_id"]), "season": g.loc[i, "season"],
                "pos_group": pos, "x": round(float(xy[i, 0]), 4), "y": round(float(xy[i, 1]), 4),
                "archetype": config.ARCHETYPE_NAMES_V2[f"{pos}{c}"],
                "membership": round(float(resp[i].max()), 3),
                "is_boundary": bool(resp[i].max() < 0.6),
            })

    gdf = pd.DataFrame(gallery)
    sdf = pd.DataFrame(smap)
    print(f"gallery: {len(gdf)} archetypes ({int((gdf.pos_group=='F').sum())} F / "
          f"{int((gdf.pos_group=='D').sum())} D); style-map: {len(sdf)} player-seasons "
          f"({int(sdf.is_boundary.sum())} boundary)")
    for _, r in gdf.sort_values(["pos_group", "mean_value"], ascending=[True, False]).iterrows():
        ex = ", ".join(e["name"] for e in json.loads(r["exemplars"])[:3])
        print(f"  {r['pos_group']} {r['name']:24s} value {r['mean_value']:+6.2f} n={r['member_count']:3d}  ex: {ex}")

    if args.dry_run:
        print("\n[dry-run] not written")
        return
    gdf["model_version"] = "archetypes_v2"
    sdf["model_version"] = "archetypes_v2"
    bq.write_df(gdf, "archetype_gallery", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["pos_group"])
    bq.write_df(sdf, "player_style_map", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["pos_group", "season"])
    print(f"\nWrote archetype_gallery ({len(gdf)}) + player_style_map ({len(sdf)}).")


if __name__ == "__main__":
    main()
