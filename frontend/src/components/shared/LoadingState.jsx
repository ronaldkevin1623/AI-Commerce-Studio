import { useEffect, useState } from "react";
import { Box, Typography, Stack } from "@mui/material";

/**
 * A 3x3 pixel-grid loader with a diagonal "chevron" wavefront —
 * adapted from a Tailwind/Next.js reference into plain MUI + CSS
 * keyframes, since this project doesn't use Tailwind.
 */
const CHEVRON_DELAYS = Array.from({ length: 9 }, (_, i) => {
  const r = Math.floor(i / 3);
  const c = i % 3;
  return (c + Math.abs(r - 1)) * 90;
});

function useElapsed(active) {
  const [ds, setDs] = useState(0);
  useEffect(() => {
    if (!active) {
      setDs(0);
      return;
    }
    const t = setInterval(() => setDs((d) => d + 1), 100);
    return () => clearInterval(t);
  }, [active]);
  const total = ds / 10;
  return total < 60 ? `${total.toFixed(1)}s` : `${Math.floor(total / 60)}m ${(total % 60).toFixed(1)}s`;
}

export default function LoadingState({ label = "Thinking", active = true }) {
  const elapsed = useElapsed(active);

  return (
    <Stack direction="row" alignItems="center" spacing={1.25}>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(3, 4px)", gap: "1.5px" }}>
        {CHEVRON_DELAYS.map((delay, i) => (
          <Box
            key={i}
            sx={{
              width: 4,
              height: 4,
              borderRadius: "1px",
              bgcolor: "primary.light",
              opacity: 0.15,
              animation: active ? `cartpilot-pixel-on 650ms ease-in-out ${delay}ms infinite` : "none",
            }}
          />
        ))}
      </Box>

      <Typography
        variant="body2"
        sx={{
          fontWeight: 500,
          backgroundImage: "linear-gradient(90deg, rgba(154,163,178,0.6) 35%, #F3F4F6 50%, rgba(154,163,178,0.6) 65%)",
          backgroundSize: "200% 100%",
          backgroundClip: "text",
          WebkitBackgroundClip: "text",
          color: "transparent",
          animation: active ? "cartpilot-shimmer 1.4s linear infinite" : "none",
        }}
      >
        {label}
      </Typography>

      <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
        {elapsed}
      </Typography>

      <style>{`
        @keyframes cartpilot-pixel-on {
          0%, 100% { opacity: 0.15; }
          50% { opacity: 1; }
        }
        @keyframes cartpilot-shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </Stack>
  );
}