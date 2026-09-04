import { useEffect, useMemo, useState } from "react";
import { Box, Chip, Stack, Typography } from "@mui/material";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";

import { API_BASE } from "../../config";

const inr = (paise) => `₹${Math.round((paise ?? 0) / 100).toLocaleString("en-IN")}`;

/**
 * THE PRODUCT RELATIONSHIP GRAPH.
 *
 * This is the basis for every cross-sell and every bundle the merchant is
 * asked to approve, drawn rather than described — so "these go together"
 * can be checked instead of taken on trust.
 *
 * The one thing this drawing must never do is make the two kinds of edge
 * look alike. A solid line means two products were bought in the same order
 * and a dashed one means they are merely filed under the same heading, and
 * the second is not evidence. On a young store almost every edge is dashed,
 * which is the honest picture and the one most likely to be misread — so
 * the distinction is carried three times over: in the stroke, in the
 * legend, and in a sentence the backend writes itself.
 *
 * Laid out on a circle rather than force-directed. A force simulation looks
 * more sophisticated and encodes nothing: with eight products its clusters
 * are artefacts of the starting positions, and a merchant would read
 * meaning into a distance that means nothing. A ring makes no claim about
 * proximity at all.
 */
export default function RelationshipGraph({ card }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  const [hover, setHover] = useState(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/growth/graph`);
        if (!res.ok) throw new Error(`Store returned ${res.status}`);
        const data = await res.json();
        if (live) setState({ status: "ready", data, error: null });
      } catch (err) {
        if (live) setState({ status: "error", data: null, error: String(err.message ?? err) });
      }
    })();
    return () => { live = false; };
  }, []);

  const { nodes, edges, layout } = useMemo(() => {
    const ns = state.data?.nodes ?? [];
    const size = 460;
    const radius = 168;
    const centre = size / 2;
    const placed = ns.map((node, i) => {
      // Start at the top and go clockwise, so the ordering the backend
      // chose (most-observed first) is readable off the drawing.
      const angle = (i / Math.max(ns.length, 1)) * Math.PI * 2 - Math.PI / 2;
      return {
        ...node,
        x: centre + radius * Math.cos(angle),
        y: centre + radius * Math.sin(angle),
        angle,
      };
    });
    const byId = Object.fromEntries(placed.map((n) => [n.id, n]));
    return {
      nodes: placed,
      edges: (state.data?.edges ?? [])
        .map((e) => ({ ...e, a: byId[e.source], b: byId[e.target] }))
        .filter((e) => e.a && e.b),
      layout: { size, centre },
    };
  }, [state.data]);

  if (state.status === "loading" || state.status === "error") {
    return (
      <Box sx={{ ...card, mb: 3 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
          <HubOutlinedIcon sx={{ fontSize: 17, color: "text.secondary" }} />
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5 }}>
            Product relationships
          </Typography>
        </Stack>
        <Typography variant="caption" sx={{ color: state.error ? "error.main" : "text.secondary" }}>
          {state.error ? `Couldn't read the graph: ${state.error}` : "Reading order history…"}
        </Typography>
      </Box>
    );
  }

  const { basis_counts: basis, orders_read: ordersRead, note } = state.data;
  const observed = basis?.co_purchase ?? 0;

  return (
    <Box sx={{ ...card, mb: 3 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
        <HubOutlinedIcon sx={{ fontSize: 17, color: "text.secondary" }} />
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5 }}>
          Product relationships
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Chip
          size="small"
          label={`${observed} observed · ${basis?.category_adjacency ?? 0} assumed`}
          sx={{ height: 22, fontSize: 11, bgcolor: "rgba(255,255,255,0.06)" }}
        />
      </Stack>

      <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 2, lineHeight: 1.65 }}>
        {note}
      </Typography>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "460px 1fr" }, gap: 2 }}>
        <Box sx={{ overflowX: "auto" }}>
          {/* The viewBox is wider than the ring on both sides: labels are
              anchored outward from the nodes, so a box that stopped at the
              circle would clip every name on the left and right of it. */}
          <svg width={layout.size} height={layout.size} role="img"
               viewBox={`-72 0 ${layout.size + 144} ${layout.size}`}
               aria-label="Product relationship graph">
            {edges.map((edge, i) => {
              const on = hover && (edge.source === hover || edge.target === hover);
              const real = edge.basis === "co_purchase";
              return (
                <line
                  key={i}
                  x1={edge.a.x} y1={edge.a.y} x2={edge.b.x} y2={edge.b.y}
                  stroke={real ? "#4ADE80" : "#5B6472"}
                  strokeWidth={real ? Math.min(1.5 + edge.support, 5) : 1}
                  // Dashed is not decoration: it is the whole difference
                  // between an observation and an assumption.
                  strokeDasharray={real ? undefined : "3 4"}
                  opacity={hover ? (on ? 0.95 : 0.12) : real ? 0.85 : 0.4}
                />
              );
            })}
            {nodes.map((node) => {
              const on = hover === node.id;
              const right = Math.cos(node.angle) > -0.1;
              return (
                <g key={node.id}
                   onMouseEnter={() => setHover(node.id)}
                   onMouseLeave={() => setHover(null)}
                   style={{ cursor: "default" }}>
                  <circle
                    cx={node.x} cy={node.y}
                    r={node.observed_degree ? 9 : 6}
                    fill={node.observed_degree ? "#4ADE80" : "#9AA3B2"}
                    stroke="#12151A" strokeWidth={2}
                    opacity={hover && !on ? 0.35 : 1}
                  />
                  <text
                    x={node.x + (right ? 14 : -14)} y={node.y + 4}
                    textAnchor={right ? "start" : "end"}
                    fill={on ? "#E6E9EF" : "#8A93A2"}
                    fontSize={10.5}
                    opacity={hover && !on ? 0.3 : 1}
                  >
                    {node.name.length > 22 ? `${node.name.slice(0, 21)}…` : node.name}
                  </text>
                </g>
              );
            })}
          </svg>
        </Box>

        <Box>
          <Stack spacing={1.25} sx={{ mb: 2 }}>
            <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 26, height: 0, borderTop: "3px solid #4ADE80" }} />
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                Bought in the same order — thicker means more often
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 26, height: 0, borderTop: "1px dashed #5B6472" }} />
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                Same category only — an assumption, not evidence
              </Typography>
            </Stack>
          </Stack>

          <Typography variant="caption"
                      sx={{ color: "text.disabled", display: "block", mb: 1,
                            textTransform: "uppercase", letterSpacing: 0.6, fontSize: 10 }}>
            Products · {nodes.length}
          </Typography>
          <Stack spacing={0.5} sx={{ maxHeight: 300, overflowY: "auto", pr: 0.5 }}>
            {nodes.map((node) => (
              <Stack
                key={node.id}
                direction="row" spacing={1}
                onMouseEnter={() => setHover(node.id)}
                onMouseLeave={() => setHover(null)}
                sx={{
                  alignItems: "center", px: 1, py: 0.6, borderRadius: 1,
                  bgcolor: hover === node.id ? "rgba(255,255,255,0.06)" : "transparent",
                }}
              >
                <Box sx={{
                  width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
                  bgcolor: node.observed_degree ? "#4ADE80" : "#9AA3B2",
                }} />
                <Typography variant="caption" sx={{ flex: 1, minWidth: 0, fontSize: 11.5 }} noWrap>
                  {node.name}
                </Typography>
                <Typography variant="caption"
                            sx={{ color: "text.disabled", fontSize: 11,
                                  fontVariantNumeric: "tabular-nums" }}>
                  {inr(node.price_paise)}
                </Typography>
              </Stack>
            ))}
          </Stack>

          <Typography variant="caption"
                      sx={{ color: "text.disabled", display: "block", mt: 1.5, lineHeight: 1.6 }}>
            Built from {ordersRead} order {ordersRead === 1 ? "record" : "records"} across the
            buyer-side log and the store's own checkouts. Positions on the ring carry no
            meaning — only the lines do.
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
