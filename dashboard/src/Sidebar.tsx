import type { NodeState } from "./types";
import { getNodeVisual, UPLINK_VISUALS } from "./types";

interface SidebarProps {
  nodes: NodeState[];
  connected: boolean;
  totalHealthy: number;
  totalDegraded: number;
}

export function Sidebar({ nodes, connected, totalHealthy, totalDegraded }: SidebarProps) {
  return (
    <aside className="sidebar">
      {/* Header */}
      <div className="sidebar-header">
        <h1 className="logo">
          <span className="logo-icon">◉</span> OpenMTSN
        </h1>
        <p className="subtitle">Command Center</p>
        <div className={`connection-badge ${connected ? "online" : "offline"}`}>
          <span className="dot" />
          {connected ? "LIVE" : "OFFLINE"}
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-value">{nodes.length}</span>
          <span className="stat-label">Nodes</span>
        </div>
        <div className="stat-card healthy">
          <span className="stat-value">{totalHealthy}</span>
          <span className="stat-label">Healthy</span>
        </div>
        <div className="stat-card degraded">
          <span className="stat-value">{totalDegraded}</span>
          <span className="stat-label">Degraded</span>
        </div>
      </div>

      {/* Legend */}
      <div className="legend">
        <h3>Uplink Types</h3>
        {(Object.entries(UPLINK_VISUALS) as [string, typeof UPLINK_VISUALS["5g"]][]).map(
          ([key, v]) => (
            <div key={key} className="legend-item">
              <span className="legend-dot" style={{ background: v.color }} />
              <span>{v.icon} {v.label}</span>
            </div>
          )
        )}
        <div className="legend-item">
          <span className="legend-dot degraded-dot" />
          <span>⚠️ Degraded</span>
        </div>
      </div>

      {/* Node List */}
      <div className="node-list">
        <h3>Active Nodes</h3>
        {nodes.length === 0 && <p className="empty">No nodes reporting...</p>}
        {nodes.map((node) => {
          const visual = getNodeVisual(node);
          return (
            <div
              key={node.node_id}
              className={`node-card ${!node.is_healthy ? "node-degraded" : ""}`}
              style={{ borderLeftColor: visual.color }}
            >
              <div className="node-header">
                <span className="node-name">{visual.icon} {node.node_id}</span>
                <span
                  className="node-uplink-badge"
                  style={{ background: visual.color }}
                >
                  {visual.label}
                </span>
              </div>
              <div className="node-metrics">
                <span>📶 {node.signal_strength}%</span>
                <span>📉 {node.packet_loss}%</span>
                <span>⏱ {node.latency_ms}ms</span>
              </div>
              {node.recommended_route && node.recommended_route !== node.uplink && (
                <div className="node-failover">
                  → Failover to <strong>{node.recommended_route.toUpperCase()}</strong>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
