"""Authorized one-time re-projection (UL-P1): recover the six player-attribution columns that the
Atlas `events.parquet` dropped but production `stg_play_by_play` already parses, plus per-player
faceoff W/L by zone from `stg_statsrest_faceoffs`. Writes probe-local parquet + a provenance/hash
manifest. This READS already-ingested BigQuery data; it writes NO production table and touches no
frozen Atlas asset.

Requires BigQuery creds (the deployment-atlas service-account keyfile). Run once with a BQ-capable
interpreter (e.g. deployment-atlas/.venv, which has google-cloud-bigquery). Everything downstream
reads the local parquet, so the probe stays a frozen-corpus project after this step.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import polars as pl

from . import config

ENRICH_DIR = config.PARQUET / "enriched"

# the six recovered event-player columns (keyed by game_id, event_id) + faceoffs source
_EVENT_PLAYER_SQL = """
select
  game_id, event_id,
  hitting_player_id, hittee_player_id, blocking_player_id,
  player_id as generic_player_id,        -- takeaway/giveaway actor (routed by event type downstream)
  committed_by_player_id, drawn_by_player_id
from `{proj}.nhl_staging.stg_play_by_play`
"""
_FACEOFF_SQL = """
select player_id, season_id, position_code, games_played,
  oz_faceoff_wins, oz_faceoff_losses, oz_faceoffs,
  nz_faceoff_wins, nz_faceoff_losses, nz_faceoffs,
  dz_faceoff_wins, dz_faceoff_losses, dz_faceoffs,
  ev_faceoff_wins, ev_faceoff_losses,
  total_faceoff_wins, total_faceoff_losses, total_faceoffs
from `{proj}.nhl_staging.stg_statsrest_faceoffs`
where game_type = 2
"""
# player handedness for the Link 2.4 non-role control (handedness mix). One row per player.
_BIO_SQL = "select player_id, shoots, position from `{proj}.nhl_staging.stg_player_bio`"


def _client():
    import sys
    sys.path.insert(0, str(config.ATLAS_SRC))
    from atlas import sources
    from google.cloud import bigquery
    return bigquery.Client.from_service_account_json(str(sources.SA_KEYFILE),
                                                     project=sources.BQ_PROJECT), sources.BQ_PROJECT


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pull(write: bool = True) -> dict:
    client, proj = _client()
    ENRICH_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"pulled_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "bq_project": proj, "source": "read-only; no production write", "files": {}}
    for name, sql in (("event_players.parquet", _EVENT_PLAYER_SQL),
                      ("faceoffs.parquet", _FACEOFF_SQL), ("player_bio.parquet", _BIO_SQL)):
        tbl = client.query(sql.format(proj=proj)).result().to_arrow()
        pf = pl.from_arrow(tbl)
        path = ENRICH_DIR / name
        pf.write_parquet(path)
        manifest["files"][name] = {"rows": pf.height, "cols": pf.columns, "sha256": _sha256(path),
                                   "query": " ".join(sql.split())}
    if write:
        with open(ENRICH_DIR / "MANIFEST.json", "w") as f:
            json.dump(manifest, f, indent=2)
    return manifest


if __name__ == "__main__":
    m = pull()
    for n, meta in m["files"].items():
        print(f"{n}: rows={meta['rows']:,} sha256={meta['sha256'][:16]}...")
    print("pulled_at:", m["pulled_at"])
