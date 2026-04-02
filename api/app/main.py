"""OpenMTSN Control Plane — FastAPI Application.

Provides the central API for telemetry ingestion, topology queries,
optimal routing decisions, and real-time WebSocket pushes to the
Command Center dashboard.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import RouteDecision, TelemetryPayload, TopologySnapshot
from app.redis_client import RedisTopologyStore
from app.routing_engine import calculate_optimal_route

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))

# ── Global state ──────────────────────────────────────────
_store: RedisTopologyStore | None = None
_ws_clients: set[WebSocket] = set()


def get_store() -> RedisTopologyStore:
    """Return the active Redis topology store (fail-fast if not initialised)."""
    if _store is None:
        raise RuntimeError("RedisTopologyStore not initialised — is the app running?")
    return _store


# ── Lifespan ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage Redis connection pool lifecycle."""
    global _store
    pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    _store = RedisTopologyStore(pool)
    logger.info("Redis connected at %s", settings.REDIS_URL)
    yield
    await pool.aclose()
    logger.info("Redis connection closed")


# ── App factory ───────────────────────────────────────────

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "High-assurance control plane for the OpenMTSN disaster response "
        "multi-terrain shared network. Ingests edge telemetry and dynamically "
        "routes critical data across 5G, satellite, and mesh uplinks."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST Endpoints ────────────────────────────────────────

@app.get("/health")
async def health_check() -> dict:
    """Liveness probe — also pings Redis."""
    store = get_store()
    redis_ok = await store.ping()
    return {"status": "ok" if redis_ok else "degraded", "redis": redis_ok}


@app.post("/telemetry", response_model=RouteDecision, status_code=201)
async def ingest_telemetry(payload: TelemetryPayload) -> RouteDecision:
    """Ingest telemetry from an edge agent and return the optimal route.

    Flow:
      1. Run the routing engine to compute the optimal uplink.
      2. Persist node state (with the recommendation) to Redis.
      3. Broadcast the updated topology to all WebSocket subscribers.
      4. Return the routing decision to the calling agent.
    """
    store = get_store()

    # 1. Compute optimal route
    decision = calculate_optimal_route(payload.node_id, payload)

    # 2. Persist to Redis
    await store.update_node_state(
        telemetry=payload,
        recommended_route=decision.recommended_uplink,
        is_healthy=not decision.should_failover,
    )

    # 3. Broadcast to dashboards
    await _broadcast_topology_update()

    return decision


@app.get("/topology", response_model=TopologySnapshot)
async def get_topology() -> TopologySnapshot:
    """Return the full live network topology."""
    store = get_store()
    return await store.get_topology()


@app.get("/route/{node_id}", response_model=RouteDecision)
async def get_route_for_node(node_id: str) -> RouteDecision:
    """Fetch the current state of a node and recalculate its optimal route."""
    store = get_store()
    state = await store.get_node_state(node_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in topology")

    telemetry = TelemetryPayload(
        node_id=state.node_id,
        gps=state.gps,
        uplink=state.uplink,
        signal_strength=state.signal_strength,
        packet_loss=state.packet_loss,
        latency_ms=state.latency_ms,
        timestamp=state.timestamp,
    )
    return calculate_optimal_route(node_id, telemetry)


# ── WebSocket endpoint ───────────────────────────────────

@app.websocket("/ws/topology")
async def websocket_topology(ws: WebSocket) -> None:
    """Real-time topology stream for the Command Center dashboard."""
    await ws.accept()
    _ws_clients.add(ws)
    logger.info("Dashboard WebSocket connected (%d total)", len(_ws_clients))
    try:
        while True:
            # Keep the connection alive; client can send pings
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
        logger.info("Dashboard WebSocket disconnected (%d total)", len(_ws_clients))


async def _broadcast_topology_update() -> None:
    """Push the latest topology to all connected dashboard clients."""
    if not _ws_clients:
        return
    store = get_store()
    snapshot = await store.get_topology()
    payload = snapshot.model_dump_json()
    dead: set[WebSocket] = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)
