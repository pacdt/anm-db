#!/bin/bash
set -e

echo "[entrypoint] Iniciando API..."
python main.py --mode=api &
API_PID=$!

echo "[entrypoint] Iniciando scraper full + jikan-sync + backfill em background..."
(
    python main.py --mode=full
    python main.py --mode=jikan-sync --skip-if-recent=24
    python main.py --mode=backfill-skip-times --skip-if-recent=24
) &
WORKER_PID=$!

echo "[entrypoint] API rodando (PID=$API_PID), workers (PID=$WORKER_PID)"
wait $API_PID
