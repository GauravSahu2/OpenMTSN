# 🛠️ Operations Runbook

This document provides operational instructions for deploying and maintaining the OpenMTSN high-assurance swarm platform.

## 1. Local Development & Simulation

### Environment Setup
1. Ensure Docker Desktop is running.
2. Generate certificates (provided in `/scripts/setup_certs.sh`).
3. Run the stack:
```bash
docker compose up -d --build
```

### Accessing Diagnostics
- **Dashboard**: [http://localhost:5173]
- **Control Plane API**: [https://localhost:8000/docs] (Requires HTTPS)
- **Monitoring**: [http://localhost:3000] (Grafana)

## 2. Certificate Rotation (mTLS)

To rotate certificates for node identity:
1. Generate new keys/certs in `certs/`.
2. Update the `volumes` in `docker-compose.yml`.
3. Restart the API: `docker compose restart api`.

## 3. High-Assurance Maintenance

### Monitoring Health
Check the Grafana dashboard for **QUIC Latency** and **Signature Failure Rates**. A spike in signature failures indicates potential spoofing or key desynchronization on the edge.

### Scaling
The Control Plane is stateless (backed by Redis). You can scale the `api` service horizontally using a load balancer that supports QUIC (UDP/443).

---
**Mission Priority: Continuity of Command.**
