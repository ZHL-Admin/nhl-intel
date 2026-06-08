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

# Pre-flight checks
echo -e "${YELLOW}Running pre-flight checks...${NC}"

# 1. Check disk space
echo -e "\n${YELLOW}1. Checking disk space...${NC}"
AVAILABLE_GB=$(df -h / | awk 'NR==2 {print $4}' | sed 's/G//')
echo "Available space: ${AVAILABLE_GB}GB"

if (( $(echo "$AVAILABLE_GB < 15" | bc -l) )); then
    echo -e "${RED}ERROR: Less than 15GB available. Aborting.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Disk space check passed${NC}"

# 2. Check Docker containers
echo -e "\n${YELLOW}2. Checking Docker containers...${NC}"
cd /opt/nhl-intel || { echo -e "${RED}ERROR: Cannot cd to /opt/nhl-intel${NC}"; exit 1; }

UNHEALTHY=$(docker compose ps | grep -v "healthy" | grep -c "Up" || true)
if [ "$UNHEALTHY" -gt 0 ]; then
    echo -e "${RED}ERROR: Some containers are not healthy${NC}"
    docker compose ps
    exit 1
fi
echo -e "${GREEN}✓ All containers healthy${NC}"

# 3. Verify backfill DAG exists
echo -e "\n${YELLOW}3. Verifying backfill DAG exists...${NC}"
if docker compose exec -T airflow-webserver airflow dags list | grep -q "nhl_historical_backfill"; then
    echo -e "${GREEN}✓ Backfill DAG found${NC}"
else
    echo -e "${RED}ERROR: Backfill DAG not found. Did you pull latest code and restart?${NC}"
    exit 1
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

# Trigger backfill for each season
SEASONS=("2015-16" "2016-17" "2017-18" "2018-19" "2019-20" "2020-21" "2021-22" "2022-23" "2023-24")

echo -e "\n${GREEN}Starting backfill triggers...${NC}"
echo ""

for SEASON in "${SEASONS[@]}"; do
    echo -e "${YELLOW}Triggering backfill for season ${SEASON}...${NC}"

    docker compose exec -T airflow-scheduler airflow dags trigger nhl_historical_backfill \
        --conf "{\"season\": \"${SEASON}\"}" \
        2>&1 | grep -i "created\|triggered" || {
            echo -e "${RED}WARNING: Failed to trigger ${SEASON}${NC}"
            continue
        }

    echo -e "${GREEN}✓ ${SEASON} triggered${NC}"

    # Small delay to avoid overwhelming the scheduler
    sleep 2
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
