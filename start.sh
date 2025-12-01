#!/bin/bash

# Activate virtual environment (optional but recommended)
source venv/bin/activate

# Run the production server
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info
