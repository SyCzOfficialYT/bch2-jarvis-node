#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== BCH2 JARVIS – Docker production start ==="

if [[ ! -f .env ]]; then
  echo "Creating .env with a fresh RPC password..."
  if command -v openssl >/dev/null 2>&1; then
    RPC_PASSWORD="$(openssl rand -hex 32)"
  else
    RPC_PASSWORD="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  fi
  {
    echo "RPC_USER=jarvis"
    echo "RPC_PASSWORD=${RPC_PASSWORD}"
    echo "RPC_WALLET=jarvis"
    echo "START_DIFF=8192"
    echo "JOB_REFRESH_SECONDS=5"
    echo "POOL_TAG=/BCH2-JARVIS/"
  } > .env
  chmod 600 .env
  echo ".env created. RPC credentials are stored locally in .env."
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${RPC_USER:?RPC_USER is required}"
: "${RPC_PASSWORD:?RPC_PASSWORD is required}"

if [[ "${RPC_PASSWORD}" == "CHANGE_ME_TO_A_LONG_RANDOM_SECRET" ]]; then
  echo "ERROR: RPC_PASSWORD is still the example value." >&2
  exit 1
fi

echo "Validating Docker Compose..."
sudo docker compose config --quiet

echo "Building containers..."
sudo docker compose build --pull

echo "Starting pool..."
sudo docker compose up -d

echo
sudo docker compose ps
echo
echo "Dashboard: http://localhost:3080"
echo "Stratum:   <SERVER-IP>:3333"
echo "Stats:     http://<SERVER-IP>:8080/health"
echo "Logs:      sudo docker compose logs -f stratum-proxy"
echo "=== JARVIS online ==="
