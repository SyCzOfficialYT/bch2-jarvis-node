# Bitcoin Cash II Core – binary-based, multi-arch
FROM debian:bookworm-slim

ARG TARGETARCH
ARG VERSION=27.0.2

ENV DEBIAN_FRONTEND=noninteractive
ENV BITCOIN_DATA=/data/.bitcoincashII

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    gosu \
    bash \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r bch2 && useradd -r -g bch2 -d /data -s /bin/bash bch2

# Download architecture-specific binary
RUN set -eux; \
    if [ "$TARGETARCH" = "arm64" ]; then \
      URL="https://github.com/BitcoincashII/bitcoincashII-core/releases/download/v${VERSION}/bitcoincashII-${VERSION}-linux-aarch64.tar.gz"; \
    else \
      URL="https://github.com/BitcoincashII/bitcoincashII-core/releases/download/v${VERSION}/bitcoincashII-${VERSION}-linux64.tar.gz"; \
    fi; \
    echo "Downloading $URL"; \
    wget -qO /tmp/bch2.tar.gz "$URL"; \
    mkdir -p /tmp/extract; \
    tar -xzf /tmp/bch2.tar.gz -C /tmp/extract; \
    find /tmp/extract -type f -name "bitcoincashIId" -exec cp -v {} /usr/local/bin/ \; ; \
    find /tmp/extract -type f -name "bitcoincashII-cli" -exec cp -v {} /usr/local/bin/ \; ; \
    find /tmp/extract -type f -name "bitcoincashII-tx" -exec cp -v {} /usr/local/bin/ \; || true; \
    chmod +x /usr/local/bin/bitcoincashII*; \
    rm -rf /tmp/bch2.tar.gz /tmp/extract; \
    bitcoincashIId --version || bitcoincashIId -version || true

RUN mkdir -p ${BITCOIN_DATA} /holding && chown -R bch2:bch2 /data /holding

COPY entrypoint.sh /entrypoint.sh
COPY init-wallet.sh /init-wallet.sh
RUN chmod +x /entrypoint.sh /init-wallet.sh

VOLUME ["/data/.bitcoincashII", "/holding"]
EXPOSE 8339 8342

# Default user for the node; wallet-init overrides entrypoint as root
USER bch2
WORKDIR /data

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bitcoincashIId", "-datadir=/data/.bitcoincashII", "-printtoconsole"]
