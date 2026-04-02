//! OpenMTSN Edge Telemetry Agent
//!
//! A lightweight, memory-safe daemon designed to run on constrained devices
//! (drones, phones, Raspberry Pis). It continuously monitors local network
//! interfaces, publishes telemetry to the central MQTT broker, and falls
//! back to local mesh broadcast when cloud connectivity is lost.

use chrono::Utc;
use log::{error, info, warn};
use rand::Rng;
use rumqttc::{AsyncClient, Event, MqttOptions, Packet, QoS};
use serde::{Deserialize, Serialize};
use std::net::UdpSocket;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;
use sysinfo::Networks;
use tokio::time;

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
    pub node: String,
    pub gps: [f64; 2],
    pub uplink: String,
    pub signal: u8,
    pub packet_loss: f64,
    pub latency_ms: f64,
    pub timestamp: String,
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

// ── Mesh Fallback ────────────────────────────────────────

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

    match UdpSocket::bind("0.0.0.0:0") {
        Ok(socket) => {
            let _ = socket.set_broadcast(true);
            match socket.send_to(json.as_bytes(), MESH_BROADCAST_ADDR) {
                Ok(bytes) => {
                    info!(
                        "MESH BROADCAST: sent {} bytes to nearby peers",
                        bytes
                    );
                }
                Err(e) => warn!("Mesh broadcast send failed: {}", e),
            }
        }
        Err(e) => error!("Failed to create mesh broadcast socket: {}", e),
    }
}

// ── Mesh Listener ────────────────────────────────────────

/// Listen for incoming mesh broadcasts from other agents and relay them.
async fn mesh_listener() {
    let socket = match UdpSocket::bind(format!("0.0.0.0:{}", MESH_BROADCAST_PORT)) {
        Ok(s) => {
            let _ = s.set_nonblocking(true);
            s
        }
        Err(e) => {
            warn!("Could not bind mesh listener on port {}: {}", MESH_BROADCAST_PORT, e);
            return;
        }
    };

    info!("Mesh listener active on port {}", MESH_BROADCAST_PORT);
    let mut buf = [0u8; 4096];

    loop {
        match socket.recv_from(&mut buf) {
            Ok((len, src)) => {
                if let Ok(payload) = serde_json::from_slice::<TelemetryPayload>(&buf[..len]) {
                    info!(
                        "MESH RECV: node={} from {} (signal={}%)",
                        payload.node, src, payload.signal
                    );
                    // In production: enqueue for relay to broker when connectivity resumes
                }
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                // No data available, sleep briefly
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
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

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

    // Spawn MQTT event loop handler
    let connected_flag = mqtt_connected.clone();
    let failures_counter = consecutive_failures.clone();
    tokio::spawn(async move {
        loop {
            match eventloop.poll().await {
                Ok(Event::Incoming(Packet::ConnAck(_))) => {
                    info!("MQTT connected to broker");
                    connected_flag.store(true, Ordering::SeqCst);
                    failures_counter.store(0, Ordering::SeqCst);
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

    // Spawn mesh listener
    tokio::spawn(mesh_listener());

    // ── Telemetry publish loop ───────────────────────────
    let mut interval = time::interval(PUBLISH_INTERVAL);
    loop {
        interval.tick().await;

        let (uplink, signal, packet_loss, latency_ms) = probe_network_interfaces();

        let payload = TelemetryPayload {
            node: node_id.clone(),
            gps: [gps_lat, gps_lon],
            uplink,
            signal,
            packet_loss: (packet_loss * 100.0).round() / 100.0,
            latency_ms: (latency_ms * 100.0).round() / 100.0,
            timestamp: Utc::now().to_rfc3339(),
        };

        let json = match serde_json::to_string(&payload) {
            Ok(j) => j,
            Err(e) => {
                error!("Failed to serialise telemetry: {}", e);
                continue;
            }
        };

        // Attempt MQTT publish
        match client
            .publish(MQTT_TOPIC, QoS::AtLeastOnce, false, json.as_bytes())
            .await
        {
            Ok(_) => {
                consecutive_failures.store(0, Ordering::SeqCst);
                info!(
                    "MQTT PUB: node={} uplink={} signal={}% loss={:.1}% lat={:.0}ms",
                    payload.node, payload.uplink, payload.signal,
                    payload.packet_loss, payload.latency_ms
                );
            }
            Err(e) => {
                let fails = consecutive_failures.fetch_add(1, Ordering::SeqCst) + 1;
                warn!(
                    "MQTT publish failed ({}/{}): {}",
                    fails, MAX_MQTT_FAILURES, e
                );

                // If we've exceeded the failure threshold, fall back to mesh
                if fails >= MAX_MQTT_FAILURES {
                    warn!(
                        "MESH FALLBACK: {} consecutive MQTT failures — broadcasting to peers",
                        fails
                    );
                    broadcast_mesh_fallback(&payload);
                }
            }
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
            node: "test-node".to_string(),
            gps: [12.9716, 77.5946],
            uplink: "satellite".to_string(),
            signal: 85,
            packet_loss: 2.5,
            latency_ms: 45.0,
            timestamp: "2026-01-01T00:00:00Z".to_string(),
        };
        let json = serde_json::to_string(&payload).unwrap();
        assert!(json.contains("test-node"));
        assert!(json.contains("satellite"));
        assert!(json.contains("85"));
    }

    #[test]
    fn test_telemetry_deserialisation() {
        let json = r#"{
            "node": "drone-1",
            "gps": [12.9716, 77.5946],
            "uplink": "satellite",
            "signal": 85,
            "packet_loss": 2.5,
            "latency_ms": 45.0,
            "timestamp": "2026-01-01T00:00:00Z"
        }"#;
        let payload: TelemetryPayload = serde_json::from_str(json).unwrap();
        assert_eq!(payload.node, "drone-1");
        assert_eq!(payload.signal, 85);
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
