#!/bin/bash

# -----------------------------
# Start Python Server Script
# -----------------------------

# Exit on any error
set -e

# Activate virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Virtual environment not found. Please create one first."
    exit 1
fi

# Optional: Set environment variables
# Respect an already-set ENVIRONMENT (e.g. from the deployment's own env/.env);
# only default to development so local runs don't get production's
# Secure+SameSite=None cookie behavior, which Safari rejects over plain HTTP.
export ENVIRONMENT="${ENVIRONMENT:-development}"
export PORT="${PORT:-8000}"

# Start the server
echo "Starting the server..."
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"

# Keep the script running in case of background process (optional)
# nohup python main.py > server.log 2>&1 &
# echo "Server started in background. Logs are in server.log"
