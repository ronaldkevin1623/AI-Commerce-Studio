import { useCallback, useRef, useState } from "react";

import { WS_URL } from "../config";

/**
 * Manages the WebSocket lifecycle for one agent run:
 * - sendIntent() opens a fresh connection and sends the user's request
 * - events[] accumulates every step the backend streams back
 * - selectProduct() answers the agent's "which one should I buy?" pause
 * - respondToEscalation() answers a risk-gate escalation
 * Both responses reuse the same still-open socket.
 */
export function useAgentSocket() {
  const [events, setEvents] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [pendingApproval, setPendingApproval] = useState(false);
  const [pendingSelection, setPendingSelection] = useState(false);
  const [clarify, setClarify] = useState(null);
  const socketRef = useRef(null);

  // sessionId ties consecutive messages together so a follow-up can narrow
  // the previous results instead of searching again from nothing.
  const sendIntent = useCallback((message, name = "Demo User", email = "demo@commerce-studio.dev",
                                  sessionId = null) => {
    setEvents([]);
    setIsRunning(true);
    setPendingApproval(false);
    setPendingSelection(false);
    setClarify(null);

    const socket = new WebSocket(WS_URL);
    socketRef.current = socket;

    socket.onopen = () => {
      socket.send(JSON.stringify({ message, name, email, session_id: sessionId }));
    };

    socket.onmessage = (rawEvent) => {
      const parsed = JSON.parse(rawEvent.data);
      setEvents((prev) => [...prev, parsed]);

      if (parsed.type === "clarify") {
        setClarify(parsed.payload);
      }
      if (parsed.type === "await_selection") {
        setPendingSelection(true);
      }
      if (parsed.type === "risk_gate" && parsed.payload.decision === "escalated") {
        setPendingApproval(true);
      }
    };

    socket.onclose = () => {
      setIsRunning(false);
      setPendingSelection(false);
    };

    socket.onerror = () => {
      setIsRunning(false);
      setPendingSelection(false);
    };
  }, []);

  // The run is blocked on this reply, so the socket must always get one —
  // skipping sends an empty answer set rather than nothing at all, which
  // would leave the pipeline waiting forever.
  const answerClarify = useCallback((answers) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ answers: answers ?? {} }));
    }
    setClarify(null);
  }, []);

  const selectProduct = useCallback((productId) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ selected_product_id: productId }));
      setPendingSelection(false);
    }
  }, []);

  // Abandon the current run: close the socket and clear the flags so a
  // new conversation isn't blocked by a run that was left mid-flight
  // (e.g. still waiting on a product selection).
  const resetRun = useCallback(() => {
    const socket = socketRef.current;
    if (socket && socket.readyState <= WebSocket.OPEN) {
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      socket.close();
    }
    socketRef.current = null;
    setEvents([]);
    setIsRunning(false);
    setPendingApproval(false);
    setPendingSelection(false);
    setClarify(null);
  }, []);

  const respondToEscalation = useCallback((approved) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ approved }));
      setPendingApproval(false);
    }
  }, []);

  return {
    events,
    isRunning,
    pendingApproval,
    pendingSelection,
    clarify,
    sendIntent,
    answerClarify,
    selectProduct,
    respondToEscalation,
    resetRun,
  };
}