/// Types matching the FastAPI Pydantic models

export type UplinkType = "5g" | "satellite" | "mesh" | "cellular";

export interface NodeState {
  node_id: string;
  gps: [number, number];
  uplink: UplinkType;
  signal_strength: number;
  packet_loss: number;
  latency_ms: number;
  timestamp: string;
  recommended_route: UplinkType | null;
  is_healthy: boolean;
  proxied_by: string | null;
  is_under_jamming: boolean;
  is_verified: boolean;
}

export interface TopologySnapshot {
  nodes: NodeState[];
  total_healthy: number;
  total_degraded: number;
  snapshot_time: string;
}

export interface RouteDecision {
  target_node: string;
  current_uplink: UplinkType;
  recommended_uplink: UplinkType;
  should_failover: boolean;
  reason: string;
  confidence_score: number;
}

/** Visual config for each uplink type */
export interface UplinkVisual {
  color: string;
  glow: string;
  label: string;
  icon: string;
}

export const UPLINK_VISUALS: Record<UplinkType, UplinkVisual> = {
  "5g": {
    color: "#00e676",
    glow: "0 0 20px rgba(0, 230, 118, 0.6)",
    label: "5G",
    icon: "📡",
  },
  satellite: {
    color: "#448aff",
    glow: "0 0 20px rgba(68, 138, 255, 0.6)",
    label: "Satellite",
    icon: "🛰️",
  },
  mesh: {
    color: "#ff9100",
    glow: "0 0 20px rgba(255, 145, 0, 0.6)",
    label: "Mesh",
    icon: "🔗",
  },
  cellular: {
    color: "#7c4dff",
    glow: "0 0 20px rgba(124, 77, 255, 0.6)",
    label: "Cellular",
    icon: "📱",
  },
};

/** Get visual for a node, with degraded override */
export function getNodeVisual(node: NodeState): UplinkVisual {
  if (!node.is_healthy) {
    return {
      color: "#ff1744",
      glow: "0 0 25px rgba(255, 23, 68, 0.8)",
      label: "DEGRADED",
      icon: "⚠️",
    };
  }
  return UPLINK_VISUALS[node.uplink];
}
