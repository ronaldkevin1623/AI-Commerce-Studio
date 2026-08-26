import { Box, Typography, Stack } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import CheckIcon from "@mui/icons-material/Check";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";

function formatAmount(amountPaise) {
  if (amountPaise == null) return "—";
  return `₹${(amountPaise / 100).toLocaleString("en-IN")}`;
}

export default function FailureCard({ failure, recovery }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr auto 1fr" }, gap: 1.5, alignItems: "stretch" }}>
      <Box sx={{ bgcolor: "error.light", borderRadius: 2, p: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <CloseIcon sx={{ fontSize: 16, color: "error.main" }} />
          <Typography variant="caption" fontWeight={600} color="error.main" sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}>
            What failed
          </Typography>
        </Stack>
        <Typography variant="body2" sx={{ mb: 1.5 }}>{failure.reason}</Typography>
        <Box sx={{ bgcolor: "background.default", borderRadius: 1, p: 1, fontFamily: "monospace", fontSize: 11 }}>
          amount: {formatAmount(failure.amount_paise)}<br />
          order_id: {failure.order_id || "—"}
        </Box>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Typography sx={{ fontSize: 20, color: "text.secondary" }}>→</Typography>
      </Box>

      {recovery ? (
        <Box sx={{ bgcolor: "success.light", borderRadius: 2, p: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <CheckIcon sx={{ fontSize: 16, color: "success.main" }} />
            <Typography variant="caption" fontWeight={600} color="success.main" sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}>
              How it recovered
            </Typography>
          </Stack>
          <Typography variant="body2" sx={{ mb: 1.5 }}>
            A subsequent attempt was confirmed by Razorpay — logged as a fresh, verified payment, not an automatic retry.
          </Typography>
          <Box sx={{ bgcolor: "background.default", borderRadius: 1, p: 1, fontFamily: "monospace", fontSize: 11 }}>
            status: payment_confirmed<br />
            order_id: {recovery.order_id || "—"}
          </Box>
        </Box>
      ) : (
        <Box sx={{ bgcolor: "background.paper", border: "1px dashed", borderColor: "divider", borderRadius: 2, p: 2, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
          <HourglassEmptyIcon sx={{ fontSize: 18, color: "text.secondary", mb: 1 }} />
          <Typography variant="caption" color="text.secondary">
            No recovery yet — run another request and complete payment to see it logged here.
          </Typography>
        </Box>
      )}
    </Box>
  );
}