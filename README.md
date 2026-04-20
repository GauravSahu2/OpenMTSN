<div align="center">

# ◉ OpenMTSN: Sovereign High-Assurance Swarm Infrastructure

### Open Multi-Terrain Shared Network

**A production-grade, sovereign disaster response platform engineered for high-assurance situational awareness. Optimized for HTTP/3 (QUIC), cryptographic non-repudiation, and resilient edge compute.**

[![CI/CD](https://img.shields.io/github/actions/workflow/status/openmtsn/openmtsn/main.yml?style=for-the-badge&logo=github&label=CI%2FCD)](https://github.com/openmtsn/openmtsn/actions)
[![License](https://img.shields.io/badge/License-MIT-00e676?style=for-the-badge)](LICENSE)
[![Security](https://img.shields.io/badge/Audit-Ed25519-cyan?style=for-the-badge&logo=shield)](docs/SOVEREIGN_AUDIT.md)
[![Protocol](https://img.shields.io/badge/Protocol-HTTP/3-blue?style=for-the-badge&logo=hyper)](api/)

---

*"Where infrastructure fails, sovereignty endures. OpenMTSN provides a cryptographically verified, mathematically fault-tolerant backbone for mission-critical disaster recovery."*

</div>

---

## 🏛️ High-Assurance Architecture

OpenMTSN 2.0 has been hardened for high-stakes environments, transitioning from a generic telemetry app to a **Sovereign Audit** platform.

```mermaid
graph TB
    subgraph Edge["📡 Sovereign Edge (Rust)"]
        Agent[OpenMTSN Agent<br/>Tokio + Ed25519]
        DB[(SQLite<br/>Tactical Queue)]
        Agent <--> DB
    end

    subgraph Audit["🛡️ Sovereign Audit Layer"]
        Sign[Packet Signing<br/>Private Key Isolation]
        Ver[Control Plane Validator<br/>mTLS Identity Provider]
    end

    subgraph Transport["🌐 High-Assurance Transport"]
        QUIC[HTTP/3 / QUIC<br/>Low-Latency / Zero-Drop]
        mTLS[mTLS Tunnel<br/>Certificate Discovery]
    end

    subgraph Control["☁️ Control Plane (FastAPI)"]
        API[Routing Engine<br/>Vector Scoring]
        Redis[(Redis<br/>Live Topology)]
        API <--> Redis
    end

    subgraph UI["🖥️ Command Center"]
        Dashboard[React Dashboard<br/>ISRO Bhuvan Integration]
    end

    Agent -->|1. Sign| Sign
    Sign -->|2. Encrypt| Transport
    Transport -->|3. Verify| Ver
    Ver -->|4. Route| API
    API -->|5. Visualize| Dashboard

    style Edge fill:#05070a,stroke:#00f2ff,color:#e8eaf6
    style Audit fill:#05070a,stroke:#ff1744,color:#e8eaf6
    style Transport fill:#05070a,stroke:#448aff,color:#e8eaf6
    style Control fill:#05070a,stroke:#7c4dff,color:#e8eaf6
    style UI fill:#05070a,stroke:#ffa726,color:#e8eaf6
```

---

## 🔄 Telemetry Chain of Custody (Workflow)

The system ensures absolute integrity of situational awareness data through a multi-stage verification pipeline.

```mermaid
sequenceDiagram
    participant E as Edge Agent (Rust)
    participant S as Sovereign Audit Layer
    participant C as Control Plane (HTTP/3)
    participant D as Dashboard

    E->>E: Monitor Signal (5G/Sat/Mesh)
    E->>E: Package Telemetry (JSON)
    E->>S: Sign with Ed25519
    S->>C: mTLS Handshake + QUIC Stream
    C->>C: Extract Client Identity (Cert)
    C->>C: Retrieve Public Key
    C->>C: Verify Non-Repudiation
    alt Verified
        C->>C: Compute Routing Vector (SRE)
        C->>D: Broadcast verified_status=true
    else Failed
        C->>D: SECURITY ALERT: Unverified Node
    end
```

---

## 🚀 Key Strategic Features

### 1. Sovereign Audit (Ed25519)
Every telemetry packet originates with a cryptographic signature. The Control Plane verifies these signatures against a known identity provider (mTLS), ensuring that tactical data cannot be spoofed or altered in transit.

### 2. ISRO Bhuvan & Official Mapping
Synchronized with official **Indian Government (ISRO Bhuvan)** and Google India mapping data. The command center enforces official sovereign boundaries, including high-visibility overlays for restricted/monitored zones.

### 3. Tactical Edge Resilience
The Rust edge agent is built with zero OS dependencies (bundled libraries) and features an **autonomous SQLite persistence layer**. In "Blackout Mode," telemetry is queued locally and flushed with cryptographic integrity once a QUIC link is re-established.

### 4. Interactive Temporal Awareness
Mission-critical time synchronization across **UTC, IST, and Local** temporal modes, ensuring regional responders and global coordinators operate on a unified timeline.

---

## 🛠️ Quick Start (Vanguard Edition)

### 1. Local Hardened Simulation
Launch the high-assurance stack including the mTLS-ready Control Plane and signed agents:

```bash
git clone https://github.com/GauravSahu2/OpenMTSN.git
cd OpenMTSN
docker compose up -d --build
```

### 2. Identity Verification
The Control Plane is now accessible via **HTTPS** on port 8000.
- **RESTful Bridge**: [https://localhost:8000/docs](https://localhost:8000/docs)
- **Command Center**: [http://localhost:5173](http://localhost:5173)

---

## 📚 Technical Documentation

- [**Sovereign Audit Specification**](docs/SOVEREIGN_AUDIT.md): Cryptographic chain-of-custody details.
- [**Operations Runbook**](docs/OPERATIONS.md): Multi-cloud deployment and certificate rotation.
- [**Routing Algorithms**](api/app/routing_engine.py): Weighted vector failover logic.

---

<div align="center">

**OpenMTSN: Resiliency is a Sovereign Right.**
[Report Bug](https://github.com/GauravSahu2/OpenMTSN/issues) · [Request Feature](https://github.com/GauravSahu2/OpenMTSN/issues)

</div>
