import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { useAgentSocket } from "../hooks/useAgentSocket";
import { API_BASE } from "../config";

/**
 * Multi-session conversation state, held above the router so switching
 * pages doesn't wipe it.
 *
 * All session mutations go through functional setState updaters and a
 * ref-held snapshot of the in-flight turn. Reading `sessions` from a
 * callback's closure caused stale-state bugs (a "new chat" could
 * re-archive or re-run the previous turn), so nothing here does that.
 *
 * In-memory only — a refresh clears everything.
 */
const ConversationContext = createContext(null);

const makeSession = () => ({ id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, title: null, turns: [] });

export function ConversationProvider({ children }) {
  const initial = useMemo(() => makeSession(), []);
  const [sessions, setSessions] = useState([initial]);
  const [activeSessionId, setActiveSessionId] = useState(initial.id);
  const [liveQuery, setLiveQuery] = useState(null);
  const [paymentStatus, setPaymentStatus] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);

  const agent = useAgentSocket();
  const { events, isRunning, pendingApproval, pendingSelection, sendIntent } = agent;

  // Tolerate an older useAgentSocket that has no resetRun: a missing
  // teardown shouldn't stop a new session from being created.
  const resetRun = useCallback(() => {
    if (typeof agent.resetRun === "function") agent.resetRun();
  }, [agent]);

  // Mirror of the in-flight turn, read at archive time so we never
  // depend on a stale closure value.
  const liveRef = useRef({ query: null, events: [] });
  liveRef.current = { query: liveQuery, events };

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? sessions[0];

  const liveTurn = useMemo(
    () => (liveQuery ? { id: "live", query: liveQuery, events } : null),
    [liveQuery, events]
  );

  const transcript = useMemo(
    () => (liveTurn ? [...activeSession.turns, liveTurn] : activeSession.turns),
    [activeSession, liveTurn]
  );

  const runStage = pendingSelection
    ? "selection"
    : pendingApproval
      ? "approval"
      : isRunning
        ? "running"
        : null;

  /** Fold the in-flight turn into a session. Pure updater — no closure reads. */
  const archiveInto = useCallback((list, sessionId) => {
    const { query, events: evts } = liveRef.current;
    if (!query || evts.length === 0) return list;
    return list.map((s) =>
      s.id === sessionId
        ? {
            ...s,
            title: s.title ?? query,
            turns: [...s.turns, { id: `t-${Date.now()}`, query, events: evts }],
          }
        : s
    );
  }, []);

  const startRun = useCallback(
    (text) => {
      const value = text?.trim();
      if (!value) return false;

      // A run paused at the product picker keeps its socket open, so
      // `isRunning` stayed true indefinitely and the composer was dead —
      // the only escape was starting a new chat. Asking for something else
      // now abandons the previous run rather than being refused.
      //
      // The snapshot is taken here, before resetRun() empties `events`,
      // because the archive updater below runs after that and would
      // otherwise fold an empty turn into the session.
      const snapshot = liveRef.current;
      const wasPaused = Boolean(runStage);

      if (wasPaused) {
        fetch(`${API_BASE}/abandon-run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: snapshot.query,
            stage: `${runStage} — superseded by a new request`,
          }),
        }).catch(() => {});
        resetRun();
      }

      setSessions((prev) => {
        const archived =
          snapshot.query && snapshot.events.length
            ? prev.map((s) =>
                s.id === activeSessionId
                  ? {
                      ...s,
                      title: s.title ?? snapshot.query,
                      turns: [
                        ...s.turns,
                        { id: `t-${Date.now()}`, query: snapshot.query, events: snapshot.events },
                      ],
                    }
                  : s
              )
            : prev;
        return archived.map((s) =>
          s.id === activeSessionId && !s.title ? { ...s, title: value } : s
        );
      });

      setPaymentStatus(null);
      setLiveQuery(value);
      // The active conversation is the thread a follow-up narrows.
      sendIntent(value, undefined, undefined, activeSessionId);
      return true;
    },
    [sendIntent, activeSessionId, runStage, resetRun]
  );

  const doNewChat = useCallback(() => {
    // Decide once, from this render's state: a session is reusable only
    // if it has no title, no turns, and nothing in flight.
    const reusable =
      activeSession &&
      !activeSession.title &&
      activeSession.turns.length === 0 &&
      !liveRef.current.query;

    resetRun();
    setPaymentStatus(null);

    if (reusable) {
      setLiveQuery(null);
      return;
    }

    const fresh = makeSession();
    setSessions((prev) => [...archiveInto(prev, activeSessionId), fresh]);
    setActiveSessionId(fresh.id);
    setLiveQuery(null);
  }, [resetRun, archiveInto, activeSessionId, activeSession]);

  const doOpenSession = useCallback(
    (id) => {
      if (id === activeSessionId) return;
      resetRun();
      setSessions((prev) => archiveInto(prev, activeSessionId));
      setLiveQuery(null);
      setPaymentStatus(null);
      setActiveSessionId(id);
    },
    [resetRun, archiveInto, activeSessionId]
  );

  // Leaving an in-flight run needs an explicit decision.
  const guard = useCallback(
    (action) => {
      if (runStage) {
        setPendingAction(() => action);
        return;
      }
      action();
    },
    [runStage]
  );

  const newChat = useCallback(() => guard(doNewChat), [guard, doNewChat]);
  const openSession = useCallback((id) => guard(() => doOpenSession(id)), [guard, doOpenSession]);

  const continueRun = useCallback(() => setPendingAction(null), []);

  const terminateRun = useCallback(() => {
    const { query } = liveRef.current;
    if (query) {
      fetch(`${API_BASE}/abandon-run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, stage: runStage }),
      }).catch(() => {});
    }
    const action = pendingAction;
    setPendingAction(null);
    action?.();
  }, [pendingAction, runStage]);

  const sessionList = useMemo(
    () => sessions.map((s) => ({ id: s.id, query: s.title ?? "New chat" })).reverse(),
    [sessions]
  );

  /**
   * Search from a photograph, as a turn in the same conversation.
   *
   * This is a request/response rather than a streamed run, but it produces
   * exactly what a typed search produces — steps, then candidates — so it
   * is pushed into the same event list and drawn by the same turn renderer.
   * A separate results view would have been less code today and two
   * divergent product lists by next week.
   */
  const startPhotoSearch = useCallback(
    async ({ imageB64, note = "" }) => {
      const label = note.trim() ? `Photo · ${note.trim()}` : "Search by photo";
      const snapshot = liveRef.current;

      setSessions((prev) => {
        const archived =
          snapshot.query && snapshot.events.length
            ? prev.map((s) =>
                s.id === activeSessionId
                  ? {
                      ...s,
                      title: s.title ?? snapshot.query,
                      turns: [
                        ...s.turns,
                        { id: `t-${Date.now()}`, query: snapshot.query, events: snapshot.events },
                      ],
                    }
                  : s
              )
            : prev;
        return archived.map((s) =>
          s.id === activeSessionId && !s.title ? { ...s, title: label } : s
        );
      });

      resetRun();
      setPaymentStatus(null);
      setLiveQuery(label);
      agent.pushEvents([
        // The picture rides with the turn rather than in separate state, so
        // it is archived into the session by the same code that archives
        // everything else — and scrolling back to an old photo search shows
        // the photo it was, not a label saying there was one.
        { type: "photo", payload: { image: imageB64, note: note.trim() } },
        { type: "step", payload: "Sending the photo to eBay's image search." },
      ]);

      try {
        const res = await fetch(`${API_BASE}/image-search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          // Same conversation id the socket sends, so a follow-up typed
          // after a photo search narrows those results instead of starting
          // a new search from whatever words it contains.
          body: JSON.stringify({
            image_b64: imageB64,
            note,
            session_id: activeSessionId,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          agent.pushEvents([
            {
              type: "error",
              payload:
                typeof data.detail === "string"
                  ? data.detail
                  : "The photo search could not run.",
            },
          ]);
          return;
        }
        agent.pushEvents([
          ...(data.steps ?? []).map((s) => ({ type: "step", payload: s })),
          ...(data.candidates?.length
            ? [
                { type: "candidates", payload: data.candidates },
                // The carousel reads this event, not `candidates`.
                // recommended_id is null on purpose: the listings are
                // ordered by quality, but nothing here picked one, and
                // marking a winner would put an "agent's pick" badge on a
                // choice the agent never made.
                {
                  type: "await_selection",
                  payload: {
                    candidates: data.candidates,
                    recommended_id: null,
                    reason: null,
                  },
                },
              ]
            : []),
        ]);
      } catch {
        agent.pushEvents([{ type: "error", payload: "Couldn't reach the backend." }]);
      }
    },
    [activeSessionId, agent, resetRun, setPaymentStatus]
  );

  const value = {
    ...agent,
    startPhotoSearch,
    transcript,
    sessionList,
    activeSessionId,
    paymentStatus,
    setPaymentStatus,
    sidebarCollapsed,
    setSidebarCollapsed,
    startRun,
    newChat,
    openSession,
    runStage,
    abandonPrompt: Boolean(pendingAction),
    continueRun,
    terminateRun,
  };

  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>;
}

export function useConversation() {
  const ctx = useContext(ConversationContext);
  if (!ctx) throw new Error("useConversation must be used inside ConversationProvider");
  return ctx;
}