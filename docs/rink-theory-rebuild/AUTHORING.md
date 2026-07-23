# RINK THEORY — running & authoring

## Running locally

The site is a live-data SPA: the Power Ratings page, the `/ratings/players` table,
and the Home rail all fetch from the backend. **With no backend reachable, those
surfaces show "Ratings unavailable" (or "Loading…") — not an error you can ignore.**

### 1. Backend (FastAPI, port 8000)

```bash
cd backend
uvicorn main:app --port 8000        # or: make backend
```

- Defaults to the **DuckDB serving snapshot** (`data/serving/nhl_intel.duckdb`) —
  `main.py` sets `SERVING_BACKEND=duckdb`; no BigQuery client on the request path.
- Sanity check: `curl http://localhost:8000/ratings` → 32 teams + a `data_through`
  date. If this fails, the frontend rail/ratings will be empty.
- A **stale backend process** started before the `/ratings` route existed will 404
  that route — restart it after pulling.

### 2. Frontend (Vite, port 5173)

```bash
cd frontend
npm ci
npm run dev
```

- The API base URL defaults to `http://localhost:8000`
  (`src/api/client.ts`: `import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'`).
- If the backend runs on a different host/port, set it:
  ```bash
  VITE_API_BASE_URL=http://localhost:8077 npm run dev
  ```

### Dev-only rail mode override

The Home rail auto-switches offseason vs in-season from the ratings `data_through`
(offseason when the data is > 30 days stale). To force a mode while developing:

- `/?rail=inseason` — Power Ratings + Luck Watch
- `/?rail=offseason` — Projected 2026-27 + Contract Watch

(Only honored when `import.meta.env.DEV` is true.)

## Authoring notes

- Notes live in `frontend/content/notes/*.mdx`. Frontmatter: `title, slug, date,
  dek, tags[], status, readingTime?, tool?`.
- **`status: draft` never ships** — drafts render in `npm run dev` only, and are
  excluded from the production notes index, the Home feed, and RSS. Publish by
  flipping to `status: published`.
- Figures are imported from the `@figures` kit; freeze figure data inline by
  default (§5.3). Cite every number in an MDX comment.

## Build & RSS

```bash
cd frontend
npm run build        # runs scripts/gen-rss.mjs (prebuild) → public/rss.xml, then tsc + vite build
```

- **Set a real `SITE_URL`** at build so RSS links aren't the `rinktheory.example`
  placeholder: `SITE_URL=https://<domain> npm run build`.
