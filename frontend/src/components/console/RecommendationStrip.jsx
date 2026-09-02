import { useEffect, useRef, useState } from "react";
import { Box, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import LocalShippingIcon from "@mui/icons-material/LocalShippingOutlined";

import { API_BASE } from "../../config";

/**
 * What to look at before you have asked for anything.
 *
 * Every card is a real product with the reason it is here written on it —
 * something actually bought, or something the shop stocks that matches a
 * search actually run. Nothing is invented and nothing is sponsored; if
 * there were no history the endpoint returns nothing and this renders
 * nothing, because an empty shelf is a fact worth reporting rather than a
 * space to fill.
 *
 * It lives in the console's empty state, so it disappears the moment a
 * conversation starts — the agent's own results replace it, and two rows of
 * products competing for the same attention would be one row too many.
 */
// Deterministic from the name, so a product keeps the same tile every time
// rather than flickering to a new colour on each render.
function hue(name) {
  let total = 0;
  for (let i = 0; i < (name || "").length; i += 1) total = (total * 31 + name.charCodeAt(i)) % 360;
  return total;
}

function monogram(name) {
  return (name || "?")
    .split(/[\s-]+/)
    .filter((w) => /[a-z0-9]/i.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

export default function RecommendationStrip({ onPick }) {
  const [data, setData] = useState(null);
  const scroller = useRef(null);
  const [edges, setEdges] = useState({ left: false, right: false });

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/recommendations`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, []);

  // Which way the row can still travel. Drives the fades and the arrows, so
  // neither claims there is more to see when there is not.
  const measure = () => {
    const el = scroller.current;
    if (!el) return;
    setEdges({
      left: el.scrollLeft > 8,
      right: el.scrollLeft + el.clientWidth < el.scrollWidth - 8,
    });
  };

  useEffect(() => {
    measure();
    const el = scroller.current;
    if (!el) return undefined;
    el.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      el.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [data]);

  const cards = data?.cards ?? [];
  if (!cards.length) return null;

  const nudge = (direction) =>
    scroller.current?.scrollBy({ left: direction * 320, behavior: "smooth" });

  return (
    <Box sx={{ width: "100%", mt: 4 }}>
      <Stack
        direction="row"
        sx={{ alignItems: "baseline", justifyContent: "space-between", mb: 1, px: 0.5 }}
      >
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary", fontWeight: 700, fontSize: 10.5,
            letterSpacing: "0.09em", textTransform: "uppercase",
          }}
        >
          Picked up where you left off
        </Typography>
        <Tooltip title={data?.note ?? ""} arrow>
          <Typography variant="caption" sx={{ color: "text.disabled", fontSize: 10.5 }}>
            from your orders and searches
          </Typography>
        </Tooltip>
      </Stack>

      <Box sx={{ position: "relative" }}>
        {/* The fades are the affordance: they say "there is more this way"
            without a control to click, and they vanish at each end so they
            never imply content that is not there. */}
        {["left", "right"].map((side) => (
          <Box
            key={side}
            aria-hidden="true"
            sx={{
              position: "absolute", top: 0, bottom: 0, [side]: 0, width: 56,
              zIndex: 2, pointerEvents: "none",
              opacity: edges[side] ? 1 : 0,
              transition: "opacity 180ms",
              background: `linear-gradient(to ${side === "left" ? "right" : "left"},
                #191a1a 10%, rgba(25,26,26,0))`,
            }}
          />
        ))}

        {["left", "right"].map((side) => (
          <IconButton
            key={side}
            size="small"
            onClick={() => nudge(side === "left" ? -1 : 1)}
            aria-label={side === "left" ? "Scroll back" : "Scroll forward"}
            sx={{
              position: "absolute", top: "50%", [side]: -6, zIndex: 3,
              transform: "translateY(-50%)",
              opacity: edges[side] ? 1 : 0,
              pointerEvents: edges[side] ? "auto" : "none",
              transition: "opacity 180ms",
              bgcolor: "rgba(20,21,21,0.92)",
              border: "1px solid", borderColor: "divider",
              "&:hover": { bgcolor: "rgba(32,34,34,0.98)" },
            }}
          >
            {side === "left"
              ? <ChevronLeftIcon sx={{ fontSize: 17 }} />
              : <ChevronRightIcon sx={{ fontSize: 17 }} />}
          </IconButton>
        ))}

        <Stack
          ref={scroller}
          direction="row"
          spacing={1.25}
          sx={{
            overflowX: "auto", overflowY: "hidden", pb: 1, px: 0.5,
            scrollSnapType: "x proximity",
            "&::-webkit-scrollbar": { height: 6 },
            "&::-webkit-scrollbar-thumb": {
              bgcolor: "rgba(255,255,255,0.14)", borderRadius: 3,
            },
          }}
        >
          {cards.map((card) => (
            <Box
              // Keyed on the name, not the id. The demo seeder reuses ids
              // across separately seeded products (two cards both arrived as
              // "demo-3"), and React silently drops the duplicate. The server
              // already guarantees names are unique in this response.
              key={`${card.source}-${card.name}`}
              onClick={() => onPick?.(card)}
              sx={{
                flex: "0 0 auto", width: 176, scrollSnapAlign: "start",
                borderRadius: 2, overflow: "hidden", cursor: "pointer",
                border: "1px solid", borderColor: "divider",
                bgcolor: "rgba(255,255,255,0.025)",
                transition: "border-color 140ms, transform 140ms",
                "&:hover": {
                  borderColor: "rgba(255,255,255,0.28)",
                  transform: "translateY(-2px)",
                },
              }}
            >
              <Box
                sx={{
                  height: 116, display: "flex", alignItems: "center",
                  justifyContent: "center", bgcolor: "rgba(255,255,255,0.05)",
                }}
              >
                {card.image ? (
                  <Box
                    component="img"
                    src={card.image}
                    alt=""
                    loading="lazy"
                    sx={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                ) : (
                  // The shop has no photographs of its own stock yet, and a
                  // stock photo would be a picture of something nobody is
                  // selling. So: a monogram tile, coloured deterministically
                  // from the product name. It is obviously not a photograph,
                  // which is the point — it reads as a deliberate blank
                  // rather than an image that failed to load.
                  <Box
                    sx={{
                      width: "100%", height: "100%",
                      display: "flex", flexDirection: "column",
                      alignItems: "center", justifyContent: "center", gap: 0.5,
                      background: `linear-gradient(135deg,
                        hsl(${hue(card.name)} 22% 17%),
                        hsl(${(hue(card.name) + 40) % 360} 20% 12%))`,
                    }}
                  >
                    <Typography
                      sx={{
                        fontSize: 22, fontWeight: 700, lineHeight: 1,
                        color: `hsl(${hue(card.name)} 40% 72%)`,
                        letterSpacing: "0.04em",
                      }}
                    >
                      {monogram(card.name)}
                    </Typography>
                    <Typography sx={{ fontSize: 8.5, color: "text.disabled",
                                      letterSpacing: "0.08em" }}>
                      NO PHOTO YET
                    </Typography>
                  </Box>
                )}
              </Box>

              <Box sx={{ p: 1.1 }}>
                <Typography
                  variant="body2"
                  sx={{
                    fontSize: 12, fontWeight: 500, lineHeight: 1.35,
                    display: "-webkit-box", WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical", overflow: "hidden",
                    minHeight: 32,
                  }}
                >
                  {card.name}
                </Typography>

                <Stack
                  direction="row"
                  sx={{ alignItems: "center", justifyContent: "space-between", mt: 0.75 }}
                >
                  <Typography
                    variant="body2"
                    sx={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}
                  >
                    ₹{((card.price_paise ?? 0) / 100).toLocaleString("en-IN")}
                  </Typography>
                  {card.buyable && (
                    <Tooltip title="This one the agent can actually pay for" arrow>
                      <LocalShippingIcon sx={{ fontSize: 14, color: "success.main" }} />
                    </Tooltip>
                  )}
                </Stack>

                <Typography
                  variant="caption"
                  sx={{
                    color: "text.disabled", fontSize: 10, display: "block", mt: 0.5,
                    lineHeight: 1.3, whiteSpace: "nowrap", overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {card.why}
                </Typography>
              </Box>
            </Box>
          ))}
        </Stack>
      </Box>
    </Box>
  );
}
