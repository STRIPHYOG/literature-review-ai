#!/usr/bin/env bash
set -e

PORT="${PORT:-10000}"
echo "=================================================="
echo "Starting FastAPI Application on port $PORT"
echo "Working directory: $(pwd)"
echo "Python binary: $(which python || which python3)"
echo "=================================================="

# Ensure we're in the directory that contains 'app'
if [ -d "backend/app" ]; then
    echo "Found backend/app, changing directory to backend..."
    cd backend
fi

# Ensure PYTHONPATH includes the current working directory
export PYTHONPATH=".:$(pwd):${PYTHONPATH}"

# Test import to give clear diagnostic feedback if something is missing
if command -v python &>/dev/null; then
    python -c "import app.main; print('Successfully loaded app.main!')"
    exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
else
    python3 -c "import app.main; print('Successfully loaded app.main!')"
    exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
fi
