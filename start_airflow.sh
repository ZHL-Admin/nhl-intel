#!/bin/bash

# Start Airflow locally for development

export AIRFLOW_HOME=~/airflow
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "Starting Airflow webserver and scheduler..."
echo "Webserver will be available at http://localhost:8080"
echo "Login with admin/admin"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start webserver and scheduler in background
airflow webserver --port 8080 &
WEBSERVER_PID=$!

airflow scheduler &
SCHEDULER_PID=$!

# Trap Ctrl+C to kill both processes
trap "kill $WEBSERVER_PID $SCHEDULER_PID; exit" INT

# Wait for both processes
wait
