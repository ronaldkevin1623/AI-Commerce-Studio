import { Box, Stack, Typography } from "@mui/material";
import CampaignOutlinedIcon from "@mui/icons-material/CampaignOutlined";

/**
 * Promoted products, offered beside the answer and never inside it.
 *
 * Kept visually separate on purpose. The results above are the agent's
 * answer to what was asked; this is a merchant paying to put a complement
 * in front of somebody, and the two are different kinds of thing. A
 * sponsored card mixed into the ranked list would look like a
 * recommendation, so it sits below a rule, in a quieter frame, under a
 * label that says what it is before anyone has to work it out.
 *
 * The disclosure text comes from the server rather than being written here,
 * so what the shopper is told and what the backend actually did cannot
 * drift apart.
 */
export default function SponsoredSlot({ payload, onOpen }) {
  const items = payload?.items ?? [];
  if (!items.length) return null;

  return (
    <Box
      sx={{
        mt: 2.5,
        pt: 2,
        borderTop: "1px solid",
        borderColor: "divider",
      }}
    >
      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 0.25 }}>
        <CampaignOutlinedIcon sx={{ fontSize: 14, color: "text.disabled" }} />
        <Typography
          variant="caption"
          sx={{
            color: "text.disabled", fontWeight: 700, fontSize: 10.5,
            letterSpacing: "0.08em", textTransform: "uppercase",
          }}
        >
          {payload.heading}
        </Typography>
      </Stack>

      <Typography
        variant="caption"
        sx={{ color: "text.secondary", display: "block", mb: 1.25, lineHeight: 1.6, maxWidth: 620 }}
      >
        {payload.disclosure}
      </Typography>

      <Stack direction="row" spacing={1.25} sx={{ flexWrap: "wrap", gap: 1.25 }}>
        {items.map((item) => (
          <Box
            key={item.id}
            onClick={() => onOpen?.(item, items)}
            sx={{
              width: 260,
              p: 1.25,
              borderRadius: 1.5,
              border: "1px dashed",
              borderColor: "rgba(148,163,184,0.4)",
              bgcolor: "rgba(148,163,184,0.05)",
              cursor: onOpen ? "pointer" : "default",
              transition: "border-color 140ms, background-color 140ms",
              "&:hover": onOpen
                ? { borderColor: "rgba(148,163,184,0.7)", bgcolor: "rgba(148,163,184,0.09)" }
                : undefined,
            }}
          >
            <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
              {item.image && (
                <Box
                  component="img"
                  src={item.image}
                  alt=""
                  sx={{
                    width: 40, height: 40, borderRadius: 1, objectFit: "cover",
                    flexShrink: 0, border: "1px solid", borderColor: "divider",
                  }}
                />
              )}
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  variant="body2"
                  noWrap
                  sx={{ fontSize: 12.5, fontWeight: 500 }}
                >
                  {item.name}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{ color: "text.secondary", fontSize: 11.5, fontVariantNumeric: "tabular-nums" }}
                >
                  ₹{(item.price_paise / 100).toLocaleString("en-IN")}
                  {(item.stock ?? 0) > 0 ? " · in stock" : ""}
                </Typography>
              </Box>
            </Stack>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
