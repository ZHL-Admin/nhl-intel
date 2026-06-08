#!/bin/bash
# Monitor historical backfill progress from local machine
# Queries BigQuery and Airflow API to track progress

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

AIRFLOW_URL="http://136.111.233.177:8080"

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}NHL Historical Backfill Monitor${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

while true; do
    clear
    echo -e "${GREEN}NHL Historical Backfill Progress Monitor${NC}"
    echo "Last updated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "${GREEN}======================================${NC}"
    echo ""

    # Check Airflow scheduler health
    echo -e "${YELLOW}Airflow Scheduler Status:${NC}"
    SCHEDULER_STATUS=$(curl -s "${AIRFLOW_URL}/health" | jq -r '.scheduler.status // "unknown"')
    if [ "$SCHEDULER_STATUS" == "healthy" ]; then
        echo -e "${GREEN}✓ Scheduler: ${SCHEDULER_STATUS}${NC}"
    else
        echo -e "${RED}✗ Scheduler: ${SCHEDULER_STATUS}${NC}"
    fi
    echo ""

    # Check seasons loaded
    echo -e "${YELLOW}Seasons Loaded (raw_boxscores):${NC}"
    bq query --use_legacy_sql=false --format=pretty --max_rows=20 "
        SELECT
            season,
            COUNT(DISTINCT game_id) as games,
            MIN(ingestion_date) as first_load,
            MAX(ingestion_date) as last_load
        FROM \`nhl-intel-498216.nhl_raw.raw_boxscores\`
        GROUP BY season
        ORDER BY season
    " 2>/dev/null || echo -e "${RED}Error querying BigQuery${NC}"
    echo ""

    # Check for failures
    echo -e "${YELLOW}Backfill Failures:${NC}"
    bq query --use_legacy_sql=false --format=pretty --max_rows=20 "
        SELECT
            season,
            data_type,
            COUNT(*) as failures
        FROM \`nhl-intel-498216.nhl_raw.raw_backfill_failures\`
        GROUP BY season, data_type
        ORDER BY season, data_type
    " 2>/dev/null || echo "No failures table yet (will be created on first failure)"
    echo ""

    # Check staging layer
    echo -e "${YELLOW}Staging Layer (stg_games):${NC}"
    bq query --use_legacy_sql=false --format=pretty --max_rows=20 "
        SELECT
            season,
            COUNT(DISTINCT game_id) as games
        FROM \`nhl-intel-498216.nhl_staging.stg_games\`
        WHERE season >= '2015-16'
        GROUP BY season
        ORDER BY season
    " 2>/dev/null || echo "No staging data yet"
    echo ""

    # Progress summary
    echo -e "${GREEN}======================================${NC}"
    echo -e "${YELLOW}Target: 9 seasons (2015-16 through 2023-24)${NC}"
    echo -e "${YELLOW}Expected: ~1200-1400 games per season${NC}"
    echo -e "${GREEN}======================================${NC}"
    echo ""
    echo "Press Ctrl+C to exit. Refreshing in 60 seconds..."

    sleep 60
done
