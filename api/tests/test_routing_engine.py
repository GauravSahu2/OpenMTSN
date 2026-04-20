"""Unit tests for the OpenMTSN routing engine.

These tests validate correct failover behaviour across all uplink types
and edge conditions. They are the primary mutation testing target.
"""

from __future__ import annotations

from app.models import TelemetryPayload, UplinkType
from app.routing_engine import (
    _compute_health_score,
    _needs_failover,
    calculate_optimal_route,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Health Score Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestHealthScore:
    """Validate the composite health score computation."""

    def test_perfect_connection(self, healthy_5g_telemetry: TelemetryPayload):
        score = _compute_health_score(healthy_5g_telemetry)
        assert 0.8 <= score <= 1.0, f"Perfect connection should score high, got {score}"

    def test_zero_signal_yields_low_score(self):
        payload = TelemetryPayload(
            node_id="test-0",
            gps=(0, 0),
            uplink=UplinkType.FIVEG,
            signal_strength=0,
            packet_loss=0.0,
            latency_ms=0.0,
        )
        score = _compute_health_score(payload)
        # signal=0 contributes 0 to the 30% weight, but loss=0 and latency=0 are perfect
        assert 0.5 <= score <= 0.75

    def test_total_packet_loss_yields_very_low_score(self):
        payload = TelemetryPayload(
            node_id="test-loss",
            gps=(0, 0),
            uplink=UplinkType.CELLULAR,
            signal_strength=50,
            packet_loss=100.0,
            latency_ms=0.0,
        )
        score = _compute_health_score(payload)
        assert score < 0.5, f"100% packet loss should heavily penalise, got {score}"

    def test_extreme_latency_penalises_score(self):
        payload = TelemetryPayload(
            node_id="test-lat",
            gps=(0, 0),
            uplink=UplinkType.SATELLITE,
            signal_strength=80,
            packet_loss=0.0,
            latency_ms=600.0,  # Beyond 500ms cap
        )
        score = _compute_health_score(payload)
        # latency_score = 0.0 (capped), but signal + loss are good
        assert 0.5 <= score <= 0.8

    def test_score_is_bounded_zero_to_one(self):
        """Score must always be in [0.0, 1.0] regardless of inputs."""
        worst = TelemetryPayload(
            node_id="worst",
            gps=(0, 0),
            uplink=UplinkType.MESH,
            signal_strength=0,
            packet_loss=100.0,
            latency_ms=1000.0,
        )
        best = TelemetryPayload(
            node_id="best",
            gps=(0, 0),
            uplink=UplinkType.FIVEG,
            signal_strength=100,
            packet_loss=0.0,
            latency_ms=0.0,
        )
        assert 0.0 <= _compute_health_score(worst) <= 1.0
        assert 0.0 <= _compute_health_score(best) <= 1.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Failover Threshold Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFailoverThresholds:
    """Validate the hard threshold triggers for failover."""

    def test_normal_conditions_no_failover(self, healthy_5g_telemetry):
        assert _needs_failover(healthy_5g_telemetry) is False

    def test_high_packet_loss_triggers_failover(self, degraded_cellular_telemetry):
        assert _needs_failover(degraded_cellular_telemetry) is True

    def test_low_signal_triggers_failover(self, weak_signal_telemetry):
        assert _needs_failover(weak_signal_telemetry) is True

    def test_boundary_packet_loss_no_failover(self):
        """Exactly at threshold should NOT trigger (> not >=)."""
        payload = TelemetryPayload(
            node_id="boundary",
            gps=(0, 0),
            uplink=UplinkType.FIVEG,
            signal_strength=50,
            packet_loss=15.0,  # Exactly at threshold
            latency_ms=50.0,
        )
        assert _needs_failover(payload) is False

    def test_boundary_signal_no_failover(self):
        """Exactly at threshold should NOT trigger (< not <=)."""
        payload = TelemetryPayload(
            node_id="boundary",
            gps=(0, 0),
            uplink=UplinkType.FIVEG,
            signal_strength=30,  # Exactly at threshold
            packet_loss=5.0,
            latency_ms=50.0,
        )
        assert _needs_failover(payload) is False

    def test_just_above_packet_loss_threshold(self):
        payload = TelemetryPayload(
            node_id="just-above",
            gps=(0, 0),
            uplink=UplinkType.FIVEG,
            signal_strength=50,
            packet_loss=15.1,
            latency_ms=50.0,
        )
        assert _needs_failover(payload) is True

    def test_just_below_signal_threshold(self):
        payload = TelemetryPayload(
            node_id="just-below",
            gps=(0, 0),
            uplink=UplinkType.FIVEG,
            signal_strength=29,
            packet_loss=5.0,
            latency_ms=50.0,
        )
        assert _needs_failover(payload) is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Full Routing Decision Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCalculateOptimalRoute:
    """End-to-end routing decision tests."""

    def test_healthy_5g_stays_on_5g(self, healthy_5g_telemetry):
        decision = calculate_optimal_route("drone-1", healthy_5g_telemetry)
        assert decision.should_failover is False
        assert decision.recommended_uplink == UplinkType.FIVEG
        assert decision.confidence_score > 0.7

    def test_degraded_cellular_fails_to_satellite(self, degraded_cellular_telemetry):
        decision = calculate_optimal_route("relay-7", degraded_cellular_telemetry)
        assert decision.should_failover is True
        assert decision.recommended_uplink == UplinkType.SATELLITE
        assert "satellite" in decision.reason.lower()

    def test_degraded_5g_fails_to_satellite(self, weak_signal_telemetry):
        decision = calculate_optimal_route("sensor-3", weak_signal_telemetry)
        assert decision.should_failover is True
        assert decision.recommended_uplink == UplinkType.SATELLITE

    def test_degraded_satellite_fails_to_mesh(self):
        payload = TelemetryPayload(
            node_id="sat-node",
            gps=(0, 0),
            uplink=UplinkType.SATELLITE,
            signal_strength=15,
            packet_loss=30.0,
            latency_ms=500.0,
        )
        decision = calculate_optimal_route("sat-node", payload)
        assert decision.should_failover is True
        assert decision.recommended_uplink == UplinkType.MESH

    def test_degraded_mesh_stays_on_mesh(self, all_degraded_mesh_telemetry):
        decision = calculate_optimal_route("mesh-node-9", all_degraded_mesh_telemetry)
        assert decision.should_failover is True
        assert decision.recommended_uplink == UplinkType.MESH
        assert "mesh" in decision.reason.lower()

    def test_high_latency_warning_appended(self, high_latency_satellite):
        decision = calculate_optimal_route("sat-relay-2", high_latency_satellite)
        # This node has acceptable loss/signal, so no failover
        assert decision.should_failover is False
        assert "WARN" in decision.reason

    def test_decision_contains_all_fields(self, healthy_5g_telemetry):
        decision = calculate_optimal_route("drone-1", healthy_5g_telemetry)
        assert decision.target_node == "drone-1"
        assert decision.current_uplink == UplinkType.FIVEG
        assert 0.0 <= decision.confidence_score <= 1.0
        assert len(decision.reason) > 0

    def test_failover_confidence_inversely_related_to_health(self):
        """When failover triggers, confidence should be higher for worse health."""
        mild_degradation = TelemetryPayload(
            node_id="mild",
            gps=(0, 0),
            uplink=UplinkType.FIVEG,
            signal_strength=25,  # Just below threshold
            packet_loss=10.0,
            latency_ms=50.0,
        )
        severe_degradation = TelemetryPayload(
            node_id="severe",
            gps=(0, 0),
            uplink=UplinkType.FIVEG,
            signal_strength=5,
            packet_loss=60.0,
            latency_ms=400.0,
        )
        mild_decision = calculate_optimal_route("mild", mild_degradation)
        severe_decision = calculate_optimal_route("severe", severe_degradation)

        assert mild_decision.should_failover is True
        assert severe_decision.should_failover is True
        # Severe should have higher confidence to switch
        assert severe_decision.confidence_score > mild_decision.confidence_score
