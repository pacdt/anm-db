#!/bin/bash
set -e

echo "[entrypoint] 1/3 Jikan sync (metadados + titulos episodios)..."
python main.py --mode=jikan-sync

echo "[entrypoint] 2/3 Scraper full (background)..."
python main.py --mode=full &

echo "[entrypoint] 3/3 Iniciando API..."
python main.py --mode=api
