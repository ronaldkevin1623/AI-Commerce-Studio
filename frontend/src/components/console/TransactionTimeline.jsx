import { Box, Typography, Stack } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import AutorenewIcon from "@mui/icons-material/Autorenew";

const STEPS = [
  { key: "intent", label: "Intent parsed" },
  { key: "match", label: "Product matched" },
  { key: "risk_gate", label: "Risk check passed" },
  { key: "order_created", label: "Razorpay order created" },
  { key: "payment_confirmed", label: "Payment confirmed" },
];

/**
 * `completedKeys` is a Set of step keys already reached.
 * `activeKey` (optional) shows a spinner on that one step.
 */
export default function TransactionTimeline({ completedKeys = new Set(), activeKey }) {
  return (
    <Box>
      <Typography
        variant="overline"
        color="text.secondary"
        sx={{ letterSpacing: 1, mb: 1.5, display: "block" }}
      >
        Transaction
      </Typography>

      <Stack spacing={1.25}>
        {STEPS.map((step) => {
          const done = completedKeys.has(step.key);
          const active = activeKey === step.key;
          return (
            <Stack key={step.key} direction="row" alignItems="center" spacing={1}>
              {done ? (
                <CheckCircleIcon sx={{ fontSize: 17, color: "success.main" }} />
              ) : active ? (
                <AutorenewIcon sx={{ fontSize: 17, color: "primary.light" }} className="spin" />
              ) : (
                <RadioButtonUncheckedIcon sx={{ fontSize: 17, color: "text.secondary", opacity: 0.4 }} />
              )}
              <Typography
                variant="body2"
                sx={{ color: done || active ? "text.primary" : "text.secondary" }}
              >
                {step.label}
              </Typography>
            </Stack>
          );
        })}
      </Stack>

      <style>{`
        .spin { animation: cartpilot-spin 1s linear infinite; }
        @keyframes cartpilot-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </Box>
  );
}