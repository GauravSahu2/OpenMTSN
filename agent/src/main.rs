//! OpenMTSN Edge Telemetry Agent
//!
//! A lightweight, memory-safe daemon designed to run on constrained devices
//! (drones, phones, Raspberry Pis). It continuously monitors local network
//! interfaces, publishes telemetry to the central MQTT broker, and falls
//! back to local mesh broadcast when cloud connectivity is lost.

use chacha20poly1305::aead::{Aead, KeyInit};
use chacha20poly1305::{ChaCha20Poly1305, Nonce};
use chrono::Utc;
use rand::Rng;
use reqwest::{Certificate, Client, Identity};
use rumqttc::{AsyncClient, Event, MqttOptions, Packet, QoS};
use rusqlite::{params, Connection, Result as SqlResult};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::net::UdpSocket;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;
use sysinfo::Networks;
use tokio::time;
use tracing::{error, info, warn};

// ── Configuration ────────────────────────────────────────
const MQTT_BROKER_HOST: &str = "localhost";
const MQTT_BROKER_PORT: u16 = 1883;
const MQTT_TOPIC: &str = "openmtsn/telemetry";
const PUBLISH_INTERVAL: Duration = Duration::from_secs(3);
const MESH_BROADCAST_PORT: u16 = 9876;
const MESH_BROADCAST_ADDR: &str = "255.255.255.255:9876";
const MAX_MQTT_FAILURES: u32 = 3;

// ── Telemetry Schema ─────────────────────────────────────

/// JSON telemetry payload published to the MQTT broker.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TelemetryPayload {
    pub node_id: String,
    pub gps: [f64; 2],
    pub uplink: String,
    pub signal_strength: u8,
    pub packet_loss: f64,
    pub latency_ms: f64,
    pub timestamp: String,
    pub metrics: Option<HashMap<String, f64>>,
    pub priority: u8,
    pub is_jammed: bool,
    pub signature: Option<String>,
}

// ── Network Interface Monitor ────────────────────────────

/// Determine the best available uplink and a simulated signal strength.
///
/// In production, this would query platform-specific APIs (NetworkManager on
/// Linux, CoreWLAN on macOS, etc.). For the open-source simulator, we
/// inspect `sysinfo` network interfaces and add realistic jitter.
fn probe_network_interfaces() -> (String, u8, f64, f64) {
    let networks = Networks::new_with_refreshed_list();
    let mut rng = rand::thread_rng();

    // Detect interface types from names (heuristic)
    let mut has_wifi = false;
    let mut has_cellular = false;
    let mut has_bluetooth = false;

    for (name, _data) in &networks {
        let lower = name.to_lowercase();
        if lower.contains("wlan") || lower.contains("wi-fi") || lower.contains("wifi") {
            has_wifi = true;
        }
        if lower.contains("wwan") || lower.contains("rmnet") || lower.contains("cellular") {
            has_cellular = true;
        }
        if lower.contains("bt") || lower.contains("bluetooth") || lower.contains("bnep") {
            has_bluetooth = true;
        }
    }

    // Priority: cellular > wifi > bluetooth > mesh fallback
    let (uplink, base_signal) = if has_cellular {
        ("cellular", rng.gen_range(60..95))
    } else if has_wifi {
        ("5g", rng.gen_range(50..90))
    } else if has_bluetooth {
        ("mesh", rng.gen_range(30..70))
    } else {
        ("satellite", rng.gen_range(40..80))
    };

    let packet_loss: f64 = rng.gen_range(0.0..8.0);
    let latency_ms: f64 = rng.gen_range(5.0..150.0);

    (uplink.to_string(), base_signal, packet_loss, latency_ms)
}

// ── Mesh Security ─────────────────────────────────────────

const MESH_KEY: &[u8; 32] = b"OpenMTSN-Deployment-Key-2026-X!1"; // 32-byte key

fn encrypt_mesh_packet(data: &str) -> Vec<u8> {
    let cipher = ChaCha20Poly1305::new(MESH_KEY.into());
    let mut rng = rand::thread_rng();
    let nonce_bytes: [u8; 12] = rng.gen();
    let nonce = Nonce::from_slice(&nonce_bytes); // 12-byte random nonce

    let encrypted = cipher
        .encrypt(nonce, data.as_bytes())
        .expect("Encryption failed");

    // Envelope: [Nonce (12b)] + [Tag+Ciphertext]
    let mut packet = nonce.to_vec();
    packet.extend_from_slice(&encrypted);
    packet
}

fn decrypt_mesh_packet(packet: &[u8]) -> Option<String> {
    if packet.len() < 12 {
        return None;
    }

    let cipher = ChaCha20Poly1305::new(MESH_KEY.into());
    let (nonce_bytes, ciphertext) = packet.split_at(12);
    let nonce = Nonce::from_slice(nonce_bytes);

    match cipher.decrypt(nonce, ciphertext) {
        Ok(plain) => String::from_utf8(plain).ok(),
        Err(_) => {
            warn!("MALICIOUS: Mesh packet failed integrity check (wrong key or tampered)");
            None
        }
    }
}

/// Broadcast telemetry via UDP to nearby OpenMTSN peers on the local subnet.
///
/// This is the last-resort data relay when the MQTT broker is unreachable.
fn broadcast_mesh_fallback(payload: &TelemetryPayload) {
    let json = match serde_json::to_string(payload) {
        Ok(j) => j,
        Err(e) => {
            error!("Failed to serialise mesh payload: {}", e);
            return;
        }
    };

    let encrypted_packet = encrypt_mesh_packet(&json);

    match UdpSocket::bind("0.0.0.0:0") {
        Ok(socket) => {
            let _ = socket.set_broadcast(true);
            match socket.send_to(&encrypted_packet, MESH_BROADCAST_ADDR) {
                Ok(bytes) => {
                    info!(
                        "MESH SECURED: sent {} bytes to nearby peers (ENCRYPTED)",
                        bytes
                    );
                }
                Err(e) => warn!("Mesh broadcast send failed: {}", e),
            }
        }
        Err(e) => error!("Failed to create mesh broadcast socket: {}", e),
    }
}

// ── Sovereignty & Audit ──────────────────────────────────
use base64::prelude::*;
use ed25519_dalek::{Signer, SigningKey};

/// Generate a deterministic signing key for simulation based on node_id.
/// In production, this would load the mTLS private key.
fn get_signing_key(node_id: &str) -> SigningKey {
    let mut seed = [0u8; 32];
    let bytes = node_id.as_bytes();
    let len = bytes.len().min(32);
    seed[..len].copy_from_slice(&bytes[..len]);
    SigningKey::from_bytes(&seed)
}

fn sign_payload(payload: &mut TelemetryPayload, key: &SigningKey) {
    // 1. Canonicalise (Serialise without signature)
    let _original_sig = payload.signature.take();
    let json = serde_json::to_string(&payload).unwrap();

    // 2. Sign
    let signature = key.sign(json.as_bytes());
    payload.signature = Some(BASE64_STANDARD.encode(signature.to_bytes()));
}

// ── Persistence Layer ─────────────────────────────────────
const DB_PATH: &str = "data/mtsn_queue.db";

pub struct PersistenceManager {
    conn: std::sync::Mutex<Connection>,
}

impl PersistenceManager {
    pub fn new() -> SqlResult<Self> {
        let conn = Connection::open(DB_PATH)?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS telemetry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )",
            [],
        )?;
        Ok(Self {
            conn: std::sync::Mutex::new(conn),
        })
    }

    pub fn queue_telemetry(&self, payload: &TelemetryPayload) -> SqlResult<()> {
        let json = serde_json::to_string(payload).unwrap();
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT INTO telemetry_queue (payload, priority) VALUES (?, ?)",
            params![json, payload.priority],
        )?;
        info!(
            "QUEUED [P{}]: Telemetry stored in local buffer",
            payload.priority
        );
        Ok(())
    }

    pub fn drain_queue(&self) -> SqlResult<Vec<(i32, TelemetryPayload)>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, payload FROM telemetry_queue ORDER BY priority DESC, id ASC LIMIT 50",
        )?;
        let rows = stmt.query_map([], |row| {
            let id: i32 = row.get(0)?;
            let payload_str: String = row.get(1)?;
            let payload: TelemetryPayload = serde_json::from_str(&payload_str).unwrap();
            Ok((id, payload))
        })?;

        let mut results = Vec::new();
        for row in rows {
            results.push(row?);
        }
        Ok(results)
    }

    pub fn delete_telemetry(&self, id: i32) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute("DELETE FROM telemetry_queue WHERE id = ?", params![id])?;
        Ok(())
    }
}

// ── Mesh Listener & Relay ─────────────────────────────────

/// Listen for incoming mesh broadcasts from other agents and relay them.
async fn mesh_listener(
    quic_client: Client,
    api_url: String,
    failures: Arc<AtomicU32>,
    relayed_count: Arc<AtomicU32>,
) {
    let socket = match UdpSocket::bind(format!("0.0.0.0:{}", MESH_BROADCAST_PORT)) {
        Ok(s) => {
            let _ = s.set_nonblocking(true);
            s
        }
        Err(e) => {
            warn!(
                "Could not bind mesh listener on port {}: {}",
                MESH_BROADCAST_PORT, e
            );
            return;
        }
    };

    info!("Mesh listener active on port {}", MESH_BROADCAST_PORT);
    let mut buf = [0u8; 4096];
    let mut recently_relayed: Vec<String> = Vec::new();

    loop {
        match socket.recv_from(&mut buf) {
            Ok((len, src)) => {
                if let Some(decrypted_json) = decrypt_mesh_packet(&buf[..len]) {
                    if let Ok(payload) = serde_json::from_str::<TelemetryPayload>(&decrypted_json) {
                        let pkt_id = format!("{}:{}", payload.node_id, payload.timestamp);

                        // 1. Deduplicate
                        if recently_relayed.contains(&pkt_id) {
                            continue;
                        }

                        info!(
                            "MESH SECURED RECV: node={} from {} (signal={}%)",
                            payload.node_id, src, payload.signal_strength
                        );

                        // 2. Relay if we have cloud connectivity
                        if failures.load(Ordering::SeqCst) < MAX_MQTT_FAILURES {
                            info!(
                                "SWARM RELAY: Proxying data for {} to Control Plane",
                                payload.node_id
                            );
                            let _ = quic_client
                                .post(format!("{}/telemetry", api_url))
                                .json(&payload)
                                .send()
                                .await;

                            relayed_count.fetch_add(1, Ordering::SeqCst);
                            recently_relayed.push(pkt_id);
                            if recently_relayed.len() > 100 {
                                recently_relayed.remove(0);
                            }
                        }
                    }
                }
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                tokio::time::sleep(Duration::from_millis(500)).await;
            }
            Err(e) => {
                warn!("Mesh listener error: {}", e);
                tokio::time::sleep(Duration::from_secs(1)).await;
            }
        }
    }
}

// ── Main ─────────────────────────────────────────────────

#[tokio::main]
async fn main() {
    // Initialise structured JSON logging for SRE auditability
    tracing_subscriber::fmt()
        .json()
        .with_max_level(tracing::Level::INFO)
        .init();

    info!("OpenMTSN Edge Agent Starting — Tactical SRE Mode Active");

    let node_id = std::env::var("MTSN_NODE_ID").unwrap_or_else(|_| "agent-001".to_string());
    let broker_host =
        std::env::var("MTSN_MQTT_HOST").unwrap_or_else(|_| MQTT_BROKER_HOST.to_string());
    let broker_port: u16 = std::env::var("MTSN_MQTT_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(MQTT_BROKER_PORT);
    let gps_lat: f64 = std::env::var("MTSN_GPS_LAT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(12.9716);
    let gps_lon: f64 = std::env::var("MTSN_GPS_LON")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(77.5946);

    info!("OpenMTSN Agent starting — node={}", node_id);
    info!("MQTT broker: {}:{}", broker_host, broker_port);

    // MQTT client setup
    let mut mqtt_opts = MqttOptions::new(&node_id, &broker_host, broker_port);
    mqtt_opts.set_keep_alive(Duration::from_secs(10));
    mqtt_opts.set_clean_session(true);

    let (client, mut eventloop) = AsyncClient::new(mqtt_opts, 10);
    let mqtt_connected = Arc::new(AtomicBool::new(false));
    let consecutive_failures = Arc::new(AtomicU32::new(0));

    // Load TLS Identity for mTLS (per-device cert)
    let cert_path =
        std::env::var("MTSN_CLIENT_CERT").unwrap_or_else(|_| format!("certs/{}.crt", node_id));
    let key_path =
        std::env::var("MTSN_CLIENT_KEY").unwrap_or_else(|_| format!("certs/{}.key", node_id));
    let ca_path = std::env::var("MTSN_CA_CERT").unwrap_or_else(|_| "certs/ca.crt".to_string());

    let client_cert = fs::read(&cert_path).expect("Failed to read client cert");
    let client_key = fs::read(&key_path).expect("Failed to read client key");
    let ca_cert = fs::read(&ca_path).expect("Failed to read CA cert");

    let identity =
        Identity::from_pem(&[client_cert, client_key].concat()).expect("Failed to create identity");
    let root_ca = Certificate::from_pem(&ca_cert).expect("Failed to load Root CA");

    let quic_client = Client::builder()
        .use_rustls_tls()
        .add_root_certificate(root_ca)
        .identity(identity)
        .https_only(true)
        .build()
        .expect("Failed to build HTTP/3 client");

    let api_url =
        std::env::var("MTSN_API_URL").unwrap_or_else(|_| "https://localhost:8000".to_string());

    // Initialize persistence
    let persistence = Arc::new(PersistenceManager::new().expect("Failed to initialize SQLite DB"));

    // Spawn MQTT event loop handler
    let connected_flag = mqtt_connected.clone();
    let mqtt_fails = consecutive_failures.clone();
    tokio::spawn(async move {
        loop {
            match eventloop.poll().await {
                Ok(Event::Incoming(Packet::ConnAck(_))) => {
                    info!("MQTT connected to broker");
                    connected_flag.store(true, Ordering::SeqCst);
                    mqtt_fails.store(0, Ordering::SeqCst);
                }
                Ok(_) => {}
                Err(e) => {
                    warn!("MQTT event loop error: {}", e);
                    connected_flag.store(false, Ordering::SeqCst);
                    tokio::time::sleep(Duration::from_secs(2)).await;
                }
            }
        }
    });

    // Initialise and spawn mesh listener
    let listener_client = quic_client.clone();
    let listener_url = api_url.clone();
    let listener_fails = consecutive_failures.clone();
    let relayed_counter = Arc::new(AtomicU32::new(0));
    let listener_relayed = relayed_counter.clone();

    tokio::spawn(async move {
        mesh_listener(
            listener_client,
            listener_url,
            listener_fails,
            listener_relayed,
        )
        .await;
    });

    let mut skip_tick = false;

    // Main telemetry loop
    let mut interval = time::interval(PUBLISH_INTERVAL);
    loop {
        interval.tick().await;

        let (uplink, signal, packet_loss, latency_ms) = probe_network_interfaces();

        // ── Tactical Jamming Detection ───────────────────
        // If loss is high but signal seems OK -> Potential EW Attack
        let is_jammed = (packet_loss > 25.0) && (signal > 40);
        if is_jammed {
            warn!("EW ALERT: Potential jamming detected! Entering LPI Mode.");
            // In LPI mode, we skip every other tick to reduce electronic footprint
            skip_tick = !skip_tick;
            if skip_tick {
                info!("LPI MODE: Skipping broadcast cycle to maintain stealth.");
                continue;
            }
        }

        let mut metrics = HashMap::new();
        metrics.insert(
            "failures".to_string(),
            consecutive_failures.load(Ordering::SeqCst) as f64,
        );
        metrics.insert(
            "relays".to_string(),
            relayed_counter.load(Ordering::SeqCst) as f64,
        );

        let priority = if is_jammed || consecutive_failures.load(Ordering::SeqCst) > 0 {
            5
        } else {
            0
        };

        let mut payload = TelemetryPayload {
            node_id: node_id.clone(),
            gps: [gps_lat, gps_lon],
            uplink,
            signal_strength: signal,
            packet_loss: (packet_loss * 100.0).round() / 100.0,
            latency_ms: (latency_ms * 100.0).round() / 100.0,
            timestamp: Utc::now().to_rfc3339(),
            metrics: Some(metrics),
            priority,
            is_jammed,
            signature: None,
        };

        // ── Phase 9: Sovereign Audit Signing ──────────────
        let signing_key = get_signing_key(&node_id);
        sign_payload(&mut payload, &signing_key);

        let json = match serde_json::to_string(&payload) {
            Ok(j) => j,
            Err(e) => {
                error!("Failed to serialise telemetry: {}", e);
                continue;
            }
        };

        // ── Phase 3: QUIC / HTTP/3 Telemetry ────────────────
        let res = quic_client
            .post(format!("{}/telemetry", api_url))
            .json(&payload)
            .send()
            .await;

        match res {
            Ok(resp) if resp.status().is_success() => {
                info!(
                    "QUIC PUB: node_id={} uplink={} signal_strength={}% loss={:.1}% lat={:.0}ms",
                    payload.node_id,
                    payload.uplink,
                    payload.signal_strength,
                    payload.packet_loss,
                    payload.latency_ms
                );
                consecutive_failures.store(0, Ordering::SeqCst);

                // Drain local queue if connected
                if let Ok(queued_items) = persistence.drain_queue() {
                    for (id, q_payload) in queued_items {
                        if quic_client
                            .post(format!("{}/telemetry", api_url))
                            .json(&q_payload)
                            .send()
                            .await
                            .is_ok()
                        {
                            let _ = persistence.delete_telemetry(id);
                        }
                    }
                }
            }
            Ok(resp) => {
                warn!("QUIC publish rejected: status={}", resp.status());
                let _ = persistence.queue_telemetry(&payload);
            }
            Err(e) => {
                warn!("QUIC connection failed: {}", e);
                let _ = persistence.queue_telemetry(&payload);

                let fails = consecutive_failures.fetch_add(1, Ordering::SeqCst) + 1;
                if fails >= MAX_MQTT_FAILURES {
                    broadcast_mesh_fallback(&payload);
                }
            }
        }

        // Also maintain MQTT for Mesh (Peer-to-Peer) coordination
        if mqtt_connected.load(Ordering::SeqCst) {
            let _ = client
                .publish(MQTT_TOPIC, QoS::AtMostOnce, false, json.as_bytes())
                .await;
        }
    }
}

// ── Tests ────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_telemetry_serialisation() {
        let payload = TelemetryPayload {
            node_id: "test-node".to_string(),
            gps: [12.9716, 77.5946],
            uplink: "satellite".to_string(),
            signal_strength: 85,
            packet_loss: 2.5,
            latency_ms: 45.0,
            timestamp: "2026-01-01T00:00:00Z".to_string(),
            metrics: None,
            priority: 0,
            is_jammed: false,
            signature: None,
        };
        let json = serde_json::to_string(&payload).unwrap();
        assert!(json.contains("test-node"));
        assert!(json.contains("satellite"));
        assert!(json.contains("85"));
    }

    #[test]
    fn test_telemetry_deserialisation() {
        let json = r#"{
            "node_id": "drone-1",
            "gps": [12.9716, 77.5946],
            "uplink": "satellite",
            "signal_strength": 85,
            "packet_loss": 2.5,
            "latency_ms": 45.0,
            "timestamp": "2026-01-01T00:00:00Z",
            "priority": 0,
            "is_jammed": false
        }"#;
        let payload: TelemetryPayload = serde_json::from_str(json).unwrap();
        assert_eq!(payload.node_id, "drone-1");
        assert_eq!(payload.signal_strength, 85);
        assert_eq!(payload.gps, [12.9716, 77.5946]);
    }

    #[test]
    fn test_network_probe_returns_valid_data() {
        let (uplink, signal, loss, latency) = probe_network_interfaces();
        assert!(!uplink.is_empty());
        assert!(signal <= 100);
        assert!(loss >= 0.0);
        assert!(latency >= 0.0);
    }
}
