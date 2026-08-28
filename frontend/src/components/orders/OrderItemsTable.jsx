import { Box, Chip, Stack, Typography } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

import { inr } from "./format";

/**
 * The items on the order.
 *
 * Two deliberate departures from a typical cart table: there is no size
 * column and no quantity stepper. eBay's Browse API doesn't expose a chosen
 * variant, so a size would be invented; and a placed order can't be edited
 * from here — plus/minus controls that changed nothing would be decoration
 * shaped like a promise. Condition is shown instead, because that eBay
 * really does report, and it's the field that matters most on a used listing.
 */

const COLUMNS = "minmax(0,1fr) 132px 88px 108px";

function HeaderCell({ children, align = "left" }) {
  return (
    <Typography
      variant="caption"
      sx={{ color: "text.secondary", fontWeight: 600, textAlign: align }}
    >
      {children}
    </Typography>
  );
}

export default function OrderItemsTable({ items = [], fallbackName }) {
  // Orders placed before item snapshots were stored still deserve a row.
  const rows = items.length
    ? items
    : [{ id: null, name: fallbackName, quantity: 1, price_paise: null, legacy: true }];

  return (
    <Box
      sx={{
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2.5,
        overflow: "hidden",
      }}
    >
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: COLUMNS,
          gap: 2,
          px: 2.5,
          py: 1.5,
          bgcolor: "rgba(255,255,255,0.02)",
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <HeaderCell>Product</HeaderCell>
        <HeaderCell>Condition</HeaderCell>
        <HeaderCell align="center">Quantity</HeaderCell>
        <HeaderCell align="right">Price</HeaderCell>
      </Box>

      {rows.map((item, index) => (
        <Box
          key={item.id ?? index}
          sx={{
            display: "grid",
            gridTemplateColumns: COLUMNS,
            gap: 2,
            alignItems: "center",
            px: 2.5,
            py: 2,
            borderBottom: index < rows.length - 1 ? "1px solid" : "none",
            borderColor: "divider",
          }}
        >
          <Stack direction="row" spacing={2} sx={{ alignItems: "center", minWidth: 0 }}>
            {item.image ? (
              <Box
                component="img"
                src={item.image}
                alt=""
                sx={{
                  width: 56,
                  height: 56,
                  borderRadius: 2,
                  objectFit: "cover",
                  bgcolor: "#fff",
                  flexShrink: 0,
                }}
              />
            ) : (
              <Box
                sx={{
                  width: 56,
                  height: 56,
                  borderRadius: 2,
                  bgcolor: "rgba(255,255,255,0.05)",
                  flexShrink: 0,
                }}
              />
            )}

            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" fontWeight={600} sx={{ lineHeight: 1.4 }}>
                {item.name}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.4 }}>
                {item.id && (
                  <Typography
                    variant="caption"
                    sx={{ color: "text.secondary", fontFamily: "monospace", fontSize: 11 }}
                  >
                    Item {item.id}
                  </Typography>
                )}
                {item.url && (
                  <Box
                    component="a"
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 0.4,
                      fontSize: 11,
                      color: "text.secondary",
                      textDecoration: "none",
                      "&:hover": { color: "primary.light" },
                    }}
                  >
                    View listing <OpenInNewIcon sx={{ fontSize: 12 }} />
                  </Box>
                )}
              </Stack>
            </Box>
          </Stack>

          <Typography variant="body2" sx={{ color: "text.secondary", fontSize: 12.5 }}>
            {item.condition ?? "Not stated"}
          </Typography>

          <Box sx={{ textAlign: "center" }}>
            <Box
              sx={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                minWidth: 34,
                px: 1,
                py: 0.35,
                borderRadius: 999,
                border: "1px solid",
                borderColor: "divider",
                fontSize: 12.5,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {String(item.quantity ?? 1).padStart(2, "0")}
            </Box>
          </Box>

          <Box sx={{ textAlign: "right" }}>
            <Typography
              variant="body2"
              fontWeight={600}
              sx={{ fontVariantNumeric: "tabular-nums" }}
            >
              {item.price_paise != null ? inr(item.price_paise) : "—"}
            </Typography>
            {item.discount_percent != null && (
              <Chip
                size="small"
                label={`${item.discount_percent}% off`}
                sx={{
                  height: 18,
                  mt: 0.5,
                  bgcolor: "rgba(34,197,94,0.14)",
                  color: "success.main",
                  "& .MuiChip-label": { px: 0.75, fontSize: 10.5 },
                }}
              />
            )}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
