#!/bin/bash
# Full historical backfill trigger script for seasons 2015-16 through 2023-24
# Run this on the Airflow VM after pulling latest code and restarting containers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}NHL Historical Backfill Trigger${NC}"
echo -e "${GREEN}Seasons: 2015-16 through 2023-24${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Pre-flight checks
echo -e "${YELLOW}Running pre-flight checks...${NC}"

# 1. Check disk space
echo -e "\n${YELLOW}1. Checking disk space...${NC}"
AVAILABLE=$(df -h / | awk 'NR==2 {print $4}')
echo "Available space: ${AVAILABLE}"

# Simple check - just warn if less than 15G
AVAILABLE_NUM=$(echo "$AVAILABLE" | sed 's/[^0-9.]//g')
if [ -n "$AVAILABLE_NUM" ] && [ "${AVAILABLE_NUM%.*}" -lt 15 ]; then
    echo -e "${RED}WARNING: Less than 15GB available. Proceed with caution.${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo -e "${GREEN}✓ Disk space check passed${NC}"

# 2. Check Docker containers
echo -e "\n${YELLOW}2. Checking Docker containers...${NC}"

docker compose ps
echo -e "${GREEN}✓ Containers checked${NC}"

# 3. Verify backfill DAG exists
echo -e "\n${YELLOW}3. Verifying backfill DAG exists...${NC}"
if docker compose exec -T airflow-scheduler airflow dags list 2>/dev/null | grep -q "nhl_historical_backfill"; then
    echo -e "${GREEN}✓ Backfill DAG found${NC}"
else
    echo -e "${YELLOW}WARNING: Could not verify DAG exists. Proceeding anyway...${NC}"
fi

# Confirmation prompt
echo -e "\n${YELLOW}Pre-flight checks complete!${NC}"
echo -e "\nThis will trigger backfill for 9 seasons:"
echo "  2015-16, 2016-17, 2017-18, 2018-19, 2019-20,"
echo "  2020-21, 2021-22, 2022-23, 2023-24"
echo ""
echo "Each season will process ~1200-1400 games."
echo "Total runtime: 6-12 hours depending on API rate limits."
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted by user"
    exit 0
fi

# Trigger backfill for each season SEQUENTIALLY
SEASONS=("2015-16" "2016-17" "2017-18" "2018-19" "2019-20" "2020-21" "2021-22" "2022-23" "2023-24")

echo -e "\n${GREEN}Starting sequential backfill...${NC}"
echo -e "${YELLOW}Note: Each season will complete before the next starts${NC}"
echo ""

for SEASON in "${SEASONS[@]}"; do
    echo -e "${YELLOW}Triggering backfill for season ${SEASON}...${NC}"

    # Trigger the DAG run
    RUN_OUTPUT=$(docker compose exec -T airflow-scheduler airflow dags trigger nhl_historical_backfill \
        --conf "{\"season\": \"${SEASON}\"}" 2>&1)

    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to trigger ${SEASON}${NC}"
        echo "$RUN_OUTPUT"
        continue
    fi

    # Extract the run_id from the output
    RUN_ID=$(echo "$RUN_OUTPUT" | grep "manual__" | awk '{print $3}' | head -1)

    if [ -z "$RUN_ID" ]; then
        echo -e "${RED}ERROR: Could not determine run ID for ${SEASON}${NC}"
        continue
    fi

    echo -e "${GREEN}✓ ${SEASON} triggered (run: ${RUN_ID})${NC}"
    echo -e "${YELLOW}Waiting for ${SEASON} to complete...${NC}"

    # Poll until the run completes (success or failed)
    while true; do
        STATE=$(docker compose exec -T airflow-scheduler airflow dags list-runs -d nhl_historical_backfill \
            --state running 2>/dev/null | grep "$RUN_ID" | wc -l)

        QUEUED=$(docker compose exec -T airflow-scheduler airflow dags list-runs -d nhl_historical_backfill \
            --state queued 2>/dev/null | grep "$RUN_ID" | wc -l)

        # If not running and not queued, it's done
        if [ "$STATE" -eq 0 ] && [ "$QUEUED" -eq 0 ]; then
            break
        fi

        echo -e "${YELLOW}  ${SEASON} still processing... (checking again in 60s)${NC}"
        sleep 60
    done

    # Check final state
    SUCCESS=$(docker compose exec -T airflow-scheduler airflow dags list-runs -d nhl_historical_backfill \
        --state success 2>/dev/null | grep "$RUN_ID" | wc -l)

    if [ "$SUCCESS" -eq 1 ]; then
        echo -e "${GREEN}✓ ${SEASON} completed successfully!${NC}\n"
    else
        echo -e "${RED}✗ ${SEASON} failed or was stopped${NC}\n"
    fi

    # Small delay before next season
    sleep 5
done

echo -e "\n${GREEN}======================================${NC}"
echo -e "${GREEN}All backfill DAG runs triggered!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Monitor progress:"
echo "  1. Airflow UI: http://$(curl -s ifconfig.me):8080"
echo "  2. Check failures: bq query --nouse_legacy_sql 'SELECT season, COUNT(*) FROM \`nhl-intel-498216.nhl_raw.raw_backfill_failures\` GROUP BY season'"
echo "  3. Watch disk: watch -n 300 df -h"
echo ""
echo -e "${YELLOW}Expected completion: 6-12 hours${NC}"
echo ""
