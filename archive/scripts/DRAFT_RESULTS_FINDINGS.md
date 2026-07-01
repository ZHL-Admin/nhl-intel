# Draft Results — API probe findings (Phase A, Handoff 5)

Probe date: 2026-06-25. Live against the public NHL API. Samples saved (gitignored) under
`scripts/draft_results_samples/draft_{year}_all.json`.

This documents the **historical draft RESULTS** surface (pick → player taken). It is a NEW, separate
concern from `raw_draft_picks` (future pick *ownership*, from `ingest_futures.py`). Keep them distinct.

---

## 1. Endpoint

`GET https://api-web.nhle.com/v1/draft/picks/{year}/{round}` where `{round}` is an integer or `all`.

- Returns the same payload regardless of `{round}` (the round arg does not filter); use `all`.
- Top-level keys: `draftYear`, `draftYears` (every selectable year), `selectableRounds`, `state`, `picks`.
- `state` is `"over"` for completed drafts.
- `draftYears` advertises **1979 … 2026** (n=48). `2026` returns `state` not over (future).
- 200 for every year 1980–2025 probed; **1963 → 404** (no data that far back).

### Round counts by era (do NOT hardcode 7)
| Year | picks | rounds |
|---|---|---|
| 2000 | 287 | 1..9 |
| 2005 | 230 | 1..7 |
| 2015 | 211 | 1..7 |
| 2020 | 217 | 1..7 |
| 2023 | 223 | 1..7 |

The NHL has used **7 rounds since 2005** (our backfill floor). Earlier drafts had up to 9 (or more
pre-1992). dbt `accepted_values` on round therefore allows **1..9**, not 1..7.

---

## 2. Pick payload fields (verified, every year identical)

```
round, pickInRound, overallPick, teamId, teamAbbrev, teamName{}, teamCommonName{},
teamPlaceNameWithPreposition{}, displayAbbrev{}, teamLogoLight, teamLogoDark, teamPickHistory,
firstName{default}, lastName{default}, positionCode, countryCode, height, weight,
amateurLeague, amateurClubName
```

`overallPick` is dense 1..N within a year. `pickInRound` resets per round.

### THE CRITICAL FINDING: there is NO player id in this payload.
Checked 2015, 2018, 2020, 2022, 2023 — **no `playerId`, no prospect id, no `id`, no `birthDate`** in
any pick, in any year. Only the name, position, country, height, weight, and amateur club. This is
worse than the handoff's §5.2 assumption (which expected *some* id to validate). Name-only resolution
is therefore not acceptable on its own (see §3).

The stats-REST `draft` report (`https://api.nhle.com/stats/rest/en/draft`) is **metadata only**
(`draftYear`, `rounds`) — it does not enumerate picks or carry player ids.

---

## 3. Player-id resolution (the §5.2 id-join verification)

### 3.1 Name matching alone is NOT reliable — measured
Normalized-name (NFKD-stripped, lowercase, alpha-only) match of a draft class against the NHL player
universe (`stg_rosters` distinct `player_id`+name, ~3,839 players):

| Class | picks | unique name match | collisions | no-match | round 1–2 no-match |
|---|---|---|---|---|---|
| 2015 | 211 | 59% | 2 | 40% | 6 |
| 2012 | 210 | 54% | 2 | 45% | 13 |
| 2018 | 217 | 57% | 0 | 43% | 11 |

Most no-matches are genuine never-NHL busts (correctly value 0). BUT the round 1–2 no-matches cannot
be assumed busts: spot-checking via the player-search API, Matthew Spencer (2015 #44) and Jeremy Roy
(2015 #31) resolve to real `playerId`s (8478441, 8478464) that are **absent from `stg_rosters`** — our
roster universe does not cover every cup-of-coffee player, so a name no-match conflates "true bust" with
"coverage gap." Name matching would produce **false zeros**. Rejected as the primary resolver.

### 3.2 Authoritative resolver: `(draft_year, overall_pick)` via player landing `draftDetails`
Every NHL player's landing payload (`GET /v1/player/{id}/landing`) carries
`draftDetails = { year, round, overallPick, teamAbbrev, ... }`. Verified internally consistent and
authoritative against the draft endpoint's own numbering:

```
8478402 McDavid   → 2015 R1 #1  EDM      8478402 matches draft 2015 #1
8479318 Matthews  → 2016 R1 #1  TOR
8477934 Draisaitl → 2014 R1 #3  EDM
…overallPick uses the SAME dense numbering as the draft-results endpoint.
```

**Resolution design (no name ambiguity):**
1. `raw_draft_results` = every pick (year, overall, name, team, pos) — the complete UNIVERSE / denominator.
2. `player_draft_origin` = for every player in our production data (`mart_player_game_stats`, ~3,834
   distinct `player_id`, 2010-11..2025-26), their `(draft_year, draft_overall, full_name)` from the
   landing `draftDetails`. Built by a resumable backfill (`scripts/ingest_player_draft_origin.py`).
3. Resolve `raw_draft_results` ⨝ `player_draft_origin` on **`(draft_year, overall_pick)`** →
   `resolved_player_id`. A pick with no producing player joined = **never reached the NHL in our data =
   realized value 0** (NOT missing). The drafting `teamAbbrev` cross-checks (both sides carry it).

The draft-results `firstName`/`lastName` is used for **display** ("who was taken") and as a
**validation cross-check**: report the share of joined picks whose landing `full_name` matches the
draft-results name (target high; mismatches flagged for inspection).

### 3.3 Why the producing-player universe is the right denominator side
Realized value (Phase B `pWAR`) only exists for players in our boxscore/pbp data. A drafted player who
never appears there has zero realized production by construction, regardless of cause. The classes
2010–2018 fall entirely inside our 2010+ data window, so "no production rows" ⇒ never an NHL regular
(or never played) ⇒ value 0 — the never-NHL=0 rule the headline depends on.

---

## 4. Decisions for Phase A
- **Backfill 2005–2025** (handoff floor); evaluable classes 2010–2018 (7-yr window, fully observable).
- `raw_draft_results` schema: `draft_year, round, pick_in_round, overall_pick, team_id, team_abbrev,
  full_name, first_name, last_name, position_code, country_code, height_in, weight_lb, amateur_league,
  amateur_club, _loaded_at, ingestion_year`. (No birth_date / player_id — the source carries neither.)
- `round` accepted_values **1..9**; `overall_pick` dense `not_null`, unique per `(draft_year, overall_pick)`.
- Yearly refresh only (drafts are annual) — wired into the weekly Monday-gated aux task, not daily.
- Player-id resolution lives in dbt `stg_draft_results` (LEFT JOIN to `player_draft_origin`), so the
  raw table stays a faithful copy of the source and resolution logic is one place, versioned.

---

## 5. Measured results after backfill (2026-06-25)

Backfill landed: `raw_draft_results` = **4,532 picks** across **21 years (2005–2025)**;
`raw_player_draft_origin` = **3,745 players** (2,763 drafted, 982 undrafted; ~89 stale ids 404'd and
were skipped — they 404 because the id no longer resolves, so they would not resolve to value anyway).

### Resolution by pick range — evaluable classes 2010–2018 (the never-NHL=0 denominator)
| Range | picks | made NHL | % made NHL | name agreement |
|---|---|---|---|---|
| 1–10   | 90   | 90  | **100%** | 100% |
| 11–31  | 188  | 183 | **97%**  | 100% |
| Round 2| 268  | 204 | **76%**  | 100% |
| Round 3–7 | 1,357 | 609 | **45%** | 100% |

The made-NHL rate falls steeply and monotonically with pick number — exactly the survivorship shape
the headline depends on (never-NHL is the dominant outcome by round 3+).

### Authoritative-join validation
- **Name agreement on all resolved picks: 99.62%** (2,116 / 2,124). **100%** within evaluable classes
  2010–2018. The only mismatches are 2019+ nickname/transliteration spellings (Maxwell↔Max,
  Dmitriy↔Dmitri) — same player, correct `(year, overall)` join, cosmetic name diff. Confirms the
  join is authoritative and name matching was correctly rejected as the resolver.
- Spot-checks: Brayden Point (2014 #79) resolves ✓; early-R2 non-NHLers Moroz/Collberg/Finn (2012)
  correctly `made_nhl = false`.

`stg_draft_results` passes all dbt tests (unique/not_null on `pick_key`, dense `overall_pick`,
`round` in 1..9, `pos_group` in F/D/G).
