import { Box, Typography, Stack, Link as MuiLink, Chip } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import StarIcon from "@mui/icons-material/Star";
import HeadphonesIcon from "@mui/icons-material/Headphones";
import LocalOfferIcon from "@mui/icons-material/LocalOffer";

/**
 * Shows the real candidate products the agent considered — each one
 * is a genuine clickable link to the actual product page (real eBay
 * listing, or a live Amazon search when running on the fallback
 * catalog). The one the agent ultimately picked is highlighted once
 * that decision arrives.
 *
 * Images: eBay listings include a real product photo (product.image).
 * The static fallback catalog has no real photo for a given item, so
 * rather than faking one with an unrelated stock image, it shows a
 * plain icon placeholder — honest about what's real data vs. not.
 */
function Thumbnail({ imageUrl }) {
  if (imageUrl) {
    return (
      <Box
        component="img"
        src={imageUrl}
        alt=""
        sx={{ width: 44, height: 44, borderRadius: 1.5, objectFit: "cover", flexShrink: 0 }}
      />
    );
  }
  return (
    <Box
      sx={{
        width: 44, height: 44, borderRadius: 1.5, flexShrink: 0,
        bgcolor: "background.default",
        border: "1px solid", borderColor: "divider",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <HeadphonesIcon sx={{ fontSize: 20, color: "text.secondary" }} />
    </Box>
  );
}

export default function TopMatches({ candidates, chosenId }) {
  if (!candidates || candidates.length === 0) {
    return (
      <Box>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1, mb: 1, display: "block" }}>
          Top matches
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
          Candidates will appear here once the agent finds matches.
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1, mb: 1, display: "block" }}>
        Top matches
      </Typography>

      <Stack spacing={1}>
        {candidates.map((product) => {
          const isChosen = product.id === chosenId;
          return (
            <MuiLink
              key={product.id}
              href={product.url}
              target="_blank"
              rel="noopener noreferrer"
              underline="none"
              sx={{
                display: "block",
                borderRadius: 2,
                p: 1.25,
                border: "1px solid",
                borderColor: isChosen ? "primary.main" : "divider",
                bgcolor: isChosen ? "rgba(59,130,246,0.1)" : "background.paper",
                transition: "border-color 0.15s, background-color 0.15s",
                "&:hover": {
                  borderColor: "primary.light",
                  bgcolor: "rgba(59,130,246,0.06)",
                },
              }}
            >
              <Stack direction="row" alignItems="center" spacing={1.25}>
                <Thumbnail imageUrl={product.image} />

                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Stack direction="row" alignItems="center" spacing={0.75}>
                    <Typography
                      variant="body2"
                      fontWeight={isChosen ? 700 : 500}
                      sx={{
                        color: isChosen ? "primary.light" : "text.primary",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {product.name}
                    </Typography>
                    {product.discount_percent != null && (
                      <Chip
                        size="small"
                        icon={<LocalOfferIcon sx={{ fontSize: 11 }} />}
                        label={`${product.discount_percent}% off`}
                        sx={{
                          height: 18,
                          fontSize: 10,
                          fontWeight: 600,
                          bgcolor: "success.light",
                          color: "success.main",
                          "& .MuiChip-icon": { color: "success.main", ml: "4px" },
                        }}
                      />
                    )}
                  </Stack>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.25 }}>
                    <Typography variant="caption" color="text.secondary" fontWeight={600}>
                      ₹{(product.price_paise / 100).toLocaleString("en-IN")}
                    </Typography>
                    {product.original_price_paise != null && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ textDecoration: "line-through", opacity: 0.6 }}
                      >
                        ₹{(product.original_price_paise / 100).toLocaleString("en-IN")}
                      </Typography>
                    )}
                    {product.rating != null && (
                      <Stack direction="row" alignItems="center" spacing={0.25}>
                        <StarIcon sx={{ fontSize: 12, color: "warning.main" }} />
                        <Typography variant="caption" color="text.secondary">
                          {product.rating}
                        </Typography>
                      </Stack>
                    )}
                  </Stack>
                </Box>

                <OpenInNewIcon sx={{ fontSize: 15, color: "text.secondary", flexShrink: 0 }} />
              </Stack>
            </MuiLink>
          );
        })}
      </Stack>
    </Box>
  );
}