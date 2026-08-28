import { Box, Typography, Stack } from "@mui/material";

/**
 * The core differentiator, rendered as an actual lock illustration
 * rather than a plain colored badge. Same base icon across all three
 * states — only color and posture change, so the shift reads
 * instantly without new visual vocabulary to learn.
 */
const STATES = {
  idle: {
    label: "Waiting",
    sub: "No purchase in progress",
    color: "#6B7280",
    bg: "rgba(107,114,128,0.12)",
  },
  allowed: {
    label: "Open",
    sub: "Action passed every check",
    color: "#22C55E",
    bg: "rgba(34,197,94,0.12)",
  },
  escalated: {
    label: "Holding",
    sub: "Waiting on human sign-off",
    color: "#F59E0B",
    bg: "rgba(245,158,11,0.12)",
  },
  blocked: {
    label: "Shut",
    sub: "Rule violation, action refused",
    color: "#EF4444",
    bg: "rgba(239,68,68,0.12)",
  },
};

function LockIcon({ state, color }) {
  // Shackle position + accent shifts per state: lifted+open, lifted+pulsing, closed+crossed
  if (state === "allowed") {
    return (
      <svg width="40" height="40" viewBox="0 0 56 56">
        <rect x="8" y="26" width="40" height="22" rx="4" fill="none" stroke={color} strokeWidth="2.5" />
        <path d="M18 26 V18 a10 10 0 0 1 20 0 v3" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
        <circle cx="28" cy="36" r="3" fill={color} />
      </svg>
    );
  }
  if (state === "escalated") {
    return (
      <svg width="40" height="40" viewBox="0 0 56 56">
        <rect x="8" y="26" width="40" height="22" rx="4" fill="none" stroke={color} strokeWidth="2.5" />
        <path d="M18 26 V18 a10 10 0 0 1 20 0 v8" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
        <circle cx="28" cy="36" r="3" fill={color} />
        <circle cx="28" cy="6" r="3" fill={color}>
          <animate attributeName="opacity" values="1;0.25;1" dur="1.1s" repeatCount="indefinite" />
        </circle>
      </svg>
    );
  }
  if (state === "blocked") {
    return (
      <svg width="40" height="40" viewBox="0 0 56 56">
        <rect x="8" y="26" width="40" height="22" rx="4" fill="none" stroke={color} strokeWidth="2.5" />
        <path d="M18 26 V18 a10 10 0 0 1 20 0 v8" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
        <circle cx="28" cy="36" r="3" fill={color} />
        <path d="M23 31 L33 41 M33 31 L23 41" stroke={color} strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }
  // idle
  return (
    <svg width="40" height="40" viewBox="0 0 56 56">
      <rect x="8" y="26" width="40" height="22" rx="4" fill="none" stroke={color} strokeWidth="2" opacity="0.6" />
      <path d="M18 26 V18 a10 10 0 0 1 20 0 v8" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" opacity="0.6" />
      <circle cx="28" cy="36" r="3" fill={color} opacity="0.6" />
    </svg>
  );
}

export default function RiskGateIndicator({ state = "idle", reason }) {
  const config = STATES[state] || STATES.idle;

  return (
    <Box sx={{ bgcolor: config.bg, borderRadius: 2, p: 2, transition: "background-color 0.3s" }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
        <LockIcon state={state} color={config.color} />
        <Box>
          <Typography variant="body2" fontWeight={700} sx={{ color: config.color }}>
            {config.label}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {reason || config.sub}
          </Typography>
        </Box>
      </Stack>
    </Box>
  );
}