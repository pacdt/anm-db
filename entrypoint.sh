#!/bin/bash
set -e

echo "[entrypoint] Iniciando API..."
python main.py --mode=api &
API_PID=$!

echo "[entrypoint] Iniciando jikan-sync + scraper full em background..."
(
    python main.py --mode=jikan-sync --skip-if-recent=24
    python main.py --mode=full
) &
WORKER_PID=$!

echo "[entrypoint] API rodando (PID=$API_PID), workers (PID=$WORKER_PID)"
wait $API_PID
