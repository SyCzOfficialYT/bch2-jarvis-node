# Bitcoin Cash II Core – binary + full runtime libs
FROM debian:bookworm-slim

ARG VERSION=27.0.2

ENV DEBIAN_FRONTEND=noninteractive
ENV BITCOIN_DATA=/data/.bitcoincashII

# ALL runtime libs the release binary typically needs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    gosu \
    bash \
    libminiupnpc17 \
    libnatpmp1 \
    libevent-2.1-7 \
    libevent-pthreads-2.1-7 \
    libboost-system1.74.0 \
    libboost-filesystem1.74.0 \
    libboost-thread1.74.0 \
    libboost-chrono1.74.0 \
    libboost-program-options1.74.0 \
    libdb5.3++ \
    libsqlite3-0 \
    libssl3 \
    libstdc++6 \
    libzmq5 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && ls -la /usr/lib/*/libnatpmp.so* /usr/lib/*/libminiupnpc.so* || true

RUN groupadd -r bch2 && useradd -r -g bch2 -d /data -s /bin/bash bch2

RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      aarch64|arm64) \
        URL="https://github.com/BitcoincashII/bitcoincashII-core/releases/download/v${VERSION}/bitcoincashII-${VERSION}-linux-aarch64.tar.gz" ;; \
      x86_64|amd64) \
        URL="https://github.com/BitcoincashII/bitcoincashII-core/releases/download/v${VERSION}/bitcoincashII-${VERSION}-linux64.tar.gz" ;; \
      *) \
        echo "Unsupported arch: $ARCH"; exit 1 ;; \
    esac; \
    echo "Downloading $URL"; \
    wget -qO /tmp/bch2.tar.gz "$URL"; \
    mkdir -p /tmp/extract; \
    tar -xzf /tmp/bch2.tar.gz -C /tmp/extract; \
    find /tmp/extract -type f -name "bitcoincashIId" -exec cp -v {} /usr/local/bin/ \; ; \
    find /tmp/extract -type f -name "bitcoincashII-cli" -exec cp -v {} /usr/local/bin/ \; ; \
    find /tmp/extract -type f -name "bitcoincashII-tx" -exec cp -v {} /usr/local/bin/ \; || true; \
    chmod +x /usr/local/bin/bitcoincashII*; \
    rm -rf /tmp/bch2.tar.gz /tmp/extract; \
    echo "=== ldd bitcoincashIId ==="; \
    ldd /usr/local/bin/bitcoincashIId || true; \
    echo "=== version ==="; \
    bitcoincashIId --version || bitcoincashIId -version || true

RUN mkdir -p ${BITCOIN_DATA} /holding && chown -R bch2:bch2 /data /holding

COPY entrypoint.sh /entrypoint.sh
COPY init-wallet.sh /init-wallet.sh
RUN chmod +x /entrypoint.sh /init-wallet.sh

VOLUME ["/data/.bitcoincashII", "/holding"]
EXPOSE 8339 8342

USER bch2
WORKDIR /data

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bitcoincashIId", "-datadir=/data/.bitcoincashII", "-printtoconsole"]
