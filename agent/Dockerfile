# ── Stage 1: Build ────────────────────────────────────────
FROM rust:latest AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
COPY Cargo.toml .
COPY src/ ./src/
RUN cargo build --release

# ── Stage 2: Runtime ─────────────────────────────────────
FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="OpenMTSN Edge Agent"

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r mtsn && useradd -r -g mtsn mtsn && \
    mkdir -p /app/data && chown -R mtsn:mtsn /app

WORKDIR /app
COPY --from=builder /build/target/release/openmtsn-agent .

USER mtsn

ENV MTSN_NODE_ID="agent-001"
ENV MTSN_MQTT_HOST="mqtt-broker"
ENV MTSN_MQTT_PORT="1883"
ENV MTSN_GPS_LAT="12.9716"
ENV MTSN_GPS_LON="77.5946"

CMD ["./openmtsn-agent"]
