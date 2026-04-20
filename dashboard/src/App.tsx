import { motion, AnimatePresence } from "framer-motion";
import { Activity, Shield, Zap, Globe } from "lucide-react";
import { NetworkMap } from "./NetworkMap";
import { useTopologySocket } from "./useTopologySocket";
import { TimezoneSelector, type TimezoneMode, formatTimestamp } from "./components/TimezoneSelector";
import { useState } from "react";
import "./CyberTheme.css";

export default function App() {
  const { topology, connected } = useTopologySocket();
  const [tzMode, setTzMode] = useState<TimezoneMode>("UTC");

  const nodes = topology?.nodes ?? [];
  const stats = {
    healthy: topology?.total_healthy ?? 0,
    degraded: topology?.total_degraded ?? 0,
    packets: nodes.reduce((acc, n) => acc + (n.packet_loss < 2 ? 100 : 80), 0) // simulated global health
  };

  return (
    <div className="app-container">
      <div className="sidebar">
        <div className="sidebar-header">
          <Shield className="text-cyan-400" size={24} />
          <h1>Aegis Command</h1>
          <div className="ml-auto">
             <TimezoneSelector mode={tzMode} onChange={setTzMode} />
          </div>
        </div>

        <div className="stats-grid grid grid-cols-2 gap-4 mb-8">
            <div className="stat-card">
                <span className="text-dim text-xs block">ACTIVE NODES</span>
                <span className="text-2xl font-bold">{nodes.length}</span>
            </div>
            <div className={`stat-card ${connected ? "text-green-500" : "text-red-500"}`}>
                <span className="text-dim text-xs block">LINK STATUS</span>
                <span className="text-xs font-bold uppercase">{connected ? "SECURE" : "INTERRUPTED"}</span>
            </div>
        </div>

        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
          <h2 className="text-xs font-bold text-dim mb-4 tracking-widest uppercase">Terrain Topology</h2>
          <AnimatePresence mode="popLayout">
            {nodes.map((node) => (
              <motion.div
                key={node.node_id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className={`node-card ${node.is_healthy ? "healthy" : "degraded"}`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-bold text-sm tracking-tight">{node.node_id}</span>
                  <span className={`badge ${node.is_healthy ? "badge-cyan" : "badge-red"}`}>
                    {node.is_healthy ? "Online" : "Degraded"}
                  </span>
                </div>
                <div className="flex gap-3 text-[10px] text-dim mb-1">
                  <div className="flex items-center gap-1"><Zap size={10} /> {node.uplink}</div>
                  <div className="flex items-center gap-1"><Activity size={10} /> {node.latency_ms.toFixed(0)}ms</div>
                </div>
                <div className="text-[9px] text-cyan-400/60 font-mono">
                  {formatTimestamp(node.timestamp, tzMode)}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        <div className="mt-auto pt-4 border-t border-glass text-[10px] text-dim flex justify-between">
           <span>ENCRYPTION: AES-256</span>
           <span>v0.3.0-PRO</span>
        </div>
      </div>

      <main className="map-viewport">
        <NetworkMap nodes={nodes} timezone={tzMode} />
        
        <motion.div 
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="status-bar"
        >
          <div className={`w-2 h-2 rounded-full ${connected ? "bg-green-500 shadow-[0_0_10px_#39ff14]" : "bg-red-500"}`} />
          <span className="tracking-widest uppercase">
            {connected ? "Secured QUIC Uplink Active" : "Attempting Cipher Handshake..."}
          </span>
          <div className="ml-4 border-l border-glass pl-4 flex gap-4 text-xs">
             <span className="flex items-center gap-1"><Globe size={12}/> Global Mesh: {stats.healthy}/{nodes.length}</span>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
