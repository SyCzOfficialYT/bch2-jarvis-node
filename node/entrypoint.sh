#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" == "0" ]]; then
  chown -R bch2:bch2 /data /holding
  exec gosu bch2 "$0" "$@"
fi

: "${RPC_USER:?RPC_USER is required}"
: "${RPC_PASSWORD:?RPC_PASSWORD is required}"

DATADIR=/data/.bitcoincashII
RUNTIME_CONF="$DATADIR/runtime.conf"
mkdir -p "$DATADIR" /holding

cat > "$RUNTIME_CONF" <<EOF
server=1
daemon=0
listen=1
port=8339
maxconnections=64
dnsseed=1

rpcuser=${RPC_USER}
rpcpassword=${RPC_PASSWORD}
rpcport=8342
rpcbind=0.0.0.0
rpcallowip=172.16.0.0/12

# Pool/node performance
\dbcache=1024
maxmempool=400
mempoolexpiry=72

txindex=1
blockfilterindex=1
disablewallet=0
printtoconsole=1
logtimestamps=1
EOF
chmod 600 "$RUNTIME_CONF"

exec "$@"
