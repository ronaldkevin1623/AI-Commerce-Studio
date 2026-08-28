import { Dialog, Button, Typography, Box } from "@mui/material";

/**
 * Guards against silently walking away from an in-flight purchase.
 * Deliberately restrained: no alarm colours, no icons — this is a
 * routine decision, not an emergency, and the visual weight should
 * match that.
 */
export default function AbandonRunDialog({ open, stage, onContinue, onTerminate }) {
  const stageCopy = {
    selection: "waiting for you to choose a product",
    approval: "waiting for you to approve a purchase",
    payment: "waiting for payment to complete",
    running: "still working on your request",
  };

  return (
    <Dialog
      open={open}
      onClose={onContinue}
      maxWidth="xs"
      fullWidth
      PaperProps={{
        sx: {
          bgcolor: "background.paper",
          backgroundImage: "none",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 3,
        },
      }}
    >
      <Box sx={{ px: 3, pt: 2.75, pb: 2.5 }}>
        <Typography variant="body1" fontWeight={600} sx={{ mb: 1.25 }}>
          End this purchase?
        </Typography>

        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>
          The agent is {stageCopy[stage] ?? stageCopy.running}. Nothing has been
          charged, and the abandonment is recorded in the audit trail.
        </Typography>
      </Box>

      <Box
        sx={{
          display: "flex",
          width: "100%",
          justifyContent: "flex-end",
          alignItems: "center",
          gap: 1,
          px: 3,
          py: 2,
          borderTop: "1px solid",
          borderColor: "divider",
        }}
      >
        <Button
          onClick={onContinue}
          sx={{
            textTransform: "none",
            fontWeight: 500,
            borderRadius: 2,
            px: 2,
            py: 0.75,
            color: "text.secondary",
            "&:hover": { bgcolor: "action.hover", color: "text.primary" },
          }}
        >
          Keep going
        </Button>
        <Button
          variant="contained"
          onClick={onTerminate}
          sx={{
            textTransform: "none",
            fontWeight: 600,
            borderRadius: 2,
            px: 2.5,
            py: 0.75,
            boxShadow: "none",
            "&:hover": { boxShadow: "none" },
          }}
        >
          End run
        </Button>
      </Box>
    </Dialog>
  );
}