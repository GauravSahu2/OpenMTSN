import { useEffect, useRef, useState, useCallback } from "react";
import type { TopologySnapshot } from "./types";

const WS_URL = "ws://localhost:8000/ws/topology";
const RECONNECT_DELAY_MS = 3000;

export function useTopologySocket() {
  const [topology, setTopology] = useState<TopologySnapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      console.log("[WS] Connected to topology stream");
      // Send keepalive ping every 15s
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send("ping");
        }
      }, 15000);
      ws.addEventListener("close", () => clearInterval(pingInterval));
    };

    ws.onmessage = (event) => {
      try {
        const snapshot: TopologySnapshot = JSON.parse(event.data);
        setTopology(snapshot);
      } catch (err) {
        console.warn("[WS] Failed to parse topology update", err);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      console.log("[WS] Disconnected — reconnecting...");
      reconnectTimerRef.current = window.setTimeout(
        connect,
        RECONNECT_DELAY_MS,
      );
    };

    ws.onerror = (err) => {
      console.error("[WS] Error", err);
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };
  }, [connect]);

  // Also poll /topology as fallback for initial data
  useEffect(() => {
    fetch("/api/topology")
      .then((r) => r.json())
      .then((data: TopologySnapshot) => {
        if (!topology) setTopology(data);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { topology, connected };
}
