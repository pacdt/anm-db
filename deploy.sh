#!/bin/bash
set -e

echo "=== anm-db deploy ==="

echo "[1/5] Parando containers..."
docker compose down

echo "[2/5] Removendo container nginx orfao (se existir)..."
docker stop anm_nginx 2>/dev/null || true
docker rm anm_nginx 2>/dev/null || true

echo "[3/5] Atualizando repositorio..."
git pull --rebase origin refactor/database-migration

echo "[4/5] Reconstruindo imagens..."
docker compose build --no-cache

echo "[5/5] Subindo containers..."
docker compose up -d

echo ""
echo "=== Deploy concluido ==="
echo "API (direto): http://localhost:8000"
echo "API (nginx):  http://localhost:3000"
echo "Docs:         http://localhost:8000/docs"
echo ""
docker compose ps
