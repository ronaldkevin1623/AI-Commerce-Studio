import { useEffect, useState } from "react";
import { Box, Button, Stack, Typography } from "@mui/material";
import AddShoppingCartIcon from "@mui/icons-material/AddShoppingCart";
import StorefrontOutlinedIcon from "@mui/icons-material/StorefrontOutlined";

import { API_BASE } from "../../config";
import { useCart } from "../../context/CartContext";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

/**
 * THE MERCHANT'S APPROVED CROSS-SELL, SHOWN TO THE BUYER.
 *
 * This is the step that closes the loop. A growth agent proposes a
 * cross-sell, the gate rules on it, the merchant approves it — and until
 * now that chain ended in a database row no customer-facing screen read.
 * The merchant could approve all day and nothing reached anybody.
 *
 * Two things it must not do, both of which every retail cross-sell widget
 * does by default:
 *
 * IT MUST NOT OVERSTATE THE BASIS. "Frequently bought together" printed
 * over a pair nobody has ever bought together is a fabricated statistic
 * with a friendly face. The wording comes from the server and changes with
 * the evidence — an adjacency-based suggestion says outright that nobody
 * has bought the two together yet.
 *
 * IT MUST NOT LOOK LIKE THE AGENT'S OWN RECOMMENDATION. The buying agent
 * works for the shopper; this is the shop talking. So it is visually a
 * different thing, labelled as the merchant's, with the approval disclosed.
 */
export default function CrossSellOffer({ productId, source }) {
  const [offer, setOffer] = useState(null);
  const { add, items } = useCart();

  useEffect(() => {
    // Only the store's own products can carry one. An eBay listing has no
    // merchant behind it who could have approved anything.
    if (!productId || source !== "merchant") {
      setOffer(null);
      return undefined;
    }
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/merchant/catalog/${encodeURIComponent(productId)}`);
        if (!res.ok) return;
        const data = await res.json();
        if (live) setOffer(data.offer ?? null);
      } catch {
        // A cross-sell that cannot be fetched is simply not shown. It is an
        // addition to the page, never a precondition for buying.
      }
    })();
    return () => { live = false; };
  }, [productId, source]);

  if (!offer) return null;

  const already = items?.some((i) => i.id === offer.product.id);

  return (
    <Box
      sx={{
        mt: 2, p: 1.75, borderRadius: 2,
        border: "1px dashed", borderColor: "rgba(125,211,252,0.35)",
        bgcolor: "rgba(125,211,252,0.05)",
      }}
    >
      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 1 }}>
        <StorefrontOutlinedIcon sx={{ fontSize: 14, color: "#7DD3FC" }} />
        <Typography sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.5,
                          color: "#7DD3FC", textTransform: "uppercase" }}>
          From the merchant
        </Typography>
      </Stack>

      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
        {offer.product.image && (
          <Box
            component="img"
            src={offer.product.image}
            alt=""
            sx={{ width: 52, height: 52, borderRadius: 1.5, objectFit: "cover",
                  flexShrink: 0, bgcolor: "rgba(255,255,255,0.04)" }}
          />
        )}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2"
                      sx={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4 }}>
            {offer.product.name}
          </Typography>
          <Typography sx={{ fontSize: 13.5, fontWeight: 700, mt: 0.25 }}>
            {inr(offer.product.price_paise)}
          </Typography>
        </Box>
        <Button
          size="small"
          variant="outlined"
          disabled={already}
          onClick={() => add({
            id: offer.product.id,
            name: offer.product.name,
            price_paise: offer.product.price_paise,
            image: offer.product.image,
            source: "merchant",
          })}
          startIcon={<AddShoppingCartIcon sx={{ fontSize: 14 }} />}
          sx={{ flexShrink: 0, fontSize: 12, textTransform: "none" }}
        >
          {already ? "In cart" : "Add"}
        </Button>
      </Stack>

      {/* The server's wording, not ours — it is the one that knows whether
          this pair was ever actually bought together. */}
      <Typography variant="caption"
                  sx={{ display: "block", mt: 1.25, color: "text.secondary",
                        lineHeight: 1.6, fontSize: 11.5 }}>
        {offer.message}
      </Typography>
      <Typography variant="caption"
                  sx={{ display: "block", mt: 0.5, color: "text.disabled",
                        lineHeight: 1.55, fontSize: 10.5 }}>
        {offer.disclosure} Offer {offer.offer_id}, approved by{" "}
        {offer.approved_by === "auto" ? "the gate without escalation" : offer.approved_by}.
      </Typography>
    </Box>
  );
}
