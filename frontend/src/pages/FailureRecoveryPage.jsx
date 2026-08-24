import { Box, Typography } from "@mui/material";

export default function FailureRecoveryPage() {
  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>
      <Typography variant="h2" gutterBottom>Failure recovery</Typography>
      <Typography variant="body2" color="text.secondary">
        Scenario walkthrough goes here — build after the core pipeline works end-to-end.
      </Typography>
    </Box>
  );
}