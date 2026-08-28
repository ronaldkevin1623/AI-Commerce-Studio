import { Box, Stack, Typography } from "@mui/material";

import { inr } from "./format";

/**
 * Every figure here is arithmetic over values captured at purchase time.
 *
 * Delivery is eBay's real reported postage for that listing, which is
 * frequently ₹0 because US sellers bundle it — shown as "Free" rather than
 * a suspicious-looking zero. Discount is the gap between the listing's own
 * original price and what it sold for, and only appears when eBay actually
 * reported one.
 */

function Line({ label, value, strong, muted }) {
  return (
    <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "baseline", gap: 2 }}>
      <Typography
        variant="body2"
        sx={{ color: strong ? "text.primary" : "text.secondary", fontWeight: strong ? 600 : 400 }}
      >
        {label}
      </Typography>
      <Typography
        variant="body2"
        sx={{
          fontWeight: strong ? 700 : 600,
          color: muted ? "text.secondary" : "text.primary",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </Typography>
    </Stack>
  );
}

function Card({ children }) {
  return (
    <Box
      sx={{
        flex: 1,
        minWidth: 0,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2.5,
        p: 2.5,
      }}
    >
      <Stack spacing={1.5}>{children}</Stack>
    </Box>
  );
}

export default function OrderTotals({ totals, priceIsConverted }) {
  if (!totals) return null;
  const freeShipping = (totals.shipping_paise ?? 0) === 0;

  return (
    <Box>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2.5}>
        <Card>
          <Line
            label="Discount"
            value={totals.discount_paise ? `− ${inr(totals.discount_paise)}` : inr(0)}
            muted={!totals.discount_paise}
          />
          <Line
            label="Delivery"
            value={freeShipping ? "Free" : inr(totals.shipping_paise)}
            muted={freeShipping}
          />
        </Card>

        <Card>
          <Line label="Subtotal" value={inr(totals.subtotal_paise)} />
          <Line label="Total" value={inr(totals.total_paise)} strong />
        </Card>
      </Stack>

      {/* What Razorpay was actually asked for, when it differs from the
          total — postage is reported by eBay but never went through
          checkout, and pretending otherwise would misstate the charge. */}
      {totals.charged_paise !== totals.total_paise && (
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 1.5 }}>
          {inr(totals.charged_paise)} was put through Razorpay checkout. Delivery is eBay's
          reported postage for the listing and was not part of that charge.
        </Typography>
      )}

      {priceIsConverted && (
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.75 }}>
          Prices converted from USD at a fixed approximate rate — eBay's Browse API has no India
          marketplace. Not a live forex lookup.
        </Typography>
      )}
    </Box>
  );
}
