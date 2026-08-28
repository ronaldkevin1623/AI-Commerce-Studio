import { Box, Chip, Stack, Tooltip, Typography } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

/**
 * The signed mandate chain behind a purchase, rendered as a chain.
 *
 * AP2's whole idea is that each link is cryptographically bound to the one
 * before it, so this shows the bindings rather than just a green tick: each
 * card carries its own hash, and the connector states which hash the next
 * link committed to. The disclosure at the bottom is load-bearing — this
 * proves the agent kept to the approved constraints, not that any seller
 * agreed to anything, and a lock icon without that caveat would overclaim.
 */

const LINK_TONE = {
  "mandate.checkout.open.1": { label: "Constraints the person approved", color: "#60A5FA" },
  "checkout.cart.1": { label: "The cart, priced at approval", color: "#A78BFA" },
  "mandate.checkout.1": { label: "Cart bound to intent", color: "#22C55E" },
};

function Hash({ value }) {
  if (!value) return null;
  return (
    <Tooltip title={value} placement="top">
      <Box
        component="span"
        sx={{
          fontFamily: "monospace",
          fontSize: 10.5,
          color: "text.secondary",
          cursor: "default",
        }}
      >
        {value.slice(0, 16)}…
      </Box>
    </Tooltip>
  );
}

export default function MandateChainCard({ chain, verification }) {
  if (!chain?.links?.length) return null;
  const ok = verification?.ok;

  return (
    <Box
      sx={{
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: ok ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)",
        borderRadius: 2.5,
        p: 2,
      }}
    >
      <Stack
        direction="row"
        sx={{ alignItems: "center", justifyContent: "space-between", gap: 2, mb: 2 }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <LockOutlinedIcon sx={{ fontSize: 16, color: ok ? "success.main" : "error.main" }} />
          <Typography variant="body2" fontWeight={600}>
            Mandate chain
          </Typography>
          <Chip
            size="small"
            label={chain.algorithm}
            sx={{
              height: 19,
              bgcolor: "rgba(255,255,255,0.05)",
              color: "text.secondary",
              "& .MuiChip-label": { px: 0.8, fontSize: 10 },
            }}
          />
        </Stack>
        <Typography
          variant="caption"
          sx={{ color: ok ? "success.main" : "error.main", fontWeight: 600 }}
        >
          {ok ? "Verified" : verification?.reason ?? "Not verified"}
        </Typography>
      </Stack>

      {/* The chain itself */}
      <Stack spacing={0}>
        {chain.links.map((link, i) => {
          const tone = LINK_TONE[link.vct] ?? { label: link.label, color: "#9AA3B2" };
          const next = chain.links[i + 1];
          return (
            <Box key={link.vct + i}>
              <Box
                sx={{
                  border: "1px solid",
                  borderColor: "divider",
                  borderLeft: "2px solid",
                  borderLeftColor: tone.color,
                  borderRadius: 1.5,
                  px: 1.5,
                  py: 1.25,
                }}
              >
                <Stack
                  direction="row"
                  sx={{ alignItems: "baseline", justifyContent: "space-between", gap: 2 }}
                >
                  <Typography variant="caption" sx={{ fontWeight: 600, color: "text.primary" }}>
                    {link.label}
                  </Typography>
                  <Box
                    component="span"
                    sx={{ fontFamily: "monospace", fontSize: 10, color: "text.secondary" }}
                  >
                    {link.vct}
                  </Box>
                </Stack>
                <Typography variant="caption" sx={{ color: "text.secondary", display: "block" }}>
                  {tone.label} · issued by {link.issuer}
                </Typography>
                <Box sx={{ mt: 0.5 }}>
                  <Hash value={link.hash} />
                </Box>
              </Box>

              {next && (
                <Stack
                  direction="row"
                  spacing={0.75}
                  sx={{ alignItems: "center", pl: 2, py: 0.5 }}
                >
                  <Box
                    sx={{
                      width: 0,
                      height: 14,
                      borderLeft: "1.5px dashed",
                      borderColor: "rgba(255,255,255,0.2)",
                    }}
                  />
                  <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 10.5 }}>
                    committed to by the next link
                  </Typography>
                </Stack>
              )}
            </Box>
          );
        })}
      </Stack>

      {/* Each individual check, so a failure names itself */}
      {verification?.checks?.length > 0 && (
        <Stack spacing={0.5} sx={{ mt: 2 }}>
          {verification.checks.map((check) => (
            <Stack key={check.name} direction="row" spacing={1} sx={{ alignItems: "center" }}>
              {check.ok ? (
                <CheckIcon sx={{ fontSize: 13, color: "success.main", flexShrink: 0 }} />
              ) : (
                <CloseIcon sx={{ fontSize: 13, color: "error.main", flexShrink: 0 }} />
              )}
              <Typography
                variant="caption"
                sx={{ color: check.ok ? "text.secondary" : "error.main", flexShrink: 0 }}
              >
                {check.name}
              </Typography>
              <Typography
                variant="caption"
                sx={{ color: "text.secondary", fontSize: 10.5, minWidth: 0 }}
                noWrap
              >
                {check.detail}
              </Typography>
            </Stack>
          ))}
        </Stack>
      )}

      {chain.disclosure && (
        <Stack
          direction="row"
          spacing={1}
          sx={{
            mt: 2,
            pt: 1.5,
            borderTop: "1px solid",
            borderColor: "divider",
            alignItems: "flex-start",
          }}
        >
          <InfoOutlinedIcon sx={{ fontSize: 14, color: "warning.main", mt: "1px", flexShrink: 0 }} />
          <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.55 }}>
            {chain.disclosure}
          </Typography>
        </Stack>
      )}
    </Box>
  );
}
