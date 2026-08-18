#!/bin/bash
set -e

DATADIR=/data/.bitcoincashII
HOLDING=/holding
CLI="bitcoincashII-cli -rpcconnect=bch2-node -rpcport=8342 -rpcuser=jarvis -rpcpassword=xz8A1Grk9NAKk4l2QerGwCmcwtVoGh62 -datadir=$DATADIR"

echo "=== BCH2 JARVIS Wallet Init ==="

for i in $(seq 1 90); do
  if $CLI getblockchaininfo >/dev/null 2>&1; then
    echo "Node RPC ready"
    break
  fi
  echo "Waiting for node RPC... ($i/90)"
  sleep 3
done

if ! $CLI getblockchaininfo >/dev/null 2>&1; then
  echo "ERROR: Node RPC not reachable after wait"
  exit 1
fi

WALLETS=$($CLI listwallets 2>/dev/null || echo "[]")
if ! echo "$WALLETS" | grep -q "jarvis"; then
  echo "Creating wallet 'jarvis'..."
  $CLI createwallet "jarvis" false false "" false false true 2>/dev/null || \
  $CLI createwallet "jarvis" 2>/dev/null || true
fi

$CLI loadwallet "jarvis" 2>/dev/null || true

CLI_W="$CLI -rpcwallet=jarvis"

mkdir -p "$HOLDING"
if [ -f "$HOLDING/holding_address.txt" ] && [ -s "$HOLDING/holding_address.txt" ]; then
  ADDR=$(cat "$HOLDING/holding_address.txt")
  echo "Existing holding address: $ADDR"
else
  echo "Generating new holding address..."
  ADDR=$($CLI_W getnewaddress "holding" 2>/dev/null || $CLI getnewaddress "holding")
  if [ -z "$ADDR" ]; then
    echo "ERROR: could not generate address"
    exit 1
  fi
  echo "$ADDR" > "$HOLDING/holding_address.txt"
  chmod 644 "$HOLDING/holding_address.txt"
  echo "New holding address created: $ADDR"
fi

cat > "$HOLDING/status.json" <<STATUS
{
  "holding_address": "$ADDR",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "wallet": "jarvis"
}
STATUS

echo "=== Wallet init complete ==="
echo "HOLDING ADDRESS: $ADDR"
exit 0
