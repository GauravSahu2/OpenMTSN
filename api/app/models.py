"""Pydantic v2 models for OpenMTSN telemetry and routing decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class UplinkType(str, Enum):
    """Supported uplink transport types."""

    FIVEG = "5g"
    SATELLITE = "satellite"
    MESH = "mesh"
    CELLULAR = "cellular"


class TelemetryPayload(BaseModel):
    """Telemetry packet ingested from an edge agent."""

    node_id: Annotated[str, Field(min_length=1, max_length=64, description="Unique node identifier")]
    gps: Annotated[
        tuple[float, float],
        Field(description="GPS coordinates (latitude, longitude)"),
    ]
    uplink: UplinkType
    signal_strength: Annotated[
        int,
        Field(ge=0, le=100, description="Signal strength percentage"),
    ]
    packet_loss: Annotated[
        float,
        Field(ge=0.0, le=100.0, description="Packet loss percentage"),
    ]
    latency_ms: Annotated[
        float,
        Field(ge=0.0, description="Round-trip latency in milliseconds"),
    ]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("gps")
    @classmethod
    def validate_gps_range(cls, v: tuple[float, float]) -> tuple[float, float]:
        lat, lon = v
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Longitude must be between -180 and 180, got {lon}")
        return v


class NodeState(BaseModel):
    """Full state of a network node, stored in Redis."""

    node_id: str
    gps: tuple[float, float]
    uplink: UplinkType
    signal_strength: int
    packet_loss: float
    latency_ms: float
    timestamp: datetime
    recommended_route: UplinkType | None = None
    is_healthy: bool = True


class RouteDecision(BaseModel):
    """Result of the routing engine's optimal route calculation."""

    target_node: str
    current_uplink: UplinkType
    recommended_uplink: UplinkType
    should_failover: bool
    reason: str
    confidence_score: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="Confidence in the routing decision (0.0–1.0)"),
    ]


class TopologySnapshot(BaseModel):
    """Full topology snapshot of all known nodes."""

    nodes: list[NodeState]
    total_healthy: int
    total_degraded: int
    snapshot_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
