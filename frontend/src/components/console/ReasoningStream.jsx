import { Box, Typography, Stack } from "@mui/material";
import TuneIcon from "@mui/icons-material/Tune";
import BoltIcon from "@mui/icons-material/Bolt";
import LightbulbIcon from "@mui/icons-material/LightbulbOutlined";
import ShieldIcon from "@mui/icons-material/ShieldOutlined";
import SearchIcon from "@mui/icons-material/Search";

const ICONS = {
  step: <BoltIcon sx={{ fontSize: 15 }} />,
  candidates: <SearchIcon sx={{ fontSize: 15 }} />,
  match: <LightbulbIcon sx={{ fontSize: 15 }} />,
  risk_gate: <ShieldIcon sx={{ fontSize: 15 }} />,
  default: <TuneIcon sx={{ fontSize: 15 }} />,
};

function describeEvent(event) {
  switch (event.type) {
    case "step":
      return event.payload;
    case "candidates":
      return `Found ${event.payload.length} real matches — see Top matches →`;
    case "match":
      return `Best match: ${event.payload.product.name} — ${event.payload.reason}`;
    case "risk_gate":
      return `Risk gate: ${event.payload.decision} — ${event.payload.reason}`;
    case "order_created":
      return `Razorpay order created — ${event.payload.razorpay_order_id}`;
    case "error":
      return event.payload;
    default:
      return JSON.stringify(event.payload);
  }
}

export default function ReasoningStream({ events }) {
  const isHighlighted = (event) => event.type === "match";

  return (
    <Box>
      <Typography
        variant="overline"
        color="text.secondary"
        sx={{ letterSpacing: 1, mb: 1.5, display: "block" }}
      >
        Reasoning stream
      </Typography>

      {events.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
          Send a request above to watch the agent think in real time.
        </Typography>
      )}

      <Stack spacing={1.25}>
        {events.map((event, i) => (
          <Box
            key={i}
            sx={{
              display: "flex",
              gap: 1.25,
              ...(isHighlighted(event) && {
                bgcolor: "rgba(59,130,246,0.12)",
                borderRadius: 1.5,
                p: 1,
                mx: -1,
              }),
            }}
          >
            <Box sx={{ color: isHighlighted(event) ? "primary.light" : "text.secondary", mt: "2px" }}>
              {ICONS[event.type] || ICONS.default}
            </Box>
            <Typography
              variant="body2"
              sx={{
                fontFamily: "monospace",
                fontSize: 13,
                color: isHighlighted(event) ? "primary.light" : "text.primary",
              }}
            >
              {describeEvent(event)}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}