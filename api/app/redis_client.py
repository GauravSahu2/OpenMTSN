"""Async Redis client for OpenMTSN network topology state management."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from app.config import settings
from app.models import NodeState, TelemetryPayload, TopologySnapshot, UplinkType

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

NODE_KEY_PREFIX = "node:"


class RedisTopologyStore:
    """Manages the live network topology state in Redis.

    Each node's state is stored as a JSON hash at ``node:<node_id>`` with a TTL
    so stale nodes are automatically evicted.
    """

    def __init__(self, redis_pool: aioredis.Redis) -> None:
        self._redis = redis_pool

    # ── Write ─────────────────────────────────────────

    async def update_node_state(
        self,
        telemetry: TelemetryPayload,
        recommended_route: UplinkType | None = None,
        is_healthy: bool = True,
    ) -> NodeState:
        """Upsert a node's state from incoming telemetry."""
        state = NodeState(
            node_id=telemetry.node_id,
            gps=telemetry.gps,
            uplink=telemetry.uplink,
            signal_strength=telemetry.signal_strength,
            packet_loss=telemetry.packet_loss,
            latency_ms=telemetry.latency_ms,
            timestamp=telemetry.timestamp,
            recommended_route=recommended_route,
            is_healthy=is_healthy,
        )

        key = f"{NODE_KEY_PREFIX}{telemetry.node_id}"
        payload = state.model_dump_json()

        await self._redis.set(key, payload, ex=settings.REDIS_NODE_TTL_SECONDS)
        logger.debug("Updated node state: %s", telemetry.node_id)
        return state

    # ── Read ──────────────────────────────────────────

    async def get_node_state(self, node_id: str) -> NodeState | None:
        """Retrieve the current state of a single node."""
        raw = await self._redis.get(f"{NODE_KEY_PREFIX}{node_id}")
        if raw is None:
            return None
        return NodeState.model_validate_json(raw)

    async def get_topology(self) -> TopologySnapshot:
        """Scan all node keys and return the full live topology."""
        nodes: list[NodeState] = []
        cursor: int | bytes = 0

        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match=f"{NODE_KEY_PREFIX}*", count=100
            )
            if keys:
                values = await self._redis.mget(*keys)
                for val in values:
                    if val is not None:
                        nodes.append(NodeState.model_validate_json(val))
            if cursor == 0:
                break

        healthy = sum(1 for n in nodes if n.is_healthy)
        return TopologySnapshot(
            nodes=nodes,
            total_healthy=healthy,
            total_degraded=len(nodes) - healthy,
        )

    async def delete_node(self, node_id: str) -> bool:
        """Remove a node from the topology."""
        result = await self._redis.delete(f"{NODE_KEY_PREFIX}{node_id}")
        return result > 0

    # ── Lifecycle ─────────────────────────────────────

    async def ping(self) -> bool:
        """Health check for the Redis connection."""
        try:
            return await self._redis.ping()
        except Exception:
            logger.exception("Redis ping failed")
            return False
