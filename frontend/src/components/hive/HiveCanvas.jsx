import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Button, Stack, Typography } from "@mui/material";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import { useNavigate } from "react-router-dom";

import { BY_ID, CLUSTERS, SPECIALISTS, TOOLS, dependentsOf } from "./topology";
import { W, defaultLayout, edges, edgePath, layoutHeight } from "./layout";
import TuneCard from "./TuneCard";
import { useHiveSettings } from "../../context/HiveSettingsContext";

/**
 * The hive.
 *
 * Two modes over one topology:
 *   map  — the whole capability graph. Clicking a cluster enters that
 *          surface; clicking anything else opens its detail panel.
 *   live — the same graph inside a console turn, where a node lights ONLY
 *          when its agent emitted a real lifecycle event over the socket.
 *
 * Dragging changes layout, never meaning. Nothing here is on a timer.
 */

const TONE = {
  idle: { stroke: "rgba(255,255,255,0.10)", fill: "rgba(255,255,255,0.03)", text: "#5B6474" },
  ready: { stroke: "rgba(59,130,246,0.40)", fill: "rgba(59,130,246,0.07)", text: "#9AA3B2" },
  planned: { stroke: "rgba(255,255,255,0.15)", fill: "transparent", text: "#5B6474", dash: "4 3" },
  running: { stroke: "#3B82F6", fill: "rgba(59,130,246,0.16)", text: "#60A5FA" },
  done: { stroke: "#22C55E", fill: "rgba(34,197,94,0.14)", text: "#22C55E" },
  warn: { stroke: "#F59E0B", fill: "rgba(245,158,11,0.14)", text: "#F59E0B" },
  blocked: { stroke: "#EF4444", fill: "rgba(239,68,68,0.14)", text: "#EF4444" },
};

const DRAG_THRESHOLD = 3;

/** Worst state wins, so a cluster never looks calmer than its specialists. */
const SEVERITY = ["idle", "ready", "done", "running", "warn", "blocked"];

function relatedSet(id) {
  const set = new Set(["you", "hive", id]);
  if (SPECIALISTS.some((s) => s.id === id)) {
    const s = BY_ID[id];
    set.add(s.cluster);
    (s.tools ?? []).forEach((t) => set.add(t));
  } else if (CLUSTERS.some((c) => c.id === id)) {
    for (const s of SPECIALISTS.filter((s) => s.cluster === id)) {
      set.add(s.id);
      (s.tools ?? []).forEach((t) => set.add(t));
    }
  } else if (TOOLS.some((t) => t.id === id)) {
    for (const s of dependentsOf(id)) {
      set.add(s.id);
      set.add(s.cluster);
    }
  }
  return set;
}

export default function HiveCanvas({ mode = "map", events = [], clusters,
                                    onlyTunable = false }) {
  const navigate = useNavigate();
  const svgRef = useRef(null);
  const dragRef = useRef(null);

  const [moved, setMoved] = useState({});
  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null);
  // The clicked <g> is the popover's anchor — SVG elements expose
  // getBoundingClientRect, which is all MUI's Popover needs.
  const [anchorEl, setAnchorEl] = useState(null);

  const settings = useHiveSettings();

  const H = useMemo(() => layoutHeight(clusters, onlyTunable), [clusters, onlyTunable]);
  const base = useMemo(() => defaultLayout(clusters, onlyTunable), [clusters, onlyTunable]);

  // Positions a person dragged belong to the layout they dragged them in.
  // Narrowing to the tunable nodes makes a shorter canvas, and the offsets
  // from the taller one left YOU and the hive sitting over the header.
  useEffect(() => {
    setMoved({});
  }, [onlyTunable, clusters]);
  const wires = useMemo(() => edges(clusters, onlyTunable), [clusters, onlyTunable]);

  const nodes = useMemo(
    () => base.map((n) => (moved[n.id] ? { ...n, ...moved[n.id] } : n)),
    [base, moved]
  );
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);

  /**
   * Fold agent lifecycle events into a status map. Later events win, so a
   * node ends on its terminal state rather than flickering back.
   */
  const runStates = useMemo(() => {
    const map = {};
    for (const e of events) {
      if (e.type !== "agent") continue;
      const { id, status, summary, tone, tools } = e.payload;
      map[id] = { status: tone ?? status, raw: status, summary, tools };
    }
    return map;
  }, [events]);

  /**
   * A tool lights because an agent that ran said it touched it. The backend
   * sends `tools` on its lifecycle events; when it doesn't, fall back to the
   * topology's declared dependency for agents that actually ran — still a
   * read of a real run, never a decoration.
   */
  const toolsUsed = useMemo(() => {
    const used = new Set();
    for (const [agentId, state] of Object.entries(runStates)) {
      const declared = BY_ID[agentId]?.tools ?? [];
      for (const t of state.tools ?? declared) used.add(t);
    }
    return used;
  }, [runStates]);

  const toneOf = useCallback(
    (node) => {
      if (mode === "live") {
        if (node.kind === "specialist") return runStates[node.id]?.status ?? "idle";
        if (node.kind === "tool") return toolsUsed.has(node.id) ? "done" : "idle";
        if (node.kind === "cluster") {
          const members = SPECIALISTS.filter((s) => s.cluster === node.id);
          const tones = members.map((m) => runStates[m.id]?.status).filter(Boolean);
          if (!tones.length) return "idle";
          return tones.reduce((a, b) => (SEVERITY.indexOf(b) > SEVERITY.indexOf(a) ? b : a));
        }
        return Object.keys(runStates).length ? "running" : "idle";
      }
      // Map mode: a node's tone is its build state, nothing more.
      if (node.kind === "tool" || node.kind === "hive" || node.kind === "you") return "ready";
      return node.state === "planned" ? "planned" : "ready";
    },
    [mode, runStates, toolsUsed]
  );

  const highlight = useMemo(() => (hovered ? relatedSet(hovered) : null), [hovered]);
  const dim = useCallback((id) => Boolean(highlight) && !highlight.has(id), [highlight]);

  const toSvg = useCallback(
    (event) => {
      const rect = svgRef.current.getBoundingClientRect();
      return {
        x: ((event.clientX - rect.left) / rect.width) * W,
        y: ((event.clientY - rect.top) / rect.height) * H,
      };
    },
    [H]
  );

  const onPointerDown = useCallback(
    (event, node) => {
      event.currentTarget.setPointerCapture(event.pointerId);
      const p = toSvg(event);
      dragRef.current = {
        id: node.id,
        dx: node.cx - p.x,
        dy: node.cy - p.y,
        startX: p.x,
        startY: p.y,
        dragging: false,
      };
    },
    [toSvg]
  );

  const onPointerMove = useCallback(
    (event, node) => {
      const drag = dragRef.current;
      if (!drag || drag.id !== node.id) return;
      const p = toSvg(event);

      // Only treat this as a drag once the pointer has actually travelled —
      // otherwise a slightly shaky click would never open the detail panel.
      if (!drag.dragging) {
        const far = Math.hypot(p.x - drag.startX, p.y - drag.startY) > DRAG_THRESHOLD;
        if (!far) return;
        drag.dragging = true;
      }

      const cx = Math.min(Math.max(p.x + drag.dx, node.w / 2), W - node.w / 2);
      const cy = Math.min(Math.max(p.y + drag.dy, node.h / 2), H - node.h / 2);
      setMoved((prev) => ({ ...prev, [node.id]: { cx, cy } }));
    },
    [toSvg, H]
  );

  const onPointerUp = useCallback(
    (event, node) => {
      const drag = dragRef.current;
      dragRef.current = null;
      if (drag?.dragging) return; // a drag is not a click

      const element = event.currentTarget;
      setSelected((current) => {
        const next = current === node.id ? null : node.id;
        setAnchorEl(next ? element : null);
        return next;
      });
    },
    []
  );

  const closeCard = useCallback(() => {
    setSelected(null);
    setAnchorEl(null);
  }, []);

  const anyActive = mode === "live" && Object.keys(runStates).length > 0;

  const nodeHandlers = (node) => ({
    onPointerDown: (e) => onPointerDown(e, node),
    onPointerMove: (e) => onPointerMove(e, node),
    onPointerUp: (e) => onPointerUp(e, node),
    onPointerEnter: () => setHovered(node.id),
    onPointerLeave: () => setHovered((h) => (h === node.id ? null : h)),
    style: { cursor: "pointer" },
  });

  return (
    <Box>
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1 }}>
          {mode === "live" ? "Orchestration" : "The hive"}
        </Typography>
        {Object.keys(moved).length > 0 && (
          <Button
            size="small"
            onClick={() => setMoved({})}
            startIcon={<RestartAltIcon sx={{ fontSize: 16 }} />}
            sx={{ color: "text.secondary", boxShadow: "none", "&:hover": { boxShadow: "none" } }}
          >
            Reset layout
          </Button>
        )}
      </Stack>

      <Box
        ref={svgRef}
        component="svg"
        viewBox={`0 0 ${W} ${H}`}
        sx={{
          width: "100%",
          height: "auto",
          display: "block",
          touchAction: "none",
          userSelect: "none",
        }}
      >
        <defs>
          <filter id="hive-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* ── Edges ───────────────────────────────────────────────────── */}
        {wires.map(({ from, to, kind }) => {
          const a = byId[from];
          const b = byId[to];
          if (!a || !b) return null;

          const target = toneOf(b);
          const tone = TONE[target] ?? TONE.idle;
          const d = edgePath(a, b);
          const faded = dim(from) || dim(to);
          const running = mode === "live" && runStates[to]?.raw === "running";

          return (
            <g key={`${from}-${to}`} opacity={faded ? 0.12 : 1} style={{ transition: "opacity 120ms" }}>
              <path
                d={d}
                fill="none"
                stroke={tone.stroke}
                strokeWidth={kind === "tool" ? 0.9 : 1.4}
                strokeDasharray={target === "planned" ? "4 3" : undefined}
              />
              {running && (
                <circle r="3" fill="#60A5FA" filter="url(#hive-glow)">
                  <animateMotion dur="1.1s" repeatCount="indefinite" path={d} />
                </circle>
              )}
            </g>
          );
        })}

        {/* ── Nodes ───────────────────────────────────────────────────── */}
        {nodes.map((node) => {
          const tone = TONE[toneOf(node)] ?? TONE.idle;
          const faded = dim(node.id);
          const isSelected = selected === node.id;
          const left = node.cx - node.w / 2;
          const top = node.cy - node.h / 2;
          const running = mode === "live" && runStates[node.id]?.raw === "running";

          const common = {
            opacity: faded ? 0.15 : 1,
            style: { transition: "opacity 120ms" },
            ...nodeHandlers(node),
          };

          if (node.kind === "you") {
            return (
              <g key={node.id} {...common}>
                <circle
                  cx={node.cx}
                  cy={node.cy}
                  r={node.w / 2}
                  fill="rgba(255,255,255,0.04)"
                  stroke={isSelected ? "#3B82F6" : "rgba(255,255,255,0.18)"}
                  strokeWidth="1.4"
                />
                <text x={node.cx} y={node.cy + 5} textAnchor="middle" fill="#9AA3B2" style={{ fontSize: 16 }}>
                  ☺
                </text>
                <text x={node.cx} y={node.cy + node.w / 2 + 15} textAnchor="middle" fill="#5B6474" style={{ fontSize: 9.5, letterSpacing: "0.08em" }}>
                  YOU
                </text>
              </g>
            );
          }

          if (node.kind === "hive") {
            return (
              <g key={node.id} {...common}>
                {anyActive && (
                  <circle cx={node.cx} cy={node.cy} r={node.w / 2} fill="none" stroke="#3B82F6" strokeWidth="1">
                    <animate attributeName="r" values={`${node.w / 2};${node.w / 2 + 14};${node.w / 2}`} dur="2.4s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.5;0;0.5" dur="2.4s" repeatCount="indefinite" />
                  </circle>
                )}
                <circle
                  cx={node.cx}
                  cy={node.cy}
                  r={node.w / 2}
                  fill="rgba(59,130,246,0.12)"
                  stroke={anyActive || isSelected ? "#3B82F6" : "rgba(59,130,246,0.40)"}
                  strokeWidth="1.5"
                />
                <text x={node.cx} y={node.cy - 1} textAnchor="middle" fill="#60A5FA" style={{ fontSize: 19, fontWeight: 600 }}>
                  ⬢
                </text>
                <text x={node.cx} y={node.cy + 15} textAnchor="middle" fill="#9AA3B2" style={{ fontSize: 8.5, letterSpacing: "0.09em" }}>
                  HIVE
                </text>
              </g>
            );
          }

          const isTool = node.kind === "tool";
          return (
            <g key={node.id} {...common}>
              <rect
                x={left}
                y={top}
                width={node.w}
                height={node.h}
                rx={isTool ? 6 : 8}
                fill={tone.fill}
                stroke={isSelected ? "#3B82F6" : tone.stroke}
                strokeWidth={isTool ? 1 : 1.2}
                strokeDasharray={tone.dash}
              />
              {!isTool && (
                <text x={left + 15} y={node.cy + 4} textAnchor="middle" fill={tone.text} style={{ fontSize: 11 }}>
                  {node.glyph}
                </text>
              )}
              <text
                x={left + (isTool ? 11 : 28)}
                y={node.cy + 4}
                fill={tone.text}
                style={{
                  fontSize: isTool ? 10 : 11,
                  fontWeight: node.kind === "cluster" ? 600 : 500,
                }}
              >
                {node.label}
              </text>
              {running && (
                <circle cx={left + node.w - 12} cy={node.cy} r="3" fill="#60A5FA">
                  <animate attributeName="opacity" values="1;0.25;1" dur="0.9s" repeatCount="indefinite" />
                </circle>
              )}
              {mode === "live" && !running && runStates[node.id] && (
                <circle cx={left + node.w - 12} cy={node.cy} r="3" fill={tone.stroke} />
              )}
              {/* Tuned away from the shipped defaults — worth seeing at a
                  glance, since it changes how this agent behaves. */}
              {mode === "map" && settings.editedNodes.has(node.id) && (
                <circle cx={left + node.w - 11} cy={node.cy} r="3" fill="#22C55E">
                  <title>Tuned — settings differ from the defaults</title>
                </circle>
              )}
            </g>
          );
        })}
      </Box>

      <TuneCard
        nodeId={selected}
        anchorEl={anchorEl}
        mode={mode}
        runState={selected ? runStates[selected] : null}
        toolUsed={selected ? toolsUsed.has(selected) : false}
        onClose={closeCard}
        onNavigate={(route) => {
          closeCard();
          navigate(route);
        }}
        settings={settings}
      />
    </Box>
  );
}
