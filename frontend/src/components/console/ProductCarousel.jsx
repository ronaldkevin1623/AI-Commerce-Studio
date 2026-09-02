import { useRef, useState } from "react";
import { Box, Chip, Stack, Tooltip, Typography } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import StarIcon from "@mui/icons-material/Star";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import StorefrontOutlinedIcon from "@mui/icons-material/StorefrontOutlined";
import CampaignOutlinedIcon from "@mui/icons-material/CampaignOutlined";

const inr = (paise) => `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

/**
 * The results, as a scrollable row of real listings.
 *
 * Clicking a card opens its detail panel; there is no buy control here. A
 * one-click purchase off a thumbnail asks someone to commit money having
 * seen a name and a number — the condition, the seller's standing and the
 * delivery estimate all live in the panel, and those are exactly the things
 * worth reading before buying a used listing from a stranger.
 *
 * Two things here are deliberately not the reference design. There is no
 * five-star rating: eBay reports a seller feedback *percentage*, so that's
 * what's shown, because inventing a per-product star score out of a
 * per-seller number would be a fabricated signal. And a flagged listing
 * keeps its warning badge on the card rather than being quietly dropped —
 * the person should see what Trust objected to and decide.
 */
export default function ProductCarousel({ products = [], recommendedId, onOpen }) {
  const scroller = useRef(null);
  const [hovered, setHovered] = useState(null);

  if (!products.length) return null;

  const nudge = (direction) => {
    scroller.current?.scrollBy({ left: direction * 280, behavior: "smooth" });
  };

  return (
    <Box sx={{ position: "relative" }}>
      <Box
        ref={scroller}
        sx={{
          display: "flex",
          gap: 1.5,
          overflowX: "auto",
          pb: 1,
          scrollSnapType: "x mandatory",
          "&::-webkit-scrollbar": { height: 6 },
          "&::-webkit-scrollbar-thumb": { bgcolor: "rgba(255,255,255,0.12)", borderRadius: 3 },
        }}
      >
        {products.map((product) => {
          const flagged = product.trust && product.trust.ok === false;
          const isPick = String(product.id) === String(recommendedId);
          const active = hovered === product.id;

          return (
            <Box
              key={product.id}
              onMouseEnter={() => setHovered(product.id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onOpen?.(product)}
              sx={{
                position: "relative",
                width: 208,
                flexShrink: 0,
                scrollSnapAlign: "start",
                bgcolor: "background.paper",
                border: "1px solid",
                borderColor: isPick ? "rgba(255,255,255,0.26)" : "divider",
                borderRadius: 2.5,
                overflow: "hidden",
                cursor: "pointer",
                transition: "border-color 150ms, transform 150ms",
                transform: active ? "translateY(-2px)" : "none",
                "&:hover": { borderColor: "rgba(255,255,255,0.30)" },
              }}
            >
              <Box sx={{ position: "relative", height: 150, bgcolor: "#fff" }}>
                {product.image ? (
                  <Box
                    component="img"
                    src={product.image}
                    alt=""
                    sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                  />
                ) : (
                  // The demo store has no product photography. An empty grey
                  // panel reads as a broken image, so this says what it is.
                  <Box
                    sx={{
                      width: "100%", height: "100%",
                      bgcolor: "#F4F4F5",
                      display: "flex", flexDirection: "column",
                      alignItems: "center", justifyContent: "center", gap: 0.5,
                    }}
                  >
                    <StorefrontOutlinedIcon sx={{ fontSize: 22, color: "#A1A1AA" }} />
                    <Typography sx={{ fontSize: 10, color: "#71717A", fontWeight: 500 }}>
                      No photo
                    </Typography>
                  </Box>
                )}

                {isPick && (
                  <Chip
                    size="small"
                    label="Agent's pick"
                    sx={{
                      position: "absolute", top: 8, left: 8, height: 20,
                      bgcolor: "rgba(10,10,11,0.82)", color: "#ECECEE",
                      backdropFilter: "blur(4px)",
                      "& .MuiChip-label": { px: 0.9, fontSize: 10, fontWeight: 600 },
                    }}
                  />
                )}

                {flagged && (
                  <Chip
                    size="small"
                    icon={<WarningAmberOutlinedIcon sx={{ fontSize: 12, color: "#fff !important" }} />}
                    label="Flagged"
                    title={(product.trust.reasons || []).join("; ")}
                    sx={{
                      position: "absolute", top: 8, right: 8, height: 20,
                      bgcolor: "rgba(245,158,11,0.92)", color: "#fff",
                      "& .MuiChip-label": { px: 0.6, fontSize: 10, fontWeight: 600 },
                    }}
                  />
                )}

                {/* The card is the affordance — hovering hints that it opens,
                    and buying happens only in the detail panel, where the
                    price, condition and delivery have actually been read. */}
                <Box
                  sx={{
                    position: "absolute", inset: 0,
                    display: "flex", alignItems: "flex-end", justifyContent: "center",
                    pb: 1.25,
                    background: "linear-gradient(to top, rgba(0,0,0,0.55), transparent 45%)",
                    opacity: active ? 1 : 0,
                    transition: "opacity 160ms",
                    pointerEvents: "none",
                  }}
                >
                  <Typography sx={{ color: "#fff", fontSize: 11.5, fontWeight: 600 }}>
                    View details
                  </Typography>
                </Box>
              </Box>

              <Box sx={{ p: 1.5 }}>
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 600, fontSize: 12.5, lineHeight: 1.35,
                    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                    overflow: "hidden", minHeight: 34,
                  }}
                >
                  {product.name}
                </Typography>

                <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.4 }}>
                  {product.condition ?? "Condition not stated"}
                </Typography>

                {/* A variation listing quotes one price for a whole group of
                    options. Saying which option this price is for stops the
                    number meaning something other than what it looks like. */}
                {product.variant_note && (
                  <Typography
                    variant="caption"
                    sx={{ color: "warning.main", display: "block", mt: 0.4, fontSize: 10.5,
                          lineHeight: 1.4 }}
                  >
                    {product.variant_note}
                  </Typography>
                )}

                {/* Paid for its place in the CONSIDERATION set, and nothing
                    else. Labelled here rather than in a footnote because a
                    shopper is entitled to know a merchant paid to be looked
                    at — and entitled to know what that did not buy, which
                    is why the tooltip says it outright. */}
                {product.sponsored && (
                  <Tooltip
                    arrow
                    title={product.sponsored_note
                      ?? "Promoted into consideration by the merchant. Its position here was earned on the same signals as everything else."}
                  >
                    <Stack
                      direction="row"
                      spacing={0.5}
                      sx={{
                        alignItems: "center",
                        mt: 0.75,
                        px: 0.9,
                        py: 0.4,
                        borderRadius: 1,
                        alignSelf: "flex-start",
                        bgcolor: "rgba(148,163,184,0.14)",
                        border: "1px dashed",
                        borderColor: "rgba(148,163,184,0.5)",
                      }}
                    >
                      <CampaignOutlinedIcon sx={{ fontSize: 13, color: "text.secondary" }} />
                      <Typography
                        sx={{ color: "text.secondary", fontWeight: 700, fontSize: 11,
                              letterSpacing: "0.02em", lineHeight: 1.2 }}
                      >
                        Sponsored · ranked on merit
                      </Typography>
                    </Stack>
                  </Tooltip>
                )}

                {/* Where it came from decides what can happen next: the agent
                    can pay the UCP merchant outright, whereas an eBay listing
                    can only be found and linked to. Saying so on the card
                    keeps that difference visible before anything is added. */}
                {product.source === "merchant" ? (
                  <Stack
                    direction="row"
                    spacing={0.5}
                    sx={{
                      alignItems: "center",
                      mt: 0.75,
                      px: 0.9,
                      py: 0.4,
                      borderRadius: 1,
                      alignSelf: "flex-start",
                      bgcolor: "rgba(34,197,94,0.14)",
                      border: "1px solid",
                      borderColor: "rgba(34,197,94,0.45)",
                    }}
                  >
                    <StorefrontOutlinedIcon sx={{ fontSize: 13, color: "success.main" }} />
                    <Typography
                      sx={{ color: "success.main", fontWeight: 700, fontSize: 11,
                            letterSpacing: "0.02em", lineHeight: 1.2 }}
                    >
                      {product.merchant_name ?? "UCP merchant"} · can be delivered
                    </Typography>
                  </Stack>
                ) : (
                  <Box
                    sx={{
                      mt: 0.75,
                      px: 0.9,
                      py: 0.4,
                      borderRadius: 1,
                      alignSelf: "flex-start",
                      bgcolor: "rgba(245,158,11,0.10)",
                      border: "1px solid",
                      borderColor: "rgba(245,158,11,0.35)",
                    }}
                  >
                    <Typography
                      sx={{ color: "warning.main", fontWeight: 600, fontSize: 11,
                            letterSpacing: "0.02em", lineHeight: 1.2 }}
                    >
                      eBay · payable, but no seller to ship it
                    </Typography>
                  </Box>
                )}

                <Stack direction="row" sx={{ alignItems: "baseline", justifyContent: "space-between", mt: 0.75, gap: 1 }}>
                  <Stack direction="row" spacing={0.6} sx={{ alignItems: "baseline", minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                      {inr(product.price_paise)}
                    </Typography>
                    {product.discount_percent != null && (
                      <Typography variant="caption" sx={{ color: "success.main", fontWeight: 600 }}>
                        {product.discount_percent}% off
                      </Typography>
                    )}
                  </Stack>

                  {/* eBay reports 0.0% for a seller nobody has rated. Showing
                      that as a rating invents the worst possible reputation
                      out of no evidence, so an unrated seller says so. */}
                  {product.seller_feedback != null &&
                  (product.seller_feedback_count || 0) > 0 ? (
                    <Stack direction="row" spacing={0.3} sx={{ alignItems: "center", flexShrink: 0 }}>
                      <StarIcon sx={{ fontSize: 12, color: "#F59E0B" }} />
                      <Typography variant="caption" sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
                        {product.seller_feedback}%
                      </Typography>
                    </Stack>
                  ) : (
                    <Typography variant="caption" sx={{ color: "text.disabled", flexShrink: 0 }}>
                      no seller ratings
                    </Typography>
                  )}
                </Stack>
              </Box>
            </Box>
          );
        })}
      </Box>

      {products.length > 2 && (
        <>
          <Nudge side="left" onClick={() => nudge(-1)} />
          <Nudge side="right" onClick={() => nudge(1)} />
        </>
      )}
    </Box>
  );
}

function Nudge({ side, onClick }) {
  const Icon = side === "left" ? ChevronLeftIcon : ChevronRightIcon;
  return (
    <Box
      component="button"
      aria-label={side === "left" ? "Scroll left" : "Scroll right"}
      onClick={onClick}
      sx={{
        position: "absolute",
        top: 66,
        [side]: -12,
        width: 28,
        height: 28,
        borderRadius: "50%",
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.default",
        color: "text.primary",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: "pointer",
        zIndex: 2,
        "&:hover": { bgcolor: "background.paper" },
      }}
    >
      <Icon sx={{ fontSize: 17 }} />
    </Box>
  );
}
