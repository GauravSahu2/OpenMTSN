import { NetworkMap } from "./NetworkMap";
import { Sidebar } from "./Sidebar";
import { useTopologySocket } from "./useTopologySocket";

export default function App() {
  const { topology, connected } = useTopologySocket();

  const nodes = topology?.nodes ?? [];
  const totalHealthy = topology?.total_healthy ?? 0;
  const totalDegraded = topology?.total_degraded ?? 0;

  return (
    <div className="app-layout">
      <Sidebar
        nodes={nodes}
        connected={connected}
        totalHealthy={totalHealthy}
        totalDegraded={totalDegraded}
      />
      <main className="map-container">
        <NetworkMap nodes={nodes} />
        {/* Overlay status bar */}
        <div className="status-bar">
          <span className={`status-dot ${connected ? "pulse-green" : "pulse-red"}`} />
          <span>
            {connected ? "Live Topology Stream" : "Reconnecting..."} •{" "}
            {nodes.length} nodes tracked
          </span>
        </div>
      </main>
    </div>
  );
}
