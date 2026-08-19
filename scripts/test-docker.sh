#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== BCH2 JARVIS – Docker test ==="

sudo docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  python:3.14-slim \
  bash -lc '
    set -euo pipefail
    python --version
    python -m pip install --no-cache-dir \
      -r stratum-proxy/requirements.txt \
      -r dashboard/backend/requirements.txt \
      pytest
    python -m py_compile stratum-proxy/proxy.py dashboard/backend/main.py
    python -m pytest -q tests
  '

echo "=== Docker tests passed ==="
