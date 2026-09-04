import { useState } from "react";
import { Box, Button, Collapse, Dialog, Stack, TextField, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import MyLocationIcon from "@mui/icons-material/MyLocation";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import LocalShippingOutlinedIcon from "@mui/icons-material/LocalShippingOutlined";
import CreditCardOutlinedIcon from "@mui/icons-material/CreditCardOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";

import { useDeliveryLocation } from "../../hooks/useDeliveryLocation";
import PolicyCheck from "./PolicyCheck";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const shortDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : null;

function Row({ icon, label, children, action }) {
  return (
    <Box sx={{ px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
      <Stack direction="row" spacing={1.25} sx={{ alignItems: "flex-start" }}>
        <Box sx={{ mt: "1px", flexShrink: 0, color: "text.secondary", display: "flex" }}>{icon}</Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" sx={{ color: "text.secondary", display: "block" }}>
            {label}
          </Typography>
          {children}
        </Box>
        {action}
      </Stack>
    </Box>
  );
}

/**
 * The checkout sheet.
 *
 * Modelled on the reference, with two honest departures. The reference shows
 * a saved card ("VISA ····4242"); AI Commerce Studio has no stored payment
 * instrument and never sees card details — Razorpay Checkout collects them —
 * so this states that rather than displaying a card that doesn't exist. And
 * the delivery address is genuinely captured from the device or typed by
 * hand; there is no pre-filled address, because a shipping address nobody
 * confirmed is the worst possible thing to invent on a checkout screen.
 */
export default function CheckoutSheet({ open, product, onClose, onPay, busy, error }) {
  const { location, status, error: locError, share, setManual } = useDeliveryLocation();
  const [manualOpen, setManualOpen] = useState(false);
  const [line1, setLine1] = useState("");
  const [city, setCity] = useState("");
  const [postcode, setPostcode] = useState("");

  if (!product) return null;

  const shipping = product.shipping_cost_paise || 0;
  const total = (product.price_paise || 0) + shipping;
  const hasAddress = Boolean(location);

  const saveManual = () => {
    if (!line1.trim() || !city.trim()) return;
    setManual(line1.trim(), city.trim(), postcode.trim());
    setManualOpen(false);
  };

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      maxWidth="xs"
      fullWidth
      slotProps={{
        paper: {
          sx: {
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 3,
            backgroundImage: "none",
            overflow: "hidden",
          },
        },
      }}
    >
      <Stack
        direction="row"
        sx={{
          alignItems: "center", justifyContent: "space-between",
          px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider",
        }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0 }}>
          {product.image && (
            <Box component="img" src={product.image} alt=""
              sx={{ width: 26, height: 26, borderRadius: 1, objectFit: "cover", bgcolor: "#fff" }} />
          )}
          <Typography variant="body2" fontWeight={600} noWrap>
            {product.name}
          </Typography>
        </Stack>
        {!busy && (
          <CloseIcon onClick={onClose} sx={{ fontSize: 18, color: "text.secondary", cursor: "pointer", flexShrink: 0 }} />
        )}
      </Stack>

      {/* Ship to */}
      <Row
        icon={<PlaceOutlinedIcon sx={{ fontSize: 17 }} />}
        label="Ship to"
        action={
          hasAddress ? (
            <Button size="small" onClick={() => setManualOpen((o) => !o)}
              sx={{ fontSize: 11.5, color: "text.secondary", minWidth: 0 }}>
              Change
            </Button>
          ) : null
        }
      >
        {hasAddress ? (
          <>
            <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
              {[location.address?.line1, location.address?.city, location.address?.postcode]
                .filter(Boolean).join(", ") || "Location captured"}
            </Typography>
            {location.lat != null && (
              <Typography variant="caption" sx={{ color: "text.secondary", fontFamily: "monospace", fontSize: 10.5 }}>
                {location.lat.toFixed(5)}, {location.lon.toFixed(5)} · ±{location.accuracy}m
              </Typography>
            )}
          </>
        ) : (
          <Stack spacing={1} sx={{ mt: 0.5 }}>
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                variant="outlined"
                disabled={status === "locating"}
                onClick={share}
                startIcon={<MyLocationIcon sx={{ fontSize: 15 }} />}
                sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" }, fontSize: 12 }}
              >
                {status === "locating" ? "Locating…" : "Share my location"}
              </Button>
              <Button size="small" onClick={() => setManualOpen((o) => !o)}
                sx={{ color: "text.secondary", fontSize: 12 }}>
                Type it
              </Button>
            </Stack>
            {locError && (
              <Typography variant="caption" sx={{ color: "warning.main" }}>
                {locError}
              </Typography>
            )}
          </Stack>
        )}

        <Collapse in={manualOpen}>
          <Stack spacing={1} sx={{ mt: 1.25 }}>
            <TextField size="small" placeholder="Address line" value={line1}
              onChange={(e) => setLine1(e.target.value)}
              slotProps={{ input: { sx: { fontSize: 13 } } }} />
            <Stack direction="row" spacing={1}>
              <TextField size="small" placeholder="City" value={city}
                onChange={(e) => setCity(e.target.value)}
                slotProps={{ input: { sx: { fontSize: 13 } } }} />
              <TextField size="small" placeholder="PIN" value={postcode}
                onChange={(e) => setPostcode(e.target.value)}
                sx={{ width: 110 }} slotProps={{ input: { sx: { fontSize: 13 } } }} />
            </Stack>
            <Button size="small" variant="contained" onClick={saveManual}
              disabled={!line1.trim() || !city.trim()}
              sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" }, alignSelf: "flex-start", fontSize: 12 }}>
              Use this address
            </Button>
          </Stack>
        </Collapse>
      </Row>

      {/* Shipping */}
      <Row icon={<LocalShippingOutlinedIcon sx={{ fontSize: 17 }} />} label="Shipping method">
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
          {shipping ? `${inr(shipping)} — seller's shipping` : "Free delivery — seller's shipping"}
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          {product.delivery_estimate_from
            ? `eBay estimates ${shortDate(product.delivery_estimate_from)}${
                product.delivery_estimate_to &&
                shortDate(product.delivery_estimate_to) !== shortDate(product.delivery_estimate_from)
                  ? `–${shortDate(product.delivery_estimate_to)}`
                  : ""
              } — an estimate, not a tracked shipment`
            : "No delivery estimate reported for this listing"}
        </Typography>
      </Row>

      {/* Payment */}
      <Row icon={<CreditCardOutlinedIcon sx={{ fontSize: 17 }} />} label="Payment method">
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
          Chosen at Razorpay checkout
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          AI Commerce Studio never sees or stores card details. Cards are rejected on this test
          account — use <strong>Netbanking</strong>.
        </Typography>
      </Row>

      {/* Total */}
      <Box sx={{ px: 2, py: 1.75 }}>
        <Stack direction="row" sx={{ justifyContent: "space-between", mb: 0.5 }}>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>Item</Typography>
          <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums" }}>
            {inr(product.price_paise)}
          </Typography>
        </Stack>
        <Stack direction="row" sx={{ justifyContent: "space-between", mb: 1 }}>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>Delivery</Typography>
          <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums" }}>
            {shipping ? inr(shipping) : "Free"}
          </Typography>
        </Stack>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "baseline" }}>
          <Typography variant="body2" fontWeight={700}>Total</Typography>
          <Typography variant="body1" fontWeight={700} sx={{ fontVariantNumeric: "tabular-nums" }}>
            {inr(total)}
          </Typography>
        </Stack>

        {/* Only the item price goes through Razorpay — postage is the
            seller's and was never part of the charge. Saying so beats a
            total that quietly disagrees with the receipt. */}
        {shipping > 0 && (
          <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.75 }}>
            {inr(product.price_paise)} is charged through Razorpay. Delivery is the seller's
            and is collected by eBay, not here.
          </Typography>
        )}

        {/* The bound, before the money moves rather than after it is
            refused. Only the item price is charged, so that is the amount
            judged — showing the total here would test a number Razorpay
            never sees. */}
        <Box sx={{ mt: 1.75 }}>
          <PolicyCheck amountPaise={product.price_paise} />
        </Box>

        {error && (
          <Typography variant="caption" sx={{ color: "error.main", display: "block", mt: 1 }}>
            {error}
          </Typography>
        )}

        {/* Never a dead button.
            This used to be a disabled "Pay now" whose only explanation was a
            grey caption underneath it, so clicking the obvious primary
            action did nothing at all and the checkout looked broken —
            indistinguishable from Razorpay failing to open. Without an
            address it now stays live and opens the address form instead, so
            the primary button always moves you forward. */}
        <Button
          fullWidth
          variant="contained"
          disabled={busy}
          onClick={() => {
            if (!hasAddress) {
              setManualOpen(true);
              return;
            }
            onPay?.(location);
          }}
          sx={{ mt: 1.75, py: 1.15, boxShadow: "none", "&:hover": { boxShadow: "none" } }}
        >
          {busy
            ? "Opening Razorpay…"
            : hasAddress
              ? `Pay now · ${inr(product.price_paise)}`
              : "Add a delivery address to continue"}
        </Button>

        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", justifyContent: "center", mt: 1.25 }}>
          <LockOutlinedIcon sx={{ fontSize: 12, color: "text.secondary" }} />
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 10.5 }}>
            Razorpay test mode · gated and signed before charge
          </Typography>
        </Stack>
      </Box>
    </Dialog>
  );
}
