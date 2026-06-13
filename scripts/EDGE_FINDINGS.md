# NHL Edge ingestion findings (Phase 1.2)

Status: **blocked on endpoint discovery.** The plan's assumed endpoints do not
exist; the real Edge data API was not discoverable by static probing and needs a
one-time browser network capture (see "What's needed" below).

## What the plan assumed
```
GET https://api-web.nhle.com/v1/edge/skater-detail/{playerId}/{season}
GET https://api-web.nhle.com/v1/edge/goalie-detail/{playerId}/{season}
GET https://api-web.nhle.com/v1/edge/team-detail/{teamId}/{season}
```

## What is actually true (probed live, 2026-06)
| Endpoint / source | Result |
|---|---|
| `api-web.nhle.com/v1/edge/skater-detail/8478402/20252026` | **404** |
| `api-web.nhle.com/v1/edge/goalie-detail/...`, `team-detail/...` | **404** |
| `api-web.nhle.com/v1/edge/skater/{id}/{season}`, `/v1/player/{id}/edge` | **404** |
| `edge.nhl.com/en/skater/{id}` | 200 — but it's the **SPA HTML page**, not data |
| `edge.nhl.com/api/v1/skater/{id}/{season}` | 200 — also the **SPA shell** (`<!DOCTYPE html> NHL EDGE…`), not JSON |
| `wsr.nhle.com/config` (service registry referenced by the page) | **403** |
| `api.nhle.com/stats/rest/en/config` (report catalog) | 200 JSON, but contains **no** report mentioning edge / speed / distance / skating / burst / zonetime / tracking |
| `api.nhle.com/stats/rest/en/skater/skatingspeed`, `…/skatingdistance`, `…/puckpossession` | **500** (not valid reports) |
| `api.nhle.com/stats/rest/en/skater/realtime`, `…/timeonice` | 200 JSON — but these are **standard** stats (hits/blocks/takeaways, TOI), **not** Edge tracking (speed, distance, bursts, zone-time-by-strength, shot speed) |

**Conclusion:** NHL Edge tracking metrics are not exposed through any public
api-web or stats-REST JSON endpoint reachable by static probing. The edge.nhl.com
SPA fetches them dynamically from a source that the static HTML/config does not
reveal (likely a protected or differently-shaped data API).

## What's needed to unblock (the one thing that can't be done by static probing)
Capture the **real XHR** the Edge site makes:

1. Open `https://edge.nhl.com/en/skater/8478402` in Chrome.
2. Open DevTools → **Network** tab → filter **Fetch/XHR** → reload the page.
3. Find the request whose JSON response contains the tracking numbers shown on the
   page (skating speed, distance, zone time, bursts). Right-click → **Copy URL**.
4. Paste that URL here, or run:
   ```
   python scripts/explore_edge.py --url '<that-url-with-{id}-and-{season}>' \
       --skater 8478402 --goalie <a goalie id> --team 10 --season 20252026
   ```
   It will save real payloads to `scripts/edge_samples/` and print their schema.

Once the real payloads exist, the rest of Phase 1.2 (typed staging models, the
`mart_edge_*` profiles, `/players/{id}/edge` + `/teams/{id}/edge` endpoints,
`refresh_edge.py`, `backfill_edge.py`) gets built **from the actual field names** —
no imagined schemas.

## Fallback if Edge proves genuinely inaccessible
Per the blueprint, features may die when the API can't support them. If no public
Edge endpoint is recoverable, the dependent features degrade as follows (and must
say so in the UI, never fake it):
- **Archetypes (4.2):** drop the Edge feature block; fit on seq-type / shot-location /
  impact / deployment features only (the plan already specifies "Edge features where
  available").
- **Territory-to-danger conversion (3.2 / 12.1):** the oz-time input comes from Edge;
  without it, fall back to the event-derived zone-time proxy (`mart_team_zone_time`,
  already labeled a proxy) and label the conversion panel a proxy too.
- **Physical aging overlay (4.4 / 12.2):** burst-rate decline needs Edge; if absent,
  ship the production aging curve without the physical leading-indicator and say so.
- **Edge cross-validation (2.5 / 12.3 / 7.1):** becomes N/A; document it as such.
