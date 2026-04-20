import { MapContainer, TileLayer, CircleMarker, Popup, Polyline, Circle, GeoJSON } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { NodeState } from "./types";
import { formatTimestamp, type TimezoneMode } from "./components/TimezoneSelector";
import { useEffect, useState, useMemo } from "react";

interface NetworkMapProps {
  nodes: NodeState[];
  timezone: TimezoneMode;
}

export function NetworkMap({ nodes, timezone }: NetworkMapProps) {
  const [indiaGeoJson, setIndiaGeoJson] = useState<any>(null);

  useEffect(() => {
    fetch("/data/india.json")
      .then(res => res.json())
      .then(data => setIndiaGeoJson(data))
      .catch(err => console.error("Failed to load India GeoJSON:", err));
  }, []);

  const center: [number, number] = useMemo(() => {
    if (nodes.length === 0) return [22.0, 78.0]; // Centered on India
    const avgLat = nodes.reduce((s, n) => s + n.gps[0], 0) / nodes.length;
    const avgLon = nodes.reduce((s, n) => s + n.gps[1], 0) / nodes.length;
    return [avgLat, avgLon];
  }, [nodes]);

  const nodeMap = useMemo(() => {
    return new Map(nodes.map(n => [n.node_id, n]));
  }, [nodes]);

  return (
    <MapContainer
      center={center}
      zoom={5}
      style={{ width: "100%", height: "100%", background: "#05070a" }}
      zoomControl={true}
      attributionControl={true}
      maxBounds={[[5, 65], [40, 100]]} // Bounding box for India region
    >
      <TileLayer
        attribution='&copy; <a href="https://maps.google.com">Google Maps India</a>'
        url="https://mt1.google.com/vt/lyrs=m&hl=en-IN&x={x}&y={y}&z={z}"
        noWrap={true}
      />

      {/* Sovereign High-Visibility Boundary Glow */}
      {indiaGeoJson && (
        <GeoJSON 
          data={indiaGeoJson}
          style={{
            color: "#00f2ff",
            weight: 3,
            fillColor: "transparent",
            opacity: 0.4
          }}
        />
      )}

      {/* Swarm Relay Vectors */}
      {nodes.filter(n => n.proxied_by).map((node) => {
        const proxy = nodeMap.get(node.proxied_by!);
        if (!proxy) return null;
        return (
          <Polyline
            key={`relay-${node.node_id}`}
            positions={[
              [node.gps[0], node.gps[1]],
              [proxy.gps[0], proxy.gps[1]]
            ]}
            pathOptions={{
              color: "#00f2ff",
              weight: 2,
              dashArray: "10, 10",
              opacity: 0.5
            }}
          />
        );
      })}

      {nodes.map((node) => {
        const color = node.is_under_jamming ? "#ff1744" : (node.is_healthy ? "#00f2ff" : "#ff3e3e");
        const isProxied = !!node.proxied_by;
        const isJammed = node.is_under_jamming;
        
        return (
          <div key={node.node_id}>
            {/* Jamming Pulse (Extra visual alert) */}
            {isJammed && (
              <Circle
                center={[node.gps[0], node.gps[1]]}
                radius={450000}
                pathOptions={{
                  color: "#ff1744",
                  fillColor: "#ff1744",
                  fillOpacity: 0.2,
                  weight: 3,
                  dashArray: "5, 10"
                }}
              />
            )}
            
            <Circle
              center={[node.gps[0], node.gps[1]]}
              radius={250000}
              pathOptions={{
                color: color,
                fillColor: color,
                fillOpacity: 0.05,
                weight: 1,
                dashArray: "10, 20"
              }}
            />
            <CircleMarker
              center={[node.gps[0], node.gps[1]]}
              radius={isJammed ? 14 : (node.is_healthy ? 8 : 12)}
              pathOptions={{
                color: isJammed ? "#ff1744" : (isProxied ? "#ffaa00" : "white"), 
                fillColor: color,
                fillOpacity: 1,
                weight: (isProxied || isJammed) ? 3 : 2,
              }}
            >
              <Popup className="cyber-popup">
                <div style={{ padding: "5px", minWidth: "170px" }}>
                  <div style={{ color: color, fontWeight: "bold", fontSize: "14px", borderBottom: "1px solid rgba(255,255,255,0.1)", marginBottom: "5px" }}>
                    {node.node_id.toUpperCase()} 
                    {isJammed && <span style={{ color: "white", backgroundColor: "#ff1744", padding: "2px 5px", fontSize: "9px", borderRadius: "3px", marginLeft: "8px" }}>EW JAMMED</span>}
                    {node.is_verified && <span title="Sovereign Audit Verified" style={{ marginLeft: "8px", cursor: "help" }}>🛡️</span>}
                  </div>
                  <div style={{ color: "#90a4ae", fontSize: "11px" }}>
                    <p>Uplink: <span style={{ color: "white" }}>{isProxied ? "SWARM RELAY" : node.uplink.toUpperCase()}</span></p>
                    {isProxied && <p>Via: <span style={{ color: "#ffaa00" }}>{node.proxied_by}</span></p>}
                    <p>Latency: <span style={{ color: "white" }}>{node.latency_ms.toFixed(1)}ms</span></p>
                    <p>Packet Loss: <span style={{ color: node.packet_loss > 10 ? "#ff1744" : "white" }}>{node.packet_loss.toFixed(1)}%</span></p>
                    <p>Last Sync: <span style={{ color: "#4db6ac" }}>{formatTimestamp(node.timestamp, timezone)}</span></p>
                    {isJammed && <p style={{ color: "#ff1744", fontWeight: "bold", marginTop: "5px" }}>!!! LPI STEALTH MODE ACTIVE !!!</p>}
                    {!node.is_verified && <p style={{ color: "#ffa726", fontSize: "10px", marginTop: "5px" }}>⚠️ Integrity Check: Pending/Unverified</p>}
                    {node.is_verified && <p style={{ color: "#4db6ac", fontSize: "10px", marginTop: "5px" }}>✓ Sovereign Audit: Verified</p>}
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          </div>
        );
      })}
    </MapContainer>
  );
}
