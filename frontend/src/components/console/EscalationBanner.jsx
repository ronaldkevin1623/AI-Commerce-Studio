import { Box, Typography, Button, Stack } from "@mui/material";

export default function EscalationBanner({ onApprove, onDeny }) {
  return (
    <Box
      sx={{
        bgcolor: "rgba(245,158,11,0.12)",
        border: "1px solid",
        borderColor: "warning.main",
        borderRadius: 2,
        p: 2,
      }}
    >
      <Typography variant="body2" fontWeight={600} sx={{ mb: 1, color: "warning.main" }}>
        Waiting on your approval
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
        This order exceeds the auto-approve limit. Review before it proceeds to Razorpay.
      </Typography>
      <Stack direction="row" spacing={1.5}>
        <Button size="small" variant="contained" color="warning" onClick={onApprove}>
          Approve
        </Button>
        <Button size="small" variant="outlined" color="error" onClick={onDeny}>
          Deny
        </Button>
      </Stack>
    </Box>
  );
}