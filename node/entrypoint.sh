#!/bin/bash
set -e

# Ensure data dir exists and has correct permissions (in case volume is mounted as root)
if [ "$(id -u)" = "0" ]; then
  chown -R bch2:bch2 /data
  exec gosu bch2 "$0" "$@"
fi

# Wait a moment for volume
mkdir -p /data/.bitcoincashII

# If conf is missing (should be mounted), create a minimal one
if [ ! -f /data/.bitcoincashII/bitcoincashII.conf ]; then
  cat > /data/.bitcoincashII/bitcoincashII.conf <<EOF
# Auto-generated minimal config - override via volume mount
server=1
listen=1
daemon=0
rpcuser=jarvis
rpcpassword=xz8A1Grk9NAKk4l2QerGwCmcwtVoGh62
rpcallowip=0.0.0.0/0
rpcbind=0.0.0.0
port=8339
rpcport=8342
txindex=1
dbcache=1024
maxmempool=500
EOF
fi

exec "$@"
