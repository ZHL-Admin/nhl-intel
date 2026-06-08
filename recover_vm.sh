#!/bin/bash
# Recovery script for frozen Airflow VM
# Run this on the VM when Docker network issues occur

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Airflow VM Recovery Script${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

# Get to the project directory
cd ~/NIR

echo -e "${YELLOW}1. Checking current container status...${NC}"
docker compose ps
echo ""

echo -e "${YELLOW}2. Stopping all containers gracefully...${NC}"
docker compose down --timeout 30

echo -e "${GREEN}✓ Containers stopped${NC}"
echo ""

echo -e "${YELLOW}3. Checking system resources...${NC}"
echo "Memory:"
free -h
echo ""
echo "Disk:"
df -h /
echo ""

# Check if we're low on memory
AVAILABLE_MEM=$(free -m | awk 'NR==2 {print $7}')
if [ "$AVAILABLE_MEM" -lt 500 ]; then
    echo -e "${RED}WARNING: Less than 500MB available memory${NC}"
    echo -e "${YELLOW}Clearing system cache...${NC}"
    sudo sync
    sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
    echo -e "${GREEN}✓ Cache cleared${NC}"
    echo ""
fi

echo -e "${YELLOW}4. Starting containers...${NC}"
docker compose up -d

echo -e "${GREEN}✓ Containers started${NC}"
echo ""

echo -e "${YELLOW}5. Waiting for Airflow to be ready (30 seconds)...${NC}"
sleep 30

echo -e "${YELLOW}6. Checking container health...${NC}"
docker compose ps
echo ""

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Recovery complete!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Check Airflow UI: http://\$(curl -s ifconfig.me):8080"
echo "  2. Review any failed DAG runs and clear them if needed"
echo "  3. Re-run trigger_full_backfill.sh with BATCH_SIZE=1"
echo ""
echo -e "${YELLOW}Note: The backfill script has been updated to run 1 season at a time${NC}"
echo ""
