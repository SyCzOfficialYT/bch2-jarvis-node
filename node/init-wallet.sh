#!/usr/bin/env bash
set -euo pipefail

DATADIR=/data/.bitcoincashII
HOLDING=/holding
: "${RPC_USER:?RPC_USER is required}"
: "${RPC_PASSWORD:?RPC_PASSWORD is required}"
RPC_WALLET="${RPC_WALLET:-jarvis}"
CLI=(bitcoincashII-cli -rpcconnect=bch2-node -rpcport=8342 -rpcuser="$RPC_USER" -rpcpassword="$RPC_PASSWORD" -datadir="$DATADIR")

wait_for_rpc() {
  for i in $(seq 1 90); do
    if "${CLI[@]}" getblockchaininfo >/dev/null 2>&1; then
      echo "Node RPC ready"
      return 0
    fi
    echo "Waiting for node RPC... ($i/90)"
    sleep 3
  done
  echo "ERROR: Node RPC not reachable after wait" >&2
  return 1
}

create_or_load_wallet() {
  local wallets
  wallets=$("${CLI[@]}" listwallets 2>/dev/null || printf '[]')
  if ! grep -q '"'"${RPC_WALLET}"'"' <<<"$wallets"; then
    echo "Creating wallet '$RPC_WALLET'..."
    "${CLI[@]}" createwallet "$RPC_WALLET" >/dev/null
  fi
  "${CLI[@]}" loadwallet "$RPC_WALLET" >/dev/null 2>&1 || true
}

wait_for_rpc
create_or_load_wallet

CLI_W=("${CLI[@]}" "-rpcwallet=$RPC_WALLET")
mkdir -p "$HOLDING"

if [[ -s "$HOLDING/holding_address.txt" ]]; then
  ADDR=$(<"$HOLDING/holding_address.txt")
  echo "Existing holding address: $ADDR"
else
  echo "Generating new holding address..."
  ADDR=$("${CLI_W[@]}" getnewaddress holding)
  [[ -n "$ADDR" ]] || { echo "ERROR: could not generate address" >&2; exit 1; }
  printf '%s\n' "$ADDR" > "$HOLDING/holding_address.txt"
  chmod 644 "$HOLDING/holding_address.txt"
  echo "New holding address created: $ADDR"
fi

INFO=$("${CLI_W[@]}" getaddressinfo "$ADDR")
printf '%s\n' "$INFO" | grep -q '"scriptPubKey"' || { echo "ERROR: holding address has no scriptPubKey" >&2; exit 1; }

cat > "$HOLDING/status.json" <<STATUS
{
  "holding_address": "${ADDR}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "wallet": "${RPC_WALLET}"
}
STATUS

echo "=== Wallet init complete ==="
echo "HOLDING ADDRESS: $ADDR"
