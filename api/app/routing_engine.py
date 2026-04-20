"""Core routing engine for OpenMTSN.

Evaluates telemetry data to determine when a node must switch from a degraded
uplink to a healthier alternative — ensuring zero-drop handoffs for
life-saving data.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import settings
from app.models import RouteDecision, TelemetryPayload, UplinkType

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Weight matrix for the composite health score ──────────
# Packet loss is the highest-weighted factor because dropped
# packets directly endanger life-saving telemetry.
WEIGHT_SIGNAL: float = 0.30
WEIGHT_PACKET_LOSS: float = 0.40
WEIGHT_LATENCY: float = 0.30

# ── Priority cascade (ordered by bandwidth for ideal conditions) ──
UPLINK_PRIORITY: list[UplinkType] = [
    UplinkType.FIVEG,
    UplinkType.CELLULAR,
    UplinkType.SATELLITE,
    UplinkType.MESH,
]


def _compute_health_score(telemetry: TelemetryPayload) -> float:
    """Compute a normalised health score ∈ [0.0, 1.0] for the current uplink.

    A score of 1.0 represents a perfect connection; 0.0 is unusable.

    Scoring methodology:
      • signal_strength: Normalised from 0-100 -> 0.0-1.0
      • packet_loss: Inverted (0% loss -> 1.0, 100% loss -> 0.0)
      • latency_ms: Mapped through a decay function capped at 500ms
    """
    signal_score = telemetry.signal_strength / 100.0
    loss_score = 1.0 - (telemetry.packet_loss / 100.0)
    latency_score = max(0.0, 1.0 - (telemetry.latency_ms / 500.0))

    composite = (
        WEIGHT_SIGNAL * signal_score
        + WEIGHT_PACKET_LOSS * loss_score
        + WEIGHT_LATENCY * latency_score
    )
    return round(min(max(composite, 0.0), 1.0), 4)


def _needs_failover(telemetry: TelemetryPayload) -> bool:
    """Determine whether telemetry values breach critical thresholds."""
    return (
        telemetry.packet_loss > settings.PACKET_LOSS_FAILOVER_THRESHOLD
        or telemetry.signal_strength < settings.SIGNAL_STRENGTH_FAILOVER_THRESHOLD
    )


def _select_best_uplink(
    current: UplinkType,
    telemetry: TelemetryPayload,
) -> tuple[UplinkType, str]:
    """Select the best available uplink when the current one is degraded.

    Strategy:
      1. Walk the priority cascade, skipping the current (failing) uplink.
      2. If the current uplink is cellular or 5G (both terrestrial),
         prefer satellite first for geographic diversity.
      3. If all higher-priority options are the same type, fall back to mesh
         which guarantees local peer connectivity.
    """
    # When 5G/cellular are both degraded, satellite gives geographic diversity
    terrestrial = {UplinkType.FIVEG, UplinkType.CELLULAR}

    if current in terrestrial:
        # Satellite provides the best diversity from terrestrial failures
        return (
            UplinkType.SATELLITE,
            f"Terrestrial uplink '{current.value}' degraded — failing over to satellite "
            f"(packet_loss={telemetry.packet_loss}%, signal={telemetry.signal_strength}%)",
        )

    if current == UplinkType.SATELLITE:
        return (
            UplinkType.MESH,
            f"Satellite uplink degraded — failing over to local mesh relay "
            f"(packet_loss={telemetry.packet_loss}%, signal={telemetry.signal_strength}%)",
        )

    # Already on mesh — nowhere else to go, stay on mesh (most resilient)
    return (
        UplinkType.MESH,
        f"All uplinks degraded — remaining on mesh as most-resilient fallback "
        f"(packet_loss={telemetry.packet_loss}%, signal={telemetry.signal_strength}%)",
    )


def calculate_optimal_route(
    node_id: str,
    telemetry_data: TelemetryPayload,
    history: list[float] | None = None,
) -> RouteDecision:
    """Evaluate telemetry and return the optimal routing decision.

    This version uses a moving average (hysteresis) if history is provided
    to prevent rapid switching (flapping) between uplinks.
    """
    current_health = _compute_health_score(telemetry_data)

    # Use moving average if history exists
    if history:
        # window size is len(history) + 1 (current)
        avg_health = (sum(history) + current_health) / (len(history) + 1)
        effective_health = round(avg_health, 4)
    else:
        effective_health = current_health

    # Failover trigger uses the EFFECTIVE (averaged) health to check thresholds
    # but hard failures (packet loss > 50%) should still trigger instantly
    is_critical_failure = telemetry_data.packet_loss > 50.0
    history_threshold = effective_health < 0.4 or is_critical_failure
    should_failover = _needs_failover(telemetry_data) if not history else history_threshold

    if should_failover:
        recommended_uplink, reason = _select_best_uplink(telemetry_data.uplink, telemetry_data)
        confidence = round(1.0 - effective_health, 4)
        logger.warning(
            "FAILOVER node=%s | %s → %s | health=%.4f (inst=%.4f) | %s",
            node_id,
            telemetry_data.uplink.value,
            recommended_uplink.value,
            effective_health,
            current_health,
            reason,
        )
    else:
        recommended_uplink = telemetry_data.uplink
        confidence = effective_health
        reason = (
            f"Uplink '{telemetry_data.uplink.value}' stable — no action required "
            f"(avg_health={effective_health}, current={current_health})"
        )
        logger.info(
            "STABLE   node=%s | %s | health=%.4f",
            node_id,
            telemetry_data.uplink.value,
            effective_health,
        )

    # Check for latency warning (informational)
    lat_warn = telemetry_data.latency_ms > settings.LATENCY_WARNING_THRESHOLD_MS
    if lat_warn and not should_failover:
        reason += f" [WARN: latency {telemetry_data.latency_ms}ms over threshold]"

    return RouteDecision(
        target_node=node_id,
        current_uplink=telemetry_data.uplink,
        recommended_uplink=recommended_uplink,
        should_failover=should_failover,
        reason=reason,
        confidence_score=confidence,
    )


def compute_health_score(telemetry: TelemetryPayload) -> float:
    """Public wrapper for the health score computation ∈ [0.0, 1.0]."""
    return _compute_health_score(telemetry)
