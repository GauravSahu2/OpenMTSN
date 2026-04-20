"""Shared pytest fixtures for the OpenMTSN API test suite."""

from __future__ import annotations

from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.models import TelemetryPayload, UplinkType
from app.redis_client import RedisTopologyStore


@pytest_asyncio.fixture
async def fake_redis():
    """Provide a fakeredis async instance for tests."""
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield server
    await server.aclose()


@pytest_asyncio.fixture
async def store(fake_redis):
    """Provide a RedisTopologyStore backed by fakeredis."""
    return RedisTopologyStore(fake_redis)


@pytest_asyncio.fixture
async def test_client(fake_redis, monkeypatch):
    """Provide an async httpx test client with fakeredis injected."""
    import app.main as main_module

    original_store = main_module._store
    main_module._store = RedisTopologyStore(fake_redis)

    headers = {"X-MTSN-API-Key": "openmtsn-secret-key-2026"}
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=headers
    ) as client:
        yield client

    main_module._store = original_store


# ── Reusable telemetry fixtures ───────────────────────────


@pytest.fixture
def healthy_5g_telemetry() -> TelemetryPayload:
    """A healthy 5G node — should NOT trigger failover."""
    return TelemetryPayload(
        node_id="drone-1",
        gps=(12.9716, 77.5946),
        uplink=UplinkType.FIVEG,
        signal_strength=85,
        packet_loss=2.0,
        latency_ms=15.0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def degraded_cellular_telemetry() -> TelemetryPayload:
    """A cellular node with high packet loss — should trigger failover to satellite."""
    return TelemetryPayload(
        node_id="relay-7",
        gps=(28.6139, 77.2090),
        uplink=UplinkType.CELLULAR,
        signal_strength=45,
        packet_loss=22.0,
        latency_ms=180.0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def weak_signal_telemetry() -> TelemetryPayload:
    """A node with critically low signal — should trigger failover."""
    return TelemetryPayload(
        node_id="sensor-3",
        gps=(34.0522, -118.2437),
        uplink=UplinkType.FIVEG,
        signal_strength=18,
        packet_loss=8.0,
        latency_ms=90.0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def high_latency_satellite() -> TelemetryPayload:
    """A satellite node with acceptable loss but very high latency."""
    return TelemetryPayload(
        node_id="sat-relay-2",
        gps=(-33.8688, 151.2093),
        uplink=UplinkType.SATELLITE,
        signal_strength=60,
        packet_loss=5.0,
        latency_ms=350.0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def all_degraded_mesh_telemetry() -> TelemetryPayload:
    """A mesh node where everything is bad — should stay on mesh."""
    return TelemetryPayload(
        node_id="mesh-node-9",
        gps=(51.5074, -0.1278),
        uplink=UplinkType.MESH,
        signal_strength=12,
        packet_loss=45.0,
        latency_ms=400.0,
        timestamp=datetime.now(UTC),
    )
