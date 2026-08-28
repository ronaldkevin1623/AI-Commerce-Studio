import { Box, Button, Dialog, Stack, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CloseIcon from "@mui/icons-material/Close";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * The post-payment confirmation.
 *
 * The map is a real OpenStreetMap embed centred on the coordinates the person
 * actually shared — free, no key, no account, and no invented pin. If they
 * typed an address instead of sharing a location there are no coordinates, so
 * the map is simply absent rather than dropped on a guessed city centre.
 *
 * The reference design has a "track package" button. There is nothing to
 * track: AI Commerce Studio has no fulfilment integration, so that space says what is
 * actually known instead of linking to a tracker that doesn't exist.
 */
export default function OrderConfirmation({ open, order, payment, location, onClose, onViewOrder }) {
  if (!order) return null;

  const lat = location?.lat;
  const lon = location?.lon;
  const hasCoords = lat != null && lon != null;
  // A small bounding box around the point keeps the embed readable.
  const bbox = hasCoords
    ? [lon - 0.008, lat - 0.005, lon + 0.008, lat + 0.005].join("%2C")
    : null;

  const addressLine = [
    location?.address?.line1,
    location?.address?.city,
    location?.address?.postcode,
  ].filter(Boolean).join(", ");

  return (
    <Dialog
      open={open}
      onClose={onClose}
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
        <Typography variant="caption" sx={{ color: "text.secondary", letterSpacing: 1 }}>
          ORDER SUMMARY
        </Typography>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Typography variant="body2" fontWeight={700} sx={{ fontVariantNumeric: "tabular-nums" }}>
            {inr(order.amount_paise)}
          </Typography>
          <CloseIcon onClick={onClose} sx={{ fontSize: 18, color: "text.secondary", cursor: "pointer" }} />
        </Stack>
      </Stack>

      <Box sx={{ px: 2.5, py: 2.5 }}>
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center", mb: 0.5 }}>
          <CheckCircleIcon sx={{ fontSize: 22, color: "success.main" }} />
          <Typography variant="h2" sx={{ fontSize: 18 }}>
            Payment confirmed
          </Typography>
        </Stack>
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 2 }}>
          Confirmation{" "}
          <Box component="span" sx={{ fontFamily: "monospace", color: "text.primary" }}>
            {payment?.razorpay_payment_id ?? order.razorpay_order_id}
          </Box>
        </Typography>

        {/* Real map, real coordinates, or nothing at all */}
        {hasCoords ? (
          <Box sx={{ borderRadius: 2.5, overflow: "hidden", border: "1px solid", borderColor: "divider", mb: 1 }}>
            <Box
              component="iframe"
              title="Delivery location"
              src={`https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat}%2C${lon}`}
              sx={{ width: "100%", height: 160, border: "none", display: "block" }}
            />
          </Box>
        ) : null}

        {addressLine && (
          <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 2 }}>
            Delivering to {addressLine}
          </Typography>
        )}

        {/* Order detail */}
        <Stack
          spacing={1}
          sx={{
            bgcolor: "rgba(255,255,255,0.03)", border: "1px solid", borderColor: "divider",
            borderRadius: 2, p: 1.5, mb: 2,
          }}
        >
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
            {order.image && (
              <Box component="img" src={order.image} alt=""
                sx={{ width: 38, height: 38, borderRadius: 1.5, objectFit: "cover", bgcolor: "#fff", flexShrink: 0 }} />
            )}
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 600, display: "block" }} noWrap>
                {order.product_name}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary", fontFamily: "monospace", fontSize: 10.5 }}>
                {order.razorpay_order_id}
              </Typography>
            </Box>
          </Stack>
        </Stack>

        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: "flex-start", bgcolor: "rgba(245,158,11,0.06)",
            border: "1px solid", borderColor: "rgba(245,158,11,0.22)",
            borderRadius: 2, p: 1.25, mb: 2,
          }}
        >
          <InfoOutlinedIcon sx={{ fontSize: 14, color: "warning.main", mt: "1px", flexShrink: 0 }} />
          <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.55 }}>
            There's no package to track. AI Commerce Studio pays through Razorpay but has no fulfilment
            integration — nothing notifies the eBay seller and no carrier reports back.
          </Typography>
        </Stack>

        <Stack direction="row" spacing={1}>
          <Button
            fullWidth
            variant="contained"
            onClick={onViewOrder}
            sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" } }}
          >
            View order
          </Button>
          <Button
            variant="outlined"
            onClick={onClose}
            startIcon={<DownloadOutlinedIcon sx={{ fontSize: 16 }} />}
            sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" }, borderColor: "divider", color: "text.secondary", flexShrink: 0 }}
          >
            Done
          </Button>
        </Stack>
      </Box>
    </Dialog>
  );
}
