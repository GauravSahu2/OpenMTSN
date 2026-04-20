# 🛡️ Sovereign Audit Specification

OpenMTSN implements a rigorous **Sovereign Audit** framework to ensure the absolute integrity and non-repudiation of situational awareness telemetry in disaster response environments.

## 1. Cryptographic Primitive
- **Algorithm**: Ed25519 (Edwards-curve Digital Signature Algorithm).
- **Reasoning**: Ed25519 provides high performance and high security with short 64-byte signatures and 32-byte public keys, ideal for resource-constrained edge devices and low-bandwidth satellite links.

## 2. Telemetry Chain of Custody

### A. Edge Signing (Rust)
The edge agent generates a unique Ed25519 keypair on first boot or retrieves it from a secure enclave.
Every telemetry packet is serialized as JSON, and a signature is computed over the payload (excluding the `signature` field itself).

### B. Transport Security (HTTP/3 + mTLS)
The packet is transmitted over a **QUIC (HTTP/3)** stream. The Control Plane acts as an identity provider by extracting the **Client Certificate** during the mTLS handshake.
- The `CN` (Common Name) or `Subject Alt Name` is used to identify the node.
- The node's authorized Public Key is retrieved from the secure store.

### C. Verification (Python/FastAPI)
The Control Plane validates the signature using the retrieved Public Key:
1. Re-serialize the payload.
2. Verify signature `S` against payload `P` and Public Key `K`.
3. If verified, mark `is_verified: true` in the live topology.

## 3. Threat Model Mitigation

| Threat | Mitigation |
|--------|------------|
| **Node Spoofing** | mTLS ensures the sender has a valid signed certificate for their Node ID. |
| **Payload Tampering** | Ed25519 signature fails if even a single bit of telemetry (e.g. GPS) is altered. |
| **Replay Attacks** | Every packet includes a unique high-resolution `timestamp`. The Control Plane enforces a 60-second signature window. |

---

## 4. Operational Guardrails
If signature verification fails, the Control Plane:
1. Logs a **SECURITY ALERT**.
2. Marks the node as **UNVERIFIED** in the dashboard.
3. Triggers an automated tactical alert to the Command Center dashboard.
