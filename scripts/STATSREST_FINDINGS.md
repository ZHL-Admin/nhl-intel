# Phase 1.3 endpoint findings

Probed 2026-06-13 against live NHL APIs. These notes justify the parsing choices in
`ingestion/nhl_api.py` and the `stg_*` models. "Offseason" below means the probe ran
in June with no current-day games, which limits live validation of two surfaces.

## A) Faceoffs by zone (stats REST)

- **Working report:** `GET https://api.nhle.com/stats/rest/en/skater/faceoffwins`
  with `cayenneExp=seasonId={YYYYYYYY} and gameTypeId={2|3}`, paged via `limit`/`start`
  (use `limit=100`; the season `total` ~= 900+ players). Returns `{"data": [...], "total": N}`.
- **This is the richest report** and the one we ingest. Per-player fields include:
  - Zone splits: `offensiveZoneFaceoffWins/Losses/Faceoffs`, `neutralZone*`, `defensiveZone*`.
  - Strength splits: `evFaceoffsWon/Lost/Faceoffs`, `ppFaceoffs*`, `shFaceoffs*`.
  - Totals: `totalFaceoffWins/Losses/Faceoffs`, `faceoffWinPct`, `gamesPlayed`.
  - Identity: `playerId`, `skaterFullName`, `positionCode`, `teamAbbrevs`, `seasonId`.
- **`skater/faceoffpercentages`** also works but is redundant — it only exposes the
  per-zone/strength *percentages* (`offensiveZoneFaceoffPct`, etc.) plus `timeOnIcePerGame`
  and `shootsCatches`. We derive percentages ourselves from the win/loss counts in
  `faceoffwins`, so we do NOT ingest faceoffpercentages.
- Zone-specific report names (`faceoffwins-byzone`, etc.) do **not** exist; the zone
  detail is columns on `faceoffwins`, not separate reports.
- **Historical depth: ≥2010-11** (probed: faceoffwins returns ~880–1000 players/season
  for 2010-11, 2013-14, 2015-16, 2018-19, 2021-22, 2024-25). Unlike Edge/ppt-replay (which
  are tracking-era only), faceoff splits are available for the full 16-season core window,
  so they are backfilled 2010-11→2025-26 to match pbp/shifts.

## B) Game landing + right-rail (api-web.nhle.com)

- **Landing:** `GET /v1/gamecenter/{gameId}/landing`. Goal video links live at
  `summary.scoring[].goals[]`. Confirmed per-goal fields (real payload, game 2025030414):
  - `eventId` (joins to play-by-play), `playerId`, `period` (via the scoring period's
    `periodDescriptor`), `timeInPeriod`, `teamAbbrev`, `shotType`, `goalModifier`, `assists`.
  - **Highlight links:** `highlightClipSharingUrl` (the shareable nhl.com/video URL we use),
    `highlightClip` (numeric id), and `pptReplayUrl` (relevant to Phase 1.4).
- **Right-rail:** `GET /v1/gamecenter/{gameId}/right-rail`. Top-level keys:
  `seasonSeries` (list of prior meetings), `seasonSeriesWins` (`{awayTeamWins, homeTeamWins,
  neededToWin}`), `gameInfo` (`{referees, linesmen, awayTeam:{headCoach, scratches},
  homeTeam:{headCoach, scratches}}`), `teamGameStats` (list of `{category, awayValue, homeValue}`),
  `linescore`, `shotsByPeriod`, `gameVideo`, `gameReports`.
- **Last-10 records are NOT in landing or right-rail.** They are served from
  `stg_standings` (the standings payload carries `l10Wins/l10Losses/l10OtLosses`), joined
  by team as-of the game date in the backend `/games/{id}/context` endpoint.

## C) Partner odds (api-web.nhle.com)

- `GET /v1/partner-game/US/now` → `{currentOddsDate, bettingPartner, games: [...]}`.
- `bettingPartner` resolved to DraftKings (partnerId 9) during the probe.
- **`games` was empty (offseason).** The per-game odds field shape therefore could not be
  captured from a live payload. `stg_partner_odds` is written against the documented
  partner-game schema (american odds per side → de-vigged implied win probabilities) but
  is flagged PENDING in-season validation in its model header and schema.yml. Ingestion
  (raw table + DAG task) is fully wired regardless, so snapshots accumulate once games return.
- Internal calibration only (blueprint 13.2): **no backend endpoint, no frontend surface.**

## D) Utilities

- **Glossary:** the plan's `api-web.nhle.com/v1/glossary` is **dead (404)**. The live
  glossary is `GET https://api.nhle.com/stats/rest/en/glossary` →
  `{"data": [{id, abbreviation, definition}, ...], "total"}`. Ingested once into
  `raw_glossary` (raw only; Phase 6 concept cards consume it — no staging model yet).
- **Standings:** `GET /v1/standings/{YYYY-MM-DD}` → `{wildCardIndicator, standings: [...]}`,
  one row per team (32 in-season). Confirmed fields used by `stg_standings`: `teamAbbrev`
  (`{default}`), `teamName` (`{default, fr}`), `points`, `wins`, `losses`, `otLosses`,
  `gamesPlayed`, `leagueSequence`/`conferenceSequence`/`divisionSequence` (ranks),
  `conferenceName`/`divisionName`, `l10Wins/l10Losses/l10OtLosses`, `streakCode`/`streakCount`.
  Returns 0 rows for offseason dates past the season's final game (validated against an
  in-season date, 2026-01-15, which returned all 32 teams).
</invoke>
