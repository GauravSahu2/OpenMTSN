import { useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, Polyline } from "react-leaflet";
import type { NodeState } from "./types";
import { getNodeVisual } from "./types";

interface NetworkMapProps {
  nodes: NodeState[];
}

export function NetworkMap({ nodes }: NetworkMapProps) {
  // Default center: world view
  const center: [number, number] = useMemo(() => {
    if (nodes.length === 0) return [20, 0];
    const avgLat = nodes.reduce((s, n) => s + n.gps[0], 0) / nodes.length;
    const avgLon = nodes.reduce((s, n) => s + n.gps[1], 0) / nodes.length;
    return [avgLat, avgLon];
  }, [nodes]);

  // Draw connection lines between nearby nodes
  const connections = useMemo(() => {
    const lines: { from: NodeState; to: NodeState; color: string }[] = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        // Connect nodes within ~5 degrees
        const dist = Math.sqrt(
          (a.gps[0] - b.gps[0]) ** 2 + (a.gps[1] - b.gps[1]) ** 2
        );
        if (dist < 5) {
          const bothHealthy = a.is_healthy && b.is_healthy;
          lines.push({
            from: a,
            to: b,
            color: bothHealthy ? "rgba(0, 230, 118, 0.3)" : "rgba(255, 23, 68, 0.4)",
          });
        }
      }
    }
    return lines;
  }, [nodes]);

  return (
    <MapContainer
      center={center}
      zoom={3}
      style={{ width: "100%", height: "100%" }}
      zoomControl={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://carto.com">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />

      {/* Connection lines */}
      {connections.map((conn, i) => (
        <Polyline
          key={`line-${i}`}
          positions={[
            [conn.from.gps[0], conn.from.gps[1]],
            [conn.to.gps[0], conn.to.gps[1]],
          ]}
          pathOptions={{
            color: conn.color,
            weight: 2,
            dashArray: "8 4",
          }}
        />
      ))}

      {/* Node markers */}
      {nodes.map((node) => {
        const visual = getNodeVisual(node);
        return (
          <CircleMarker
            key={node.node_id}
            center={[node.gps[0], node.gps[1]]}
            radius={node.is_healthy ? 10 : 14}
            pathOptions={{
              color: visual.color,
              fillColor: visual.color,
              fillOpacity: node.is_healthy ? 0.7 : 0.9,
              weight: node.is_healthy ? 2 : 3,
            }}
          >
            <Popup>
              <div style={{ fontFamily: "Inter, sans-serif", fontSize: "13px" }}>
                <strong>{visual.icon} {node.node_id}</strong>
                <br />
                Uplink: <span style={{ color: visual.color }}>{visual.label}</span>
                <br />
                Signal: {node.signal_strength}%
                <br />
                Packet Loss: {node.packet_loss}%
                <br />
                Latency: {node.latency_ms}ms
                {node.recommended_route && node.recommended_route !== node.uplink && (
                  <>
                    <br />
                    <strong style={{ color: "#ff1744" }}>
                      → Failover to {node.recommended_route.toUpperCase()}
                    </strong>
                  </>
                )}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
