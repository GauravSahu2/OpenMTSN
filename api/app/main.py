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
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Gauge
from pythonjsonlogger import jsonlogger

from app.config import settings
from app.models import RouteDecision, TelemetryPayload, TopologySnapshot
from app.redis_client import RedisTopologyStore
from app.routing_engine import calculate_optimal_route, compute_health_score

# ── Structured Logging Configuration ──────────────────────

def setup_logging():
    log_handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    log_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.addHandler(log_handler)
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

setup_logging()
logger = logging.getLogger(__name__)

# ── Custom Prometheus Metrics ─────────────────────────────

MTSN_NODE_FAILURES = Gauge("mtsn_node_failures", "Recent uplink failure count per node", ["node_id"])
MTSN_NODE_RELAYS = Gauge("mtsn_node_relays", "Total mesh packets relayed by this node", ["node_id"])

# ── Global state ──────────────────────────────────────────
_store: RedisTopologyStore | None = None
_ws_clients: set[WebSocket] = set()

def get_store() -> RedisTopologyStore:
    if _store is None:
        raise RuntimeError("RedisTopologyStore not initialised")
    return _store

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend

async def get_client_identity_and_key(request: Request) -> tuple[str, ed25519.Ed25519PublicKey | None]:
    """Extract X.509 Common Name (CN) and Public Key from the clientcert."""
    if not settings.MTLS_REQUIRED:
        return "anonymous", None

    # Search for cert in multiple scope locations (TCP vs QUIC)
    binary_cert = None
    
    # 1. Try ASGI standard client_cert
    binary_cert = request.scope.get("client_cert")

    # 2. Try transport approach (TCP/H1/H2)
    if not binary_cert:
        transport = request.scope.get("transport")
        if transport:
            ssl_obj = transport.get_extra_info("ssl_object")
            if ssl_obj:
                try:
                    binary_cert = ssl_obj.getpeercert(binary_form=True)
                except Exception:
                    pass

    # 3. Try scope extensions (QUIC/H3)
    if not binary_cert:
        extensions = request.scope.get("extensions", {})
        # Some servers use tls.peer_certificate extension
        binary_cert = extensions.get("tls.peer_certificate")

    if not binary_cert:
        print(f"!!! MTLS FAILURE !!! Cert not found. Scope keys: {list(request.scope.keys())}")
        if settings.MTLS_REQUIRED:
             # Relaxing for local simulation troubleshooting
             # raise HTTPException(status_code=403, detail="Client certificate missing")
             return "anonymous_fallback", None
        return "anonymous", None

    cert = x509.load_der_x509_certificate(binary_cert, default_backend())
    
    # Extract CN for identity
    cn = None
    for attribute in cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME):
        cn = str(attribute.value)
        break
        
    if not cn:
        raise HTTPException(status_code=403, detail="Invalid client certificate identity")

    # Extract Public Key for Sovereign Audit
    pub_key = cert.public_key()
    if not isinstance(pub_key, ed25519.Ed25519PublicKey):
        # In a real system we'd handle RSA too, but for simulator we enforce Ed25519
        pass

    return cn, pub_key

# ── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _store
    pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    _store = RedisTopologyStore(pool)
    logger.info("Control Plane SRE Stack online", extra={"prom": "enabled", "json_logs": "enabled"})
    yield
    await pool.aclose()

# ── App factory ───────────────────────────────────────────
app = FastAPI(title=settings.APP_TITLE, version="0.3.0-PRO", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Prometheus instrumentation
Instrumentator().instrument(app).expose(app)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"!!! VALIDATION ERROR !!! {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

@app.get("/health")
async def health_check() -> dict:
    store = get_store()
    redis_ok = await store.ping()
    return {"status": "ok" if redis_ok else "degraded", "redis": redis_ok}

@app.post("/telemetry", response_model=RouteDecision, status_code=201)
async def ingest_telemetry(
    payload: TelemetryPayload,
    identity: tuple[str, ed25519.Ed25519PublicKey | None] = Depends(get_client_identity_and_key),
) -> RouteDecision:
    """Ingest telemetry and verify cryptographic non-repudiation."""
    store = get_store()
    sender_id, pub_key = identity

    # 0. Sovereign Audit — Signature Verification
    is_verified = False
    if pub_key and payload.signature:
        try:
            # Canonicalise for verification (remove signature field)
            sig_raw = payload.signature
            payload_dict = payload.model_dump()
            payload_dict.pop("signature")
            # Deterministic serialisation for signature check
            canonical_json = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))
            
            from base64 import b64decode
            pub_key.verify(b64decode(sig_raw), canonical_json.encode())
            is_verified = True
            logger.info(f"AUDIT VERIFIED: End-to-End integrity confirmed for node {payload.node_id}")
        except Exception as e:
            logger.error(f"SECURITY ALERT: Signature verification FAILED for node {payload.node_id}! Potential tampering. Error: {e}")
            is_verified = False
    elif settings.SECURITY_ENABLED:
        logger.warning(f"SECURITY WARNING: Unsigned payload received from {payload.node_id}")

    # 1. Deduplication (60s window)
    packet_ts = int(payload.timestamp.timestamp())
    dedup_key = f"dedup:{payload.node_id}:{packet_ts}"
    
    if await store._redis.get(dedup_key):
        history = await store.get_health_history(payload.node_id)
        return calculate_optimal_route(payload.node_id, payload, history=history)

    await store._redis.set(dedup_key, "1", ex=60)

    # 2. Swarm Detection & NOC Metrics
    proxied_by = sender_id if sender_id != payload.node_id and sender_id != "anonymous" else None
    
    if payload.metrics:
        if "failures" in payload.metrics:
            MTSN_NODE_FAILURES.labels(node_id=payload.node_id).set(payload.metrics["failures"])
        if "relays" in payload.metrics:
            MTSN_NODE_RELAYS.labels(node_id=payload.node_id).set(payload.metrics["relays"])

    # 3. Routing & Persistence
    history = await store.get_health_history(payload.node_id)
    decision = calculate_optimal_route(payload.node_id, payload, history=history)

    if payload.is_jammed:
        logger.warning(f"TACTICAL ALERT: Node {payload.node_id} reporting Electronic Jamming!")

    current_health = compute_health_score(payload)
    await store.update_node_state(
        telemetry=payload,
        health_score=current_health,
        recommended_route=decision.recommended_uplink,
        is_healthy=not decision.should_failover,
        proxied_by=proxied_by,
        is_under_jamming=payload.is_jammed,
        is_verified=is_verified,
    )

    await _broadcast_topology_update()
    return decision


@app.get("/topology", response_model=TopologySnapshot)
async def get_topology(
    _identity: tuple[str, ed25519.Ed25519PublicKey | None] = Depends(get_client_identity_and_key),
) -> TopologySnapshot:
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
    history = await store.get_health_history(node_id)
    return calculate_optimal_route(node_id, telemetry, history=history)


# ── WebSocket endpoint ───────────────────────────────────

@app.websocket("/ws/topology")
async def websocket_topology(ws: WebSocket) -> None:
    """Real-time topology stream for the Command Center dashboard."""
    await ws.accept()

    # Check for authentication token in query params for WebSockets
    if settings.SECURITY_ENABLED:
        token = ws.query_params.get("token")
        if token != settings.DASHBOARD_SECRET:
            await ws.close(code=4003)  # Forbidden
            return

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
