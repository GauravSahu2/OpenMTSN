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
      • signal_strength: Directly normalised from 0–100 → 0.0–1.0
      • packet_loss: Inverted (0 % loss → 1.0, 100 % loss → 0.0)
      • latency_ms: Mapped through a decay function capped at 500 ms
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
    if telemetry.packet_loss > settings.PACKET_LOSS_FAILOVER_THRESHOLD:
        return True
    if telemetry.signal_strength < settings.SIGNAL_STRENGTH_FAILOVER_THRESHOLD:
        return True
    return False


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
) -> RouteDecision:
    """Evaluate telemetry and return the optimal routing decision.

    This is the core function that the control plane invokes on every
    telemetry ingestion. It:
      1. Computes a composite health score for the current uplink.
      2. Checks hard thresholds for immediate failover triggers.
      3. Selects the best alternative uplink when failover is needed.
      4. Returns a ``RouteDecision`` with a confidence score and reason.
    """
    health_score = _compute_health_score(telemetry_data)
    should_failover = _needs_failover(telemetry_data)

    if should_failover:
        recommended_uplink, reason = _select_best_uplink(
            telemetry_data.uplink, telemetry_data
        )
        confidence = round(1.0 - health_score, 4)  # Higher confidence to switch when health is low
        logger.warning(
            "FAILOVER node=%s | %s → %s | health=%.4f | %s",
            node_id,
            telemetry_data.uplink.value,
            recommended_uplink.value,
            health_score,
            reason,
        )
    else:
        recommended_uplink = telemetry_data.uplink
        confidence = health_score
        reason = (
            f"Uplink '{telemetry_data.uplink.value}' healthy — no action required "
            f"(health_score={health_score}, signal={telemetry_data.signal_strength}%, "
            f"packet_loss={telemetry_data.packet_loss}%, latency={telemetry_data.latency_ms}ms)"
        )
        logger.info(
            "STABLE   node=%s | %s | health=%.4f",
            node_id,
            telemetry_data.uplink.value,
            health_score,
        )

    # Check for latency warning (informational)
    if telemetry_data.latency_ms > settings.LATENCY_WARNING_THRESHOLD_MS and not should_failover:
        reason += f" [WARN: latency {telemetry_data.latency_ms}ms exceeds {settings.LATENCY_WARNING_THRESHOLD_MS}ms threshold]"

    return RouteDecision(
        target_node=node_id,
        current_uplink=telemetry_data.uplink,
        recommended_uplink=recommended_uplink,
        should_failover=should_failover,
        reason=reason,
        confidence_score=confidence,
    )
