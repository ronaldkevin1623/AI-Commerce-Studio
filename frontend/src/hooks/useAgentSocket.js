import { useCallback, useRef, useState } from "react";

const WS_URL = "ws://localhost:8000/ws/agent";

/**
 * Manages the WebSocket lifecycle for one agent run:
 * - sendIntent() opens a fresh connection and sends the user's request
 * - events[] accumulates every step the backend streams back
 * - approve()/deny() respond to an escalation, reusing the same open socket
 */
export function useAgentSocket() {
  const [events, setEvents] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [pendingApproval, setPendingApproval] = useState(false);
  const socketRef = useRef(null);

  const sendIntent = useCallback((message, name = "Demo User", email = "demo@cartpilot.dev") => {
    setEvents([]);
    setIsRunning(true);
    setPendingApproval(false);

    const socket = new WebSocket(WS_URL);
    socketRef.current = socket;

    socket.onopen = () => {
      socket.send(JSON.stringify({ message, name, email }));
    };

    socket.onmessage = (rawEvent) => {
      const parsed = JSON.parse(rawEvent.data);
      setEvents((prev) => [...prev, parsed]);

      if (parsed.type === "risk_gate" && parsed.payload.decision === "escalated") {
        setPendingApproval(true);
      }
    };

    socket.onclose = () => {
      setIsRunning(false);
    };

    socket.onerror = () => {
      setIsRunning(false);
    };
  }, []);

  const respondToEscalation = useCallback((approved) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ approved }));
      setPendingApproval(false);
    }
  }, []);

  return { events, isRunning, pendingApproval, sendIntent, respondToEscalation };
}