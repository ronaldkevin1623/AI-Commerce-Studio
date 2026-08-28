import { useEffect, useState } from "react";
import { Box, Typography, Stack, Collapse } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import CheckIcon from "@mui/icons-material/Check";
import LightbulbIcon from "@mui/icons-material/LightbulbOutlined";
import SearchIcon from "@mui/icons-material/Search";
import ShieldIcon from "@mui/icons-material/ShieldOutlined";
import TuneIcon from "@mui/icons-material/Tune";
import LoadingState from "../shared/LoadingState";
import StreamingText from "../shared/StreamingText";

function describeEvent(event) {
  switch (event.type) {
    case "step":
      return event.payload;
    case "candidates":
      return `Found ${event.payload.length} real matches — see Top matches →`;
    case "match":
      return `Best match: ${event.payload.product.name} — ${event.payload.reason}`;
    case "await_selection":
      return "Waiting for you to choose a product →";
    case "risk_gate":
      return `Risk gate: ${event.payload.decision} — ${event.payload.reason}`;
    case "order_created":
      return `Razorpay order created — ${event.payload.razorpay_order_id}`;
    case "mandate": {
      const m = event.payload;
      if (m.stage === "intent") {
        return `Intent mandate signed — under ₹${(m.constraints.max_amount_paise / 100).toLocaleString(
          "en-IN"
        )} for "${m.constraints.category}" · ${m.hash.slice(0, 12)}…`;
      }
      if (m.stage === "cart") {
        return `Cart mandate signed — bound to intent ${m.intent_hash.slice(0, 12)}… · ${m.hash.slice(
          0,
          12
        )}…`;
      }
      return m.ok
        ? `Mandate chain verified — ${m.checks.length} checks passed`
        : `Mandate chain FAILED — ${m.reason}`;
    }
    case "error":
      return event.payload;
    default:
      // Anything unexpected still renders readably rather than dumping
      // a wall of raw JSON into the transcript.
      return `[${event.type}]`;
  }
}

function useElapsedSeconds(active) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    setSeconds(0);
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [active]);
  return seconds;
}

/**
 * A collapsible reasoning trace: shows a shimmering "Thinking" header
 * with live elapsed time while the agent is working, then settles to
 * "Thought for Ns" once done — every row still reflects a real event
 * from the WebSocket, nothing here is decorative filler.
 */
export default function ReasoningStream({ events, isRunning }) {
  const [expanded, setExpanded] = useState(true);
  const seconds = useElapsedSeconds(isRunning);
  const isHighlighted = (event) => event.type === "match";
  // Agent lifecycle events drive the orchestration graph; showing them
  // here too would just duplicate the same information as noise.
  const visible = events.filter((e) => e.type !== "agent");

  return (
    <Box>
      <Stack
        direction="row"
        spacing={1}
        onClick={() => setExpanded((e) => !e)}
        sx={{ alignItems: "center", cursor: "pointer", mb: 1.5, userSelect: "none" }}
      >
        {isRunning ? (
          <LoadingState label="Thinking" active />
        ) : (
          <Typography variant="body2" fontWeight={600} color="text.secondary">
            {events.length > 0 ? `Thought for ${seconds || 1}s` : "Reasoning stream"}
          </Typography>
        )}
        <ExpandMoreIcon
          sx={{
            fontSize: 16,
            color: "text.secondary",
            transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
        />
      </Stack>

      <Collapse in={expanded}>
        {visible.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
            Send a request above to watch the agent think in real time.
          </Typography>
        )}

        <Box sx={{ position: "relative", pl: 2 }}>
          {visible.length > 1 && (
            <Box sx={{ position: "absolute", left: "5px", top: 4, bottom: 4, width: "1px", bgcolor: "divider" }} />
          )}

          <Stack spacing={1.1}>
            {visible.map((event, i) => (
              <Box
                key={i}
                sx={{
                  display: "flex",
                  gap: 1.25,
                  position: "relative",
                  minWidth: 0,
                  ...(isHighlighted(event) && {
                    bgcolor: "rgba(255,255,255,0.05)",
                    borderRadius: 1.5,
                    p: 1,
                    ml: -1,
                  }),
                }}
              >
                <Box
                  sx={{
                    position: "absolute",
                    left: isHighlighted(event) ? "-13px" : "-19px",
                    top: 3,
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    bgcolor: "background.default",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {i < visible.length - 1 || !isRunning ? (
                    <CheckIcon sx={{ fontSize: 11, color: isHighlighted(event) ? "text.primary" : "text.secondary" }} />
                  ) : (
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        border: "1.5px solid",
                        borderColor: "divider",
                        borderTopColor: "text.secondary",
                        animation: "commerce-studio-spin 0.7s linear infinite",
                      }}
                    />
                  )}
                </Box>

                {isHighlighted(event) ? (
                  <StreamingText
                    text={describeEvent(event)}
                    sx={{ fontFamily: "monospace", fontSize: 13, color: "text.primary", overflowWrap: "anywhere", minWidth: 0 }}
                  />
                ) : (
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: "monospace", fontSize: 13, color: "text.primary", overflowWrap: "anywhere", minWidth: 0 }}
                  >
                    {describeEvent(event)}
                  </Typography>
                )}
              </Box>
            ))}
          </Stack>
        </Box>
      </Collapse>

      <style>{`
        @keyframes commerce-studio-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </Box>
  );
}