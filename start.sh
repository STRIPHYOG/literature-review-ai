#!/usr/bin/env bash
set -e

PORT="${PORT:-10000}"
echo "Starting uvicorn on port $PORT..."
if [ -d "backend" ]; then
    cd backend
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
