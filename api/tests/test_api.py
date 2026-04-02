"""Integration tests for the OpenMTSN FastAPI endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Test the /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, test_client: AsyncClient):
        resp = await test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["redis"] is True


class TestTelemetryEndpoint:
    """Test the POST /telemetry endpoint."""

    @pytest.mark.asyncio
    async def test_ingest_valid_telemetry(self, test_client: AsyncClient):
        payload = {
            "node_id": "drone-1",
            "gps": [12.9716, 77.5946],
            "uplink": "5g",
            "signal_strength": 85,
            "packet_loss": 2.0,
            "latency_ms": 15.0,
        }
        resp = await test_client.post("/telemetry", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["target_node"] == "drone-1"
        assert data["should_failover"] is False
        assert data["recommended_uplink"] == "5g"

    @pytest.mark.asyncio
    async def test_ingest_degraded_triggers_failover(self, test_client: AsyncClient):
        payload = {
            "node_id": "relay-7",
            "gps": [28.6139, 77.209],
            "uplink": "cellular",
            "signal_strength": 20,
            "packet_loss": 40.0,
            "latency_ms": 300.0,
        }
        resp = await test_client.post("/telemetry", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["should_failover"] is True
        assert data["recommended_uplink"] == "satellite"

    @pytest.mark.asyncio
    async def test_ingest_invalid_payload_422(self, test_client: AsyncClient):
        resp = await test_client.post("/telemetry", json={"node_id": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ingest_invalid_gps_422(self, test_client: AsyncClient):
        payload = {
            "node_id": "bad-gps",
            "gps": [999.0, 0.0],
            "uplink": "5g",
            "signal_strength": 50,
            "packet_loss": 5.0,
            "latency_ms": 10.0,
        }
        resp = await test_client.post("/telemetry", json=payload)
        assert resp.status_code == 422


class TestTopologyEndpoint:
    """Test the GET /topology endpoint."""

    @pytest.mark.asyncio
    async def test_empty_topology(self, test_client: AsyncClient):
        resp = await test_client.get("/topology")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"] == []
        assert data["total_healthy"] == 0

    @pytest.mark.asyncio
    async def test_topology_after_ingestion(self, test_client: AsyncClient):
        # Ingest a node first
        await test_client.post(
            "/telemetry",
            json={
                "node_id": "alpha",
                "gps": [10.0, 20.0],
                "uplink": "satellite",
                "signal_strength": 70,
                "packet_loss": 3.0,
                "latency_ms": 120.0,
            },
        )
        resp = await test_client.get("/topology")
        data = resp.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["node_id"] == "alpha"
        assert data["total_healthy"] == 1


class TestRouteEndpoint:
    """Test the GET /route/{node_id} endpoint."""

    @pytest.mark.asyncio
    async def test_route_unknown_node_404(self, test_client: AsyncClient):
        resp = await test_client.get("/route/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_route_for_known_node(self, test_client: AsyncClient):
        # Ingest first
        await test_client.post(
            "/telemetry",
            json={
                "node_id": "beta",
                "gps": [30.0, 40.0],
                "uplink": "5g",
                "signal_strength": 90,
                "packet_loss": 1.0,
                "latency_ms": 8.0,
            },
        )
        resp = await test_client.get("/route/beta")
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_node"] == "beta"
        assert data["recommended_uplink"] == "5g"
        assert data["should_failover"] is False
