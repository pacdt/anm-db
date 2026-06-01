#!/bin/bash
set -e

echo "=== anm-db deploy ==="

echo "[1/4] Parando containers..."
docker compose down

echo "[2/4] Atualizando repositorio..."
git pull origin refactor/database-migration

echo "[3/4] Reconstruindo imagens..."
docker compose build --no-cache

echo "[4/4] Subindo containers..."
docker compose up -d

echo ""
echo "=== Deploy concluido ==="
echo "API: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo ""
docker compose ps
