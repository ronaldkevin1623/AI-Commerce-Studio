import { Box, Stack, Tooltip, Typography } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";

/**
 * The order's real progress.
 *
 * Two of these stages are genuinely observed — Razorpay tells us when an
 * order is created and when a payment is captured, and both timestamps come
 * out of Firestore. The other two are drawn dashed and greyed because
 * AI Commerce Studio has no fulfilment integration: nothing notifies the eBay seller
 * and no carrier reports back. Filling them in with plausible dates is the
 * single most tempting lie this screen could tell, so the stepper is built
 * to make their absence visible rather than to hide it.
 */

const TONE = {
  done: { ring: "#22C55E", fill: "rgba(34,197,94,0.16)", text: "#22C55E" },
  active: { ring: "#3B82F6", fill: "rgba(59,130,246,0.18)", text: "#60A5FA" },
  pending: { ring: "rgba(255,255,255,0.18)", fill: "transparent", text: "#9AA3B2" },
  failed: { ring: "#EF4444", fill: "rgba(239,68,68,0.16)", text: "#EF4444" },
  not_tracked: { ring: "rgba(255,255,255,0.14)", fill: "transparent", text: "#5B6474", dashed: true },
};

function formatWhen(stage) {
  if (stage.state === "not_tracked") return "Not tracked";
  if (!stage.at) return stage.state === "failed" ? "Did not complete" : "Not yet";
  return new Date(stage.at).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function TrackingStepper({ stages = [] }) {
  if (!stages.length) return null;

  return (
    <Box
      sx={{
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2.5,
        px: { xs: 2, md: 4 },
        py: 3.5,
      }}
    >
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: `repeat(${stages.length}, 1fr)`,
          position: "relative",
        }}
      >
        {stages.map((stage, index) => {
          const tone = TONE[stage.state] ?? TONE.pending;
          const next = stages[index + 1];
          // The connector takes the weaker of the two stages it joins, so
          // the line goes dashed exactly where knowledge runs out.
          const connectorSolid = next && stage.state === "done" && next.state !== "not_tracked";

          return (
            <Box key={stage.key} sx={{ position: "relative", textAlign: "center" }}>
              {next && (
                <Box
                  aria-hidden
                  sx={{
                    position: "absolute",
                    top: 13,
                    left: "calc(50% + 16px)",
                    right: "calc(-50% + 16px)",
                    height: 0,
                    borderTop: "1.5px",
                    borderTopStyle: connectorSolid ? "solid" : "dashed",
                    borderColor: connectorSolid ? "#22C55E" : "rgba(255,255,255,0.14)",
                  }}
                />
              )}

              <Tooltip title={stage.detail ?? ""} placement="top" enterDelay={300}>
                <Box
                  sx={{
                    width: 28,
                    height: 28,
                    mx: "auto",
                    borderRadius: "50%",
                    border: "1.5px",
                    borderStyle: tone.dashed ? "dashed" : "solid",
                    borderColor: tone.ring,
                    bgcolor: tone.fill,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    position: "relative",
                    zIndex: 1,
                    cursor: "default",
                  }}
                >
                  {stage.state === "done" ? (
                    <CheckIcon sx={{ fontSize: 15, color: tone.text }} />
                  ) : stage.state === "failed" ? (
                    <CloseIcon sx={{ fontSize: 15, color: tone.text }} />
                  ) : (
                    <Typography sx={{ fontSize: 12, fontWeight: 600, color: tone.text }}>
                      {index + 1}
                    </Typography>
                  )}
                </Box>
              </Tooltip>

              <Typography
                variant="body2"
                sx={{ mt: 1.25, fontWeight: 600, color: tone.text, fontSize: 13 }}
              >
                {stage.label}
              </Typography>
              <Typography
                variant="caption"
                sx={{ color: "text.secondary", display: "block", mt: 0.25 }}
              >
                {formatWhen(stage)}
              </Typography>
            </Box>
          );
        })}
      </Box>

      <Stack
        direction="row"
        spacing={1}
        sx={{ mt: 3, pt: 2, borderTop: "1px solid", borderColor: "divider", alignItems: "flex-start" }}
      >
        <Box
          sx={{
            width: 14,
            mt: "7px",
            borderTop: "1.5px dashed",
            borderColor: "rgba(255,255,255,0.24)",
            flexShrink: 0,
          }}
        />
        <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.6 }}>
          Dashed stages aren't tracked. AI Commerce Studio pays through Razorpay but has no fulfilment
          integration — eBay's Browse API is read-only, nothing notifies the seller, and no
          carrier reports back. Showing packed/in-transit dates here would mean inventing them.
        </Typography>
      </Stack>
    </Box>
  );
}
