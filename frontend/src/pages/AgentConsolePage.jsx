import { useState } from "react";
import { Box, TextField, IconButton, Typography, Stack, Chip, Button } from "@mui/material";
import SendIcon from "@mui/icons-material/ArrowForward";
import { useAgentSocket } from "../hooks/useAgentSocket";

export default function AgentConsolePage() {
  const [input, setInput] = useState("");
  const { events, isRunning, pendingApproval, sendIntent, respondToEscalation } = useAgentSocket();

  const handleSend = () => {
    if (input.trim()) sendIntent(input.trim());
  };

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>
      <Stack direction="row" spacing={1} sx={{ mb: 3 }}>
        <TextField
          fullWidth
          size="small"
          placeholder="Wireless earbuds under ₹2000, fast delivery"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          disabled={isRunning}
        />
        <IconButton color="primary" onClick={handleSend} disabled={isRunning}>
          <SendIcon />
        </IconButton>
      </Stack>

      <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase" }}>
        Reasoning stream
      </Typography>

      <Stack spacing={1} sx={{ mt: 1 }}>
        {events.map((event, i) => (
          <Typography key={i} variant="body2" sx={{ fontFamily: "monospace" }}>
            [{event.type}] {JSON.stringify(event.payload)}
          </Typography>
        ))}
      </Stack>

      {pendingApproval && (
        <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
          <Chip label="Escalated — awaiting approval" color="warning" />
          <Button size="small" variant="contained" onClick={() => respondToEscalation(true)}>
            Approve
          </Button>
          <Button size="small" variant="outlined" color="error" onClick={() => respondToEscalation(false)}>
            Deny
          </Button>
        </Stack>
      )}
    </Box>
  );
}