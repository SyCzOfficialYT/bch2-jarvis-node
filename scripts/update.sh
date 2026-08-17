#!/bin/bash
# Zero-manual update path: git pull + rebuild
set -e
cd "$(dirname "$0")/.."

echo "▶ Pulling latest…"
git pull --ff-only

echo "▶ Rebuilding containers…"
docker compose pull || true
docker compose up -d --build --remove-orphans

echo "▶ Done. Dashboard → http://localhost:3080"
docker compose ps
