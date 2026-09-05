import { useState } from "react";
import { Box, Stack, Typography } from "@mui/material";

import { EASE, Item, SPRING, Stagger, motion, useReducedMotion } from "./motion";

/**
 * A SYSTEM DIAGRAM, NOT AN ILLUSTRATION.
 *
 * The distinction is the whole brief for this component. A decorative
 * graphic is drawn to fill a space; a diagram is drawn because the reader
 * has to understand an ORDER of operations, and every part of it earns its
 * place by carrying one.
 *
 * So: the nodes are the real stages of this system in the real order they
 * run, each labelled with what it actually does. The connector carries a
 * pulse that travels in the direction the data does — the one piece of
 * ambient motion on the page, and it is here because direction is a fact
 * about the architecture that a static line cannot express.
 *
 * Nothing floats, nothing orbits, nothing shimmers. On a page selling
 * infrastructure, decoration reads as a lack of substance to show instead.
 */

const ACCENT = "#4F8DF7";

function Pulse({ vertical, delay = 0 }) {
  const flat = useReducedMotion();
  if (flat) return null;
  return (
    <motion.span
      aria-hidden
      initial={vertical ? { top: "-14%", opacity: 0 } : { left: "-14%", opacity: 0 }}
      animate={vertical
        ? { top: ["-14%", "114%"], opacity: [0, 1, 1, 0] }
        : { left: ["-14%", "114%"], opacity: [0, 1, 1, 0] }}
      transition={{
        duration: 2.6, delay, repeat: Infinity, repeatDelay: 1.4, ease: "linear",
        opacity: { times: [0, 0.15, 0.85, 1], duration: 2.6, delay,
                   repeat: Infinity, repeatDelay: 1.4 },
      }}
      style={{
        position: "absolute",
        width: vertical ? 3 : 26,
        height: vertical ? 26 : 3,
        borderRadius: 2,
        background: `linear-gradient(${vertical ? "180deg" : "90deg"}, transparent, ${ACCENT}, transparent)`,
        [vertical ? "left" : "top"]: "50%",
        transform: vertical ? "translateX(-50%)" : "translateY(-50%)",
      }}
    />
  );
}

function Connector({ vertical, index }) {
  return (
    <Box
      aria-hidden
      sx={{
        position: "relative",
        flexShrink: 0,
        ...(vertical
          ? { width: 3, height: 34, mx: "auto" }
          : { height: 3, flex: 1, minWidth: 24 }),
      }}
    >
      <Box sx={{
        position: "absolute", inset: 0,
        ...(vertical
          ? { width: 1, left: "50%", transform: "translateX(-0.5px)" }
          : { height: 1, top: "50%", transform: "translateY(-0.5px)" }),
        bgcolor: "rgba(255,255,255,0.13)",
      }} />
      <Pulse vertical={vertical} delay={index * 0.34} />
    </Box>
  );
}

/**
 * One stage.
 *
 * Its entrance is driven by the Stagger around the whole chain rather than
 * by an observer of its own. Six observers inside one diagram is both six
 * things to pay for and a reliability problem — nodes were arriving at
 * opacity zero and staying there when the container was still settling.
 * One observer for the diagram cannot desynchronise from itself.
 */
function Node({ node, index, vertical, active, onEnter, onLeave, compact }) {
  const Icon = node.icon;
  return (
    <Item
      y={0}
      onHoverStart={() => onEnter?.(index)}
      onHoverEnd={() => onLeave?.()}
      sx={{ flexShrink: 0, width: vertical ? "100%" : undefined }}
    >
      <Box
        sx={{
          position: "relative",
          px: compact ? 1.5 : 2,
          py: compact ? 1.1 : 1.4,
          minWidth: vertical ? 0 : compact ? 132 : 156,
          borderRadius: 1.5,
          border: "1px solid",
          borderColor: active ? "rgba(79,141,247,0.45)" : "rgba(255,255,255,0.10)",
          // Glass rather than a filled card: the section's own gradient
          // shows through, which is what stops a row of these reading as
          // six pasted rectangles.
          bgcolor: active ? "rgba(79,141,247,0.07)" : "rgba(255,255,255,0.022)",
          backdropFilter: "blur(6px)",
          transition: "border-color 220ms, background-color 220ms",
        }}
      >
        <Stack direction="row" spacing={1.1} sx={{ alignItems: "center" }}>
          {Icon && (
            <Icon sx={{
              fontSize: compact ? 15 : 16, flexShrink: 0,
              color: active ? ACCENT : "rgba(255,255,255,0.44)",
              transition: "color 220ms",
            }} />
          )}
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{
              fontSize: compact ? 12 : 12.5, fontWeight: 600, lineHeight: 1.3,
              color: "#ECECEE", letterSpacing: "-0.005em",
            }}>
              {node.label}
            </Typography>
            {node.detail && !compact && (
              <Typography sx={{
                fontSize: 10.5, color: "#8E8E96", lineHeight: 1.45, mt: 0.2,
              }}>
                {node.detail}
              </Typography>
            )}
          </Box>
        </Stack>
      </Box>
    </Item>
  );
}

/**
 * `nodes` runs in execution order. `loop` closes the last back to the first,
 * which is the only honest way to draw a system whose output is its own next
 * input — a straight line would say the process ends, and it does not.
 */
export default function Flow({ nodes, loop = false, compact = false, mount = false, sx }) {
  const [active, setActive] = useState(null);
  const flat = useReducedMotion();

  return (
    <Box sx={sx}>
      {/* Horizontal on wide screens, vertical below. Not a responsive
          afterthought: a six-stage chain squeezed onto a phone becomes
          unreadable long before it becomes narrow. */}
      <Stagger
        step={0.08}
        mount={mount}
        sx={{
          display: { xs: "none", md: "flex" },
          flexDirection: "row",
          alignItems: "center",
          flexWrap: "nowrap",
        }}
      >
        {nodes.map((node, i) => (
          <Box key={node.label} sx={{ display: "contents" }}>
            <Node node={node} index={i} active={active === i} compact={compact}
                  onEnter={setActive} onLeave={() => setActive(null)} />
            {i < nodes.length - 1 && <Connector index={i} />}
          </Box>
        ))}
      </Stagger>

      <Stagger step={0.08}
               mount={mount}
               sx={{ display: { xs: "flex", md: "none" },
                     flexDirection: "column", alignItems: "stretch" }}>
        {nodes.map((node, i) => (
          <Box key={node.label}>
            <Node node={node} index={i} vertical active={active === i} compact
                  onEnter={setActive} onLeave={() => setActive(null)} />
            {i < nodes.length - 1 && <Connector vertical index={i} />}
          </Box>
        ))}
      </Stagger>

      {loop && (
        <Box sx={{ mt: 2, position: "relative" }}>
          <Box sx={{
            height: 1, bgcolor: "rgba(255,255,255,0.10)",
            borderRadius: 1,
          }} />
          <Stack direction="row" spacing={0.75}
                 sx={{ alignItems: "center", justifyContent: "center", mt: -1.1 }}>
            <Box sx={{
              px: 1.25, py: 0.35, borderRadius: 999,
              bgcolor: "#0A0A0B", border: "1px solid rgba(255,255,255,0.10)",
            }}>
              <motion.span
                animate={flat ? undefined : { opacity: [0.45, 1, 0.45] }}
                transition={{ duration: 3.2, repeat: Infinity, ease: EASE }}
                style={{
                  fontSize: 10, letterSpacing: "0.08em", fontWeight: 700,
                  color: ACCENT, textTransform: "uppercase",
                }}
              >
                feeds the next cycle
              </motion.span>
            </Box>
          </Stack>
        </Box>
      )}
    </Box>
  );
}
