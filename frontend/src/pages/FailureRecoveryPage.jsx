import { Box, Typography } from "@mui/material";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { useFailureRecovery } from "../hooks/useFailureRecovery";
import PageBanner from "../components/shared/PageBanner";
import FailureCard from "../components/recovery/FailureCard";
import RecoveryTimeline from "../components/recovery/RecoveryTimeline";

export default function FailureRecoveryPage() {
  const { failure, recovery, loading } = useFailureRecovery();

  return (
    <Box>
      <PageBanner
        title="Failure recovery"
        subtitle="A real, logged payment failure and what happened next — pulled live from the audit trail, not staged"
      />

      <Box sx={{ maxWidth: 900, mx: "auto", px: 3, py: 4 }}>
        {loading && (
          <Typography variant="body2" color="text.secondary">Checking for logged failures…</Typography>
        )}

        {!loading && !failure && (
          <Box sx={{ bgcolor: "background.paper", border: "1px dashed", borderColor: "divider", borderRadius: 2.5, p: 4, textAlign: "center" }}>
            <InfoOutlinedIcon sx={{ fontSize: 22, color: "text.secondary", mb: 1.5 }} />
            <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>
              No failure logged yet
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480, mx: "auto", mb: 2 }}>
              This page shows a real failure the moment one happens — nothing here is
              scripted. To see it populate, run a request in the Console, and when Razorpay's
              checkout opens, complete the test card details, then click{" "}
              <b>"Failure"</b> on the mock bank confirmation screen instead of "Success."
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontFamily: "monospace" }}>
              Test card: 4111 1111 1111 1111 · any future expiry · any CVV
            </Typography>
          </Box>
        )}

        {!loading && failure && (
          <>
            <Box sx={{ bgcolor: "background.paper", border: "1px solid", borderColor: "divider", borderRadius: 2.5, p: 2.5 }}>
              <FailureCard failure={failure} recovery={recovery} />
            </Box>
            <Box sx={{ bgcolor: "background.paper", border: "1px solid", borderColor: "divider", borderRadius: 2.5, p: 2.5, mt: 2.5 }}>
              <RecoveryTimeline failure={failure} recovery={recovery} />
            </Box>
            <Box sx={{ mt: 2, display: "flex", alignItems: "center", gap: 1, px: 0.5 }}>
              <InfoOutlinedIcon sx={{ fontSize: 15, color: "text.secondary" }} />
              <Typography variant="caption" color="text.secondary">
                No silent retries. Every recovery step is logged to the audit trail.
              </Typography>
            </Box>
          </>
        )}
      </Box>
    </Box>
  );
}