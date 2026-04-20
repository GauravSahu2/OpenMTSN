import pytest

from app.models import TelemetryPayload, UplinkType
from app.routing_engine import calculate_optimal_route

# ── Security Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_telemetry_unauthorized_without_key(test_client):
    payload = {
        "node_id": "test-node",
        "gps": [0, 0],
        "uplink": "5g",
        "signal_strength": 80,
        "packet_loss": 0,
        "latency_ms": 50,
        "timestamp": "2026-01-01T00:00:00Z",
    }
    # Create a fresh client WITHOUT the default API key headers from conftest
    from httpx import ASGITransport, AsyncClient

    import app.main as main_module
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/telemetry", json=payload)
    assert response.status_code == 403
    assert "invalid X-MTSN-API-Key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_telemetry_authorized_with_key(test_client):
    payload = {
        "node_id": "test-node",
        "gps": [0, 0],
        "uplink": "5g",
        "signal_strength": 80,
        "packet_loss": 0,
        "latency_ms": 50,
        "timestamp": "2026-01-01T00:00:00Z",
    }
    headers = {"X-MTSN-API-Key": "openmtsn-secret-key-2026"}
    response = await test_client.post("/telemetry", json=payload, headers=headers)
    assert response.status_code == 201


# ── Hysteresis (Moving Average) Tests ─────────────────────


def test_hysteresis_prevents_flapping():
    """Verify that a single bad sample doesn't trigger failover if history is good."""
    payload = TelemetryPayload(
        node_id="flaky-node",
        gps=[0, 0],
        uplink=UplinkType.FIVEG,
        signal_strength=25,  # Just below threshold (30)
        packet_loss=5.0,
        latency_ms=50.0,
    )

    # 1. Test WITHOUT history (instant failover)
    decision_no_hist = calculate_optimal_route("flaky-node", payload, history=None)
    assert decision_no_hist.should_failover is True

    # 2. Test WITH healthy history (should NOT failover yet)
    # History of perfect scores [1.0, 1.0, 1.0]
    # Current health for signal=25 is roughly 0.65 ? (0.3*0.25 + 0.4*0.95 + 0.3*0.9)
    # Average of [1.0, 1.0, 0.65] is ~0.88, which is > 0.4 threshold
    decision_with_hist = calculate_optimal_route("flaky-node", payload, history=[1.0, 1.0])
    assert decision_with_hist.should_failover is False
    assert "stable" in decision_with_hist.reason.lower()


def test_critical_failure_triggers_instantly_despite_history():
    """Verify that high packet loss triggers failover immediately."""
    payload = TelemetryPayload(
        node_id="dead-node",
        gps=[0, 0],
        uplink=UplinkType.FIVEG,
        signal_strength=80,
        packet_loss=60.0,  # Critical failure (>50%)
        latency_ms=50.0,
    )

    # Even with perfect history, 60% loss should trigger failover
    decision = calculate_optimal_route("dead-node", payload, history=[1.0, 1.0])
    assert decision.should_failover is True
