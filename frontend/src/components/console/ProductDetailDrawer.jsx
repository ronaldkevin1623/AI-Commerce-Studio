import { useEffect, useState } from "react";
import { Box, Button, Drawer, Stack, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import LocalShippingOutlinedIcon from "@mui/icons-material/LocalShippingOutlined";

import AddShoppingCartIcon from "@mui/icons-material/AddShoppingCartOutlined";

import { API_BASE } from "../../config";
import SellerContactDialog from "./SellerContactDialog";
import { useCart } from "../../context/CartContext";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const shortDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : null;

/**
 * The product panel that slides in from the right.
 *
 * WHAT IS NOT HERE, ON PURPOSE: no size or colour picker. Variation groups
 * are resolved server-side to the option the request named — asking for a
 * 128GB drive prices the 128GB variant — so the number shown is already the
 * one for what was asked. A picker would invite changing that after the
 * mandate was signed against it, which the chain would then refuse.
 * Where a listing sells several options and none matched the request, the
 * panel says so rather than implying the price covers everything.
 * What sits in a picker's place is the row of *other real listings* for the
 * same search, which is the decision a buyer is actually making here: this
 * seller, or one of those.
 */
export default function ProductDetailDrawer({
  open,
  product,
  alternatives = [],
  query,
  onClose,
  onSelectAlternative,
  onBuyNow,
}) {
  const [detail, setDetail] = useState(null);
  const [activeImage, setActiveImage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const { add, has } = useCart();
  const inCart = product ? has(product.id) : false;

  // Fetch full detail on open — the gallery and description only exist on
  // eBay's single-item endpoint, and this also re-prices the listing.
  useEffect(() => {
    if (!open || !product?.id) return;

    // /product/{id} re-fetches the authoritative price from eBay. A merchant
    // item has no eBay listing behind it, and the merchant already quoted a
    // price from its own records — so asking would produce a guaranteed 404
    // and a "Checking price…" button that never resolves into anything.
    if (product.source === "merchant") {
      setDetail(null);
      setActiveImage(0);
      setLoading(false);
      return;
    }

    let live = true;
    setDetail(null);
    setActiveImage(0);
    setLoading(true);
    (async () => {
      try {
        const url = `${API_BASE}/product/${encodeURIComponent(product.id)}?query=${encodeURIComponent(query ?? "")}`;
        const res = await fetch(url);
        if (live) setDetail(res.ok ? await res.json() : null);
      } catch {
        if (live) setDetail(null);
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => { live = false; };
  }, [open, product?.id, product?.source, query]);

  if (!product) return null;

  const merged = { ...product, ...(detail ?? {}) };
  const images = merged.images?.length ? merged.images : [merged.image].filter(Boolean);
  const flagged = merged.trust && merged.trust.ok === false;
  const priceMoved =
    detail && detail.price_paise != null && detail.price_paise !== product.price_paise;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{
        paper: {
          sx: {
            width: { xs: "100%", sm: 396 },
            bgcolor: "background.default",
            borderLeft: "1px solid",
            borderColor: "divider",
            backgroundImage: "none",
          },
        },
      }}
    >
      <Stack
        direction="row"
        sx={{
          alignItems: "center", justifyContent: "space-between", gap: 1,
          px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider",
        }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0 }}>
          <ArrowBackIcon
            onClick={onClose}
            sx={{ fontSize: 18, color: "text.secondary", cursor: "pointer", flexShrink: 0 }}
          />
          <Typography variant="body2" fontWeight={600} noWrap>
            {merged.name}
          </Typography>
        </Stack>
        <CloseIcon onClick={onClose} sx={{ fontSize: 18, color: "text.secondary", cursor: "pointer", flexShrink: 0 }} />
      </Stack>

      <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 2 }}>
        {/* Gallery */}
        <Box sx={{ borderRadius: 2.5, overflow: "hidden", bgcolor: "#fff", mb: 1.25 }}>
          {images[activeImage] ? (
            <Box
              component="img"
              src={images[activeImage]}
              alt=""
              sx={{ width: "100%", height: 260, objectFit: "contain", display: "block" }}
            />
          ) : (
            <Box sx={{ width: "100%", height: 260, bgcolor: "rgba(255,255,255,0.06)" }} />
          )}
        </Box>

        {images.length > 1 && (
          <Stack direction="row" spacing={1} sx={{ mb: 2, overflowX: "auto", pb: 0.5 }}>
            {images.slice(0, 6).map((src, i) => (
              <Box
                key={src}
                component="img"
                src={src}
                alt=""
                onClick={() => setActiveImage(i)}
                sx={{
                  width: 46, height: 46, borderRadius: 1.5, objectFit: "cover",
                  bgcolor: "#fff", cursor: "pointer", flexShrink: 0,
                  border: "2px solid",
                  borderColor: i === activeImage ? "primary.main" : "transparent",
                }}
              />
            ))}
          </Stack>
        )}

        {merged.brand && (
          <Typography variant="caption" sx={{ color: "text.secondary", display: "block" }}>
            {merged.brand}
          </Typography>
        )}
        <Typography variant="body1" sx={{ fontWeight: 600, lineHeight: 1.4, mb: 0.5 }}>
          {merged.name}
        </Typography>

        <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", mb: 0.5 }}>
          <Typography variant="h2" sx={{ fontSize: 21, fontWeight: 700 }}>
            {inr(merged.price_paise)}
          </Typography>
          {merged.original_price_paise > merged.price_paise && (
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", textDecoration: "line-through" }}
            >
              {inr(merged.original_price_paise)}
            </Typography>
          )}
          {merged.discount_percent != null && (
            <Typography variant="caption" sx={{ color: "success.main", fontWeight: 600 }}>
              {merged.discount_percent}% off
            </Typography>
          )}
        </Stack>

        {/* A live reprice between search and open is exactly the thing the
            mandate chain blocks at checkout, so say it here too. */}
        {priceMoved && (
          <Typography variant="caption" sx={{ color: "warning.main", display: "block", mb: 1 }}>
            Price changed since the search — was {inr(product.price_paise)}, now{" "}
            {inr(detail.price_paise)}.
          </Typography>
        )}

        <Stack direction="row" spacing={1.5} sx={{ flexWrap: "wrap", mb: 2 }}>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {merged.condition ?? "Condition not stated"}
          </Typography>
          {merged.seller_feedback != null && (
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              Seller feedback {merged.seller_feedback}%
            </Typography>
          )}
        </Stack>

        {flagged && (
          <Stack
            direction="row"
            spacing={1}
            sx={{
              alignItems: "flex-start", bgcolor: "rgba(245,158,11,0.07)",
              border: "1px solid", borderColor: "rgba(245,158,11,0.25)",
              borderRadius: 2, p: 1.25, mb: 2,
            }}
          >
            <WarningAmberOutlinedIcon sx={{ fontSize: 15, color: "warning.main", mt: "1px", flexShrink: 0 }} />
            <Box>
              <Typography variant="caption" sx={{ color: "warning.main", fontWeight: 600, display: "block" }}>
                Trust flagged this listing
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                {(merged.trust.reasons || []).join(" · ")}
              </Typography>
            </Box>
          </Stack>
        )}

        {/* Real delivery, from the seller's own shipping options */}
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: "center", bgcolor: "background.paper", border: "1px solid",
            borderColor: "divider", borderRadius: 2, px: 1.5, py: 1.25, mb: 2,
          }}
        >
          <LocalShippingOutlinedIcon sx={{ fontSize: 16, color: "text.secondary", flexShrink: 0 }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="caption" sx={{ color: "text.primary", display: "block", fontWeight: 600 }}>
              {merged.shipping_cost_paise ? `${inr(merged.shipping_cost_paise)} delivery` : "Free delivery"}
              {merged.delivery_estimate_from && (
                <> · {shortDate(merged.delivery_estimate_from)}
                  {merged.delivery_estimate_to &&
                    shortDate(merged.delivery_estimate_to) !== shortDate(merged.delivery_estimate_from) &&
                    `–${shortDate(merged.delivery_estimate_to)}`}
                </>
              )}
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              {merged.source === "merchant"
                ? "The store ships free and has not quoted a date."
                : "eBay's estimate for this listing — not a tracked shipment."}
            </Typography>
          </Box>
        </Stack>

        {/* Other real listings for the same search */}
        {alternatives.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography
              variant="overline"
              sx={{ letterSpacing: 1, color: "text.secondary", display: "block", mb: 1, fontSize: 10 }}
            >
              Other results for this search
            </Typography>
            <Stack spacing={0.75}>
              {alternatives.slice(0, 3).map((alt) => (
                <Stack
                  key={alt.id}
                  direction="row"
                  spacing={1.25}
                  onClick={() => onSelectAlternative?.(alt)}
                  sx={{
                    alignItems: "center", px: 1.25, py: 1, borderRadius: 2,
                    border: "1px solid", borderColor: "divider", cursor: "pointer",
                    "&:hover": { borderColor: "rgba(255,255,255,0.24)" },
                  }}
                >
                  {alt.image ? (
                    <Box component="img" src={alt.image} alt=""
                      sx={{ width: 30, height: 30, borderRadius: 1, objectFit: "cover", bgcolor: "#fff", flexShrink: 0 }} />
                  ) : (
                    <Box sx={{ width: 30, height: 30, borderRadius: 1, bgcolor: "rgba(255,255,255,0.06)", flexShrink: 0 }} />
                  )}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="caption" sx={{ display: "block", fontWeight: 600 }} noWrap>
                      {alt.name}
                    </Typography>
                    <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 10.5 }}>
                      {alt.shipping_cost_paise ? `${inr(alt.shipping_cost_paise)} delivery` : "Free delivery"}
                      {alt.delivery_estimate_from && ` · ${shortDate(alt.delivery_estimate_from)}`}
                    </Typography>
                  </Box>
                  <Typography variant="caption" sx={{ fontWeight: 700, flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>
                    {inr(alt.price_paise)}
                  </Typography>
                </Stack>
              ))}
            </Stack>
          </Box>
        )}

        {merged.description && (
          <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.7, display: "block", mb: 2 }}>
            {merged.description}
          </Typography>
        )}

        {merged.variant_note && (
          <Box
            sx={{
              p: 1.5, mb: 2, borderRadius: 1.5,
              border: "1px solid", borderColor: "warning.main",
              bgcolor: "rgba(245,158,11,0.08)",
            }}
          >
            <Typography variant="caption" sx={{ color: "warning.main", fontWeight: 600, display: "block" }}>
              This listing sells several options
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.6, display: "block", mt: 0.5 }}>
              {merged.variant_note}
              {merged.price_before_variant_paise != null && (
                <> The search result showed ₹
                  {(merged.price_before_variant_paise / 100).toLocaleString("en-IN",
                    { maximumFractionDigits: 0 })}, which is a different option in the
                  same listing.</>
              )}
            </Typography>
          </Box>
        )}

        {/* What this listing actually is, and what the agent can do with it.
            The distinction is not cosmetic: one of these the agent can pay
            for outright, the other it can only find. */}
        {merged.source === "merchant" ? (
          <Box sx={{ p: 1.5, mb: 2, borderRadius: 1.5, border: "1px solid", borderColor: "divider" }}>
            <Typography variant="caption" sx={{ color: "success.main", fontWeight: 600, display: "block" }}>
              Sold by {merged.merchant_name ?? "a UCP merchant"}
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.6, display: "block", mt: 0.5 }}>
              Discovered over UCP. The seller prices this itself, checks its own
              stock, and creates the Razorpay order — so this one can be paid for
              end to end. Buyer and seller share one Razorpay test account here,
              so the money does not move between separate parties.
            </Typography>
          </Box>
        ) : (
          <Box sx={{ p: 1.5, mb: 2, borderRadius: 1.5, border: "1px solid", borderColor: "divider" }}>
            <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.6, display: "block" }}>
              A live eBay listing. AI Commerce Studio has no selling relationship with
              eBay, so it can search, screen and link to this — but paying for
              it here creates a Razorpay order that no seller will fulfil.
            </Typography>
          </Box>
        )}

        {merged.url && (
          <Box
            component="a"
            href={merged.url}
            target="_blank"
            rel="noopener noreferrer"
            sx={{
              display: "inline-flex", alignItems: "center", gap: 0.5, fontSize: 12,
              color: "text.secondary", textDecoration: "none",
              "&:hover": { color: "primary.light" },
            }}
          >
            View on eBay <OpenInNewIcon sx={{ fontSize: 13 }} />
          </Box>
        )}
      </Box>

      {/* Sticky action bar */}
      <Box sx={{ px: 2, py: 2, borderTop: "1px solid", borderColor: "divider" }}>
        <Stack direction="row" spacing={1}>
          <Button
            fullWidth
            variant="outlined"
            disabled={loading || inCart}
            // Close this panel as we add: both are right-hand drawers, so
            // leaving it open buries the cart behind it and the item looks
            // like it vanished.
            onClick={() => {
              add(merged);
              onClose?.();
            }}
            startIcon={<AddShoppingCartIcon sx={{ fontSize: 16 }} />}
            sx={{ py: 1.1 }}
          >
            {inCart ? "In cart" : "Add to cart"}
          </Button>
          <Button
            fullWidth
            variant="contained"
            disabled={loading}
            onClick={() => onBuyNow?.(merged)}
            sx={{ py: 1.1 }}
          >
            {loading ? "Checking price…" : `Buy now · ${inr(merged.price_paise)}`}
          </Button>
        </Stack>
        <Button
          fullWidth
          onClick={() => setContactOpen(true)}
          sx={{ mt: 0.75, color: "text.secondary", fontSize: 12.5, boxShadow: "none", "&:hover": { boxShadow: "none" } }}
        >
          Ask the seller a question
        </Button>
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.5, textAlign: "center" }}>
          Runs the risk gate and signs a mandate before anything is charged.
        </Typography>
      </Box>

      <SellerContactDialog
        open={contactOpen}
        product={merged}
        onClose={() => setContactOpen(false)}
      />
    </Drawer>
  );
}
