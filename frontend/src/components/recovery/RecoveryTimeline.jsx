import { Box, Typography, Stack } from "@mui/material";
import CircleIcon from "@mui/icons-material/Circle";
import CancelIcon from "@mui/icons-material/Cancel";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";

function formatTime(timestamp) {
  if (!timestamp?.toDate) return "—";
  return timestamp.toDate().toLocaleTimeString();
}

export default function RecoveryTimeline({ failure, recovery }) {
  const steps = [
    {
      icon: <CancelIcon sx={{ fontSize: 16, color: "error.main" }} />,
      label: "Payment capture failed",
      time: formatTime(failure.timestamp),
    },
    {
      icon: <CircleIcon sx={{ fontSize: 8, color: "text.secondary", ml: "4px" }} />,
      label: "Failure logged to audit trail with reason, no silent retry attempted",
      time: null,
    },
  ];

  if (recovery) {
    steps.push({
      icon: <CheckCircleIcon sx={{ fontSize: 16, color: "success.main" }} />,
      label: "Follow-up payment confirmed by Razorpay",
      time: formatTime(recovery.timestamp),
    });
  }

  return (
    <Box>
      <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1, mb: 1.5, display: "block" }}>
        Recovery timeline
      </Typography>

      <Stack spacing={0}>
        {steps.map((step, i) => (
          <Stack key={i} direction="row" spacing={1.5}>
            <Stack alignItems="center">
              {step.icon}
              {i < steps.length - 1 && (
                <Box sx={{ width: "1px", flex: 1, minHeight: 20, bgcolor: "divider", my: 0.5 }} />
              )}
            </Stack>
            <Box sx={{ pb: 2 }}>
              <Typography variant="body2">{step.label}</Typography>
              {step.time && (
                <Typography variant="caption" color="text.secondary">{step.time}</Typography>
              )}
            </Box>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}