#!/bin/bash
set -e

echo "[entrypoint] Iniciando scraper full em background..."
python main.py --mode=full &

echo "[entrypoint] Iniciando API..."
python main.py --mode=api
