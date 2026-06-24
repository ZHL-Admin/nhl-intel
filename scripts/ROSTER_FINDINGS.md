# Live-Roster Ingestion — API Findings

All facts below are from REAL pasted smoke output (`scripts/smoke_ingest_roster.py`),
not assumed. Run against TOR, 2026-06 (offseason).

## Endpoints (status verified)

| Endpoint | Status | Notes |
|---|---|---|
| `GET api-web /v1/roster/{TEAM}/current` | **307** (empty body) | Redirect; httpx does not follow by default. NOT used directly. |
| `GET api-web /v1/roster/{TEAM}/{season8}` | **200** | The actual data endpoint. `season8` = 8-digit, e.g. `20242025`. |
| `GET api-web /v1/roster-season/{TEAM}` | **200** | `list[int]` of every season8 the team has a roster for (e.g. `19271928 … latest`). |
| `GET api /stats/rest/en/players?cayenneExp=currentTeamId={id}` | **200** | Cross-check only; carries `currentTeamId` directly. |

### Endpoint deviation from the plan (the API wins)
The plan named `/roster/{TEAM}/current` as primary. That path is a **307 redirect**, so we
resolve "current" deterministically instead: **`max(/roster-season/{TEAM})` → `/roster/{TEAM}/{season8}`**.
Both are confirmed-200 with a fully-seen schema, and this avoids an offseason redirect landing
on an unpublished season. `max(roster-season)` becomes the new season the moment NHL publishes it,
so offseason trades surface exactly when NHL reflects them — same semantics `/current` points to.

## `/roster/{TEAM}/{season8}` payload shape (the source of truth)

Top-level keys: `forwards`, `defensemen`, `goalies` (each a list of player objects).
There is **no team field on the player object** — affiliation is implied by the per-team
endpoint, so the refresh tags each row with the `team_abbrev` it requested.

Player object item keys (forwards/defensemen identical; goalies omit `birthStateProvince`):

```
id                  int      <- player_id (joins stg_rosters.player_id, etc.)
headshot            string   url
firstName           object   { default, plus locale variants cs/de/... } -> use $.firstName.default
lastName            object   { default }                                 -> use $.lastName.default
sweaterNumber       int
positionCode        string   C/L/R/D/G
shootsCatches       string   L/R
heightInInches      int
weightInPounds      int
heightInCentimeters int
weightInKilograms   int
birthDate           string   YYYY-MM-DD
birthCity           object   { default }
birthCountry        string
birthStateProvince  object   { default }   (absent on some goalies)
```

`firstName` carries many locale keys that vary per player (Abruzzese has cs/de/es/fi/sk/sv;
most players have only `default`). This is exactly the schema-drift case the loader handles
by serializing nested arrays to JSON strings — so `raw_rosters` serializes
`forwards`/`defensemen`/`goalies` and `stg_roster_current` parses them with
`json_extract_array` + `json_extract_scalar($.field.default)`, drift-proof.

## stats-REST cross-check shape (validation only, never in the refresh path)

`{ data: list, total: int }`; each `data` item: `id`, `currentTeamId`, `firstName`, `fullName`,
`lastName`, `positionCode`, `sweaterNumber`. Useful to confirm `/roster` membership, but we keep
ONE authoritative source (api-web `/roster`) so a player can never resolve to two teams.

## Resolution decisions (locked)

1. **Newest snapshot wins.** Each daily refresh appends 32 teams' rows; `stg_roster_current`
   keeps `row_number() over (partition by player_id order by ingestion_date desc) = 1`, so the
   "current" snapshot is unambiguous even after a trade between runs.
2. **Live roster is the single source of membership truth.** stats-REST `currentTeamId` is a
   cross-check only.
3. **Nobody is dropped.** `int_player_current_team` LEFT JOINs live membership onto the full
   player universe (latest-game roster) and uses `coalesce(live_team, latest_game_team)`. UFAs,
   minor-leaguers, and between-contract players absent from every `/roster` keep their last-game
   team (game-type `01/02/03` filter preserved) — best available without contract data.

## Caveat preserved in code (membership ≠ performance)

Updating the team LABEL is separate from updating PERFORMANCE with the new club. A just-traded
player has zero games with his new team, so impact/archetype/radar/value still reflect old-team
usage until he plays. The live roster fixes the team label only.
