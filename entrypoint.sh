#!/bin/bash
set -e

echo "[entrypoint] 1/4 Jikan sync (metadados + titulos episodios)..."
python main.py --mode=jikan-sync

echo "[entrypoint] 2/4 Scraper full (CDN + Animefire)..."
python main.py --mode=full

echo "[entrypoint] 3/4 Backfill skip_times (Aniskip)..."
python main.py --mode=backfill-skip-times

echo "[entrypoint] 4/4 Iniciando API..."
python main.py --mode=api
