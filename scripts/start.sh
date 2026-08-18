#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== BCH2 JARVIS – preflight & start ==="

free_port() {
  local port="$1"
  if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
    echo "Port ${port} belegt – stoppe Docker-Container..."
    ids=$(docker ps -q --filter "publish=${port}" 2>/dev/null || true)
    if [ -n "${ids}" ]; then
      docker stop ${ids} 2>/dev/null || true
      docker rm -f ${ids} 2>/dev/null || true
      echo "  Container auf Port ${port} gestoppt."
    else
      echo "  WARN: Port ${port} belegt ohne Docker-Container."
      echo "  sudo ss -tlnp | grep ${port}"
    fi
  else
    echo "Port ${port} frei."
  fi
}

free_port 3333
free_port 8080

docker compose down --remove-orphans 2>/dev/null || true

docker compose run --rm --user 0:0 --no-deps --entrypoint /bin/bash bch2-node \
  -c 'mkdir -p /holding && chmod -R 777 /holding 2>/dev/null || true' || true

echo "Starte Node..."
docker compose up -d bch2-node
echo "Warte auf healthy Node..."
for i in $(seq 1 60); do
  st=$(docker inspect -f '{{.State.Health.Status}}' bch2-jarvis-node 2>/dev/null || echo starting)
  if [ "$st" = "healthy" ]; then
    echo "Node healthy."
    break
  fi
  sleep 3
done

echo "Wallet-Init..."
docker compose run --rm --user 0:0 wallet-init || true

echo "Starte Stratum + Dashboard..."
docker compose up -d --build stratum-proxy dashboard-backend dashboard-frontend

sleep 4
echo ""
echo "=== Status ==="
docker compose ps
echo ""
echo "Dashboard: http://localhost:3080"
echo "Stratum:   <IP>:3333  User: <holding>.worker1  Pass: x"
echo "=== fertig ==="
