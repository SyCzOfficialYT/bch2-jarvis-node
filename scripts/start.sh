#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== BCH2 JARVIS – production preflight ==="

if [[ ! -f .env ]]; then
  echo "ERROR: .env is missing. Copy .env.example to .env and set RPC_PASSWORD." >&2
  exit 1
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

docker compose config >/dev/null
docker compose up -d --build

echo
echo "=== Status ==="
docker compose ps
echo
echo "Dashboard : http://localhost:3080"
echo "Stratum   : <SERVER-IP>:3333"
echo "Stats     : http://<SERVER-IP>:8080/health"
echo "=== JARVIS online ==="
