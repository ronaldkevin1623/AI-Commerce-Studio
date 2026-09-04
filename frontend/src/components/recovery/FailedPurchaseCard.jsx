import { useState } from "react";
import { Box, Button, Chip, Collapse, Stack, Typography } from "@mui/material";
import PaymentRails from "./PaymentRails";
import WarningAmberIcon from "@mui/icons-material/WarningAmberOutlined";
import ReplayIcon from "@mui/icons-material/Replay";
import CreditCardOutlinedIcon from "@mui/icons-material/CreditCardOutlined";
import CloseIcon from "@mui/icons-material/Close";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/**
 * A PURCHASE THAT FAILED, AND THE THING SOMEBODY STILL WANTS.
 *
 * The product is the point. "Your payment failed" is not actionable;
 * "your payment for the Braided USB-C Cable failed because this account
 * rejects foreign cards, and netbanking would work" is — and the difference
 * is entirely in whether the record kept hold of what was being bought.
 *
 * The second thing this card does is report what the agent did NOT do.
 * "Payment failed, retrying…" is what an unbounded agent says, and three
 * retries against a card that will never work is three attempts on
 * somebody's account. It stopped, named the bound, and handed the decision
 * back — which is what bounded autonomy looks like from the outside.
 *
 * The reason text is Razorpay's own, quoted rather than paraphrased, so this
 * page and the Razorpay dashboard cannot end up describing the same failure
 * differently.
 */
const ACTIONS = [
  { key: "retry", label: "Try again", Icon: ReplayIcon, primary: true },
  { key: "change_method", label: "Change payment method", Icon: CreditCardOutlinedIcon },
  { key: "cancel", label: "Cancel", Icon: CloseIcon },
];

export default function FailedPurchaseCard({ purchase, policy, onChoose, busy }) {
  // The rails belong to THIS failure, not to the page. As a standing block
  // they were a wall of text above everything else; opened on request they
  // are the answer to the question the button asks.
  const [railsOpen, setRailsOpen] = useState(false);
  if (!purchase) return null;
  const product = purchase.product ?? {};
  const error = purchase.error ?? {};

  return (
    <Box
      sx={{
        borderRadius: 2.5, border: "1px solid",
        borderColor: "rgba(248,113,113,0.32)",
        bgcolor: "rgba(248,113,113,0.05)",
        p: 2.25,
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.75 }}>
        <WarningAmberIcon sx={{ fontSize: 17, color: "#F87171" }} />
        <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: "#F87171" }}>
          Payment could not be completed
        </Typography>
        <Box sx={{ flex: 1 }} />
        {error.code && (
          <Chip size="small" label={error.code}
                sx={{ height: 19, fontSize: 10, fontFamily: "monospace",
                      bgcolor: "rgba(255,255,255,0.06)" }} />
        )}
      </Stack>

      {/* ── the thing somebody was buying ────────────────────────────── */}
      <Stack direction="row" spacing={1.75} sx={{ alignItems: "center", mb: 1.75 }}>
        <Box
          sx={{
            width: 58, height: 58, borderRadius: 1.5, flexShrink: 0,
            bgcolor: "rgba(255,255,255,0.05)", overflow: "hidden",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          {product.image ? (
            <Box component="img" src={product.image} alt=""
                 sx={{ width: "100%", height: "100%", objectFit: "cover" }} />
          ) : (
            <Typography sx={{ fontSize: 9.5, color: "text.disabled", textAlign: "center",
                              px: 0.5, lineHeight: 1.3 }}>
              No photo
            </Typography>
          )}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2"
                      sx={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.45 }}>
            {product.name}
          </Typography>
          <Stack direction="row" spacing={1.25} sx={{ alignItems: "baseline", mt: 0.35 }}>
            <Typography sx={{ fontSize: 14, fontWeight: 700 }}>
              {inr(purchase.amount_paise ?? product.price_paise)}
            </Typography>
            {purchase.razorpay_order_id && (
              <Typography sx={{ fontSize: 10.5, color: "text.disabled",
                                fontFamily: "monospace" }}>
                {purchase.razorpay_order_id}
              </Typography>
            )}
          </Stack>
        </Box>
      </Stack>

      {/* ── why, in Razorpay's own words ─────────────────────────────── */}
      <Typography variant="body2"
                  sx={{ fontSize: 13, lineHeight: 1.7, mb: 1.25 }}>
        {purchase.summary}
      </Typography>

      {/* ── what the agent did not do, and what enforces that ────────── */}
      <Box sx={{ pl: 1.5, borderLeft: "2px solid", borderColor: "rgba(255,255,255,0.14)",
                 mb: 2 }}>
        <Typography variant="caption"
                    sx={{ display: "block", color: "text.secondary",
                          lineHeight: 1.7, fontSize: 11.5 }}>
          {policy?.statement
            ?? "A failed payment is never retried automatically. The next attempt is a fresh, separately gated and separately logged action taken by a person."}
        </Typography>
        {policy?.enforced_by && (
          <Typography variant="caption"
                      sx={{ display: "block", color: "text.disabled", mt: 0.4,
                            fontSize: 10.5 }}>
            Enforced by: {policy.enforced_by}
          </Typography>
        )}
      </Box>

      {/* ── the decision, handed back ────────────────────────────────── */}
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
        {ACTIONS.map(({ key, label, Icon, primary }) => (
          <Button
            key={key}
            size="small"
            disabled={busy}
            variant={primary ? "contained" : "outlined"}
            startIcon={<Icon sx={{ fontSize: 15 }} />}
            onClick={() => {
              if (key === "change_method") { setRailsOpen((open) => !open); return; }
              onChoose?.(key, purchase);
            }}
            sx={{
              textTransform: "none", fontSize: 12.5,
              borderColor: primary ? undefined : "divider",
              boxShadow: "none", "&:hover": { boxShadow: "none" },
            }}
          >
            {label}
          </Button>
        ))}
      </Stack>

      <Collapse in={railsOpen}>
        <Box sx={{ mt: 1.75 }}>
          <PaymentRails
            card={{ border: "1px solid", borderColor: "divider",
                    borderRadius: 2, bgcolor: "rgba(0,0,0,0.25)", p: 1.75 }}
          />
        </Box>
      </Collapse>
    </Box>
  );
}
