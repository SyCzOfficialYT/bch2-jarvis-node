#!/bin/bash
set -e

DATADIR=/data/.bitcoincashII
HOLDING=/holding
CLI="bitcoincashII-cli -datadir=$DATADIR -conf=$DATADIR/bitcoincashII.conf"

echo "=== BCH2 JARVIS Wallet Init ==="

# Wait for RPC to be ready
for i in $(seq 1 60); do
  if $CLI getblockchaininfo >/dev/null 2>&1; then
    echo "Node RPC ready"
    break
  fi
  echo "Waiting for node RPC... ($i/60)"
  sleep 3
done

# Create wallet if it doesn't exist
if ! $CLI listwallets 2>/dev/null | grep -q "jarvis"; then
  echo "Creating wallet 'jarvis'..."
  $CLI createwallet "jarvis" false false "" false false true 2>/dev/null || \
  $CLI createwallet "jarvis" 2>/dev/null || true
fi

# Load wallet
$CLI loadwallet "jarvis" 2>/dev/null || true

# Get or create holding address
if [ -f "$HOLDING/holding_address.txt" ]; then
  ADDR=$(cat "$HOLDING/holding_address.txt")
  echo "Existing holding address: $ADDR"
else
  echo "Generating new holding address..."
  ADDR=$($CLI -rpcwallet=jarvis getnewaddress "holding" 2>/dev/null || $CLI getnewaddress "holding")
  echo "$ADDR" > "$HOLDING/holding_address.txt"
  echo "New holding address created: $ADDR"
fi

# Also write a small JSON status
cat > "$HOLDING/status.json" <<EOF
{
  "holding_address": "$ADDR",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "wallet": "jarvis"
}
EOF

echo "=== Wallet init complete ==="
echo "HOLDING ADDRESS: $ADDR"
echo "This is your exchange/withdrawal address."
exit 0
