"""Central configuration for the Deployment Atlas research pipeline.

Every knob the preamble pins down lives here so it is recorded in exactly one
place: the seed, the rate limit, the backoff schedule, and the API endpoints.
Nothing in this module performs I/O.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
# All randomness in the pipeline (backoff jitter, sampling, model seeding) is
# derived from this single seed and recorded in every run's metadata.
SEED: int = 20260710

# ---------------------------------------------------------------------------
# Fetch / rate-limit / backoff policy (preamble, non-negotiable)
# ---------------------------------------------------------------------------
MAX_REQUESTS_PER_SEC: float = 5.0          # hard ceiling across the client
BACKOFF_BASE_SECONDS: float = 2.0          # first retry waits ~2s
BACKOFF_MAX_SECONDS: float = 60.0          # never wait longer than this
MAX_RETRIES: int = 5                       # attempts after the first failure
RETRY_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
REQUEST_TIMEOUT_SECONDS: float = 30.0

# Polite, identifying User-Agent for a research client (task 0.1).
USER_AGENT: str = (
    "deployment-atlas/0.1 (NHL deployment research; non-commercial; "
    "contact: repo owner via github)"
)

# ---------------------------------------------------------------------------
# API endpoints (verified against real payloads in Phase 0)
# ---------------------------------------------------------------------------
SHIFTCHARTS_URL = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game_id}"
PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
CLUB_SCHEDULE_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team}/{season_id}"
SCORE_BY_DATE_URL = "https://api-web.nhle.com/v1/score/{date}"

# ---------------------------------------------------------------------------
# Game id semantics (preamble; re-verified in Phase 0)
# ---------------------------------------------------------------------------
# {season_start_year:4}{type:2}{game_number:4}
# In the id string: 01=preseason, 02=regular, 03=playoffs.
# In payload bodies the same concept appears as integer gameType 1/2/3.
GAME_TYPE_PRESEASON = "01"
GAME_TYPE_REGULAR = "02"
GAME_TYPE_PLAYOFF = "03"

# Shift-row typeCode semantics (verified in Phase 0). 517 = real player shift;
# 505 = embedded goal-marker row. Filtering rule adopted: keep typeCode == 517.
SHIFT_TYPECODE_SHIFT = 517
SHIFT_TYPECODE_GOAL = 505

# Standard regulation period length in seconds (for absolute-time math).
REGULATION_PERIOD_SECONDS = 1200

# ---------------------------------------------------------------------------
# Storage roots (all relative to the project root, which is this repo)
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PARQUET_DIR: Path = DATA_DIR / "parquet"
DUCKDB_PATH: Path = DATA_DIR / "atlas.duckdb"
REPORTS_DIR: Path = PROJECT_ROOT / "reports"
MANIFEST_PATH: Path = RAW_DIR / "manifest.json"
RUN_META_PATH: Path = RAW_DIR / "run_meta.json"
FETCH_LOG_PATH: Path = RAW_DIR / "fetch_log.json"
