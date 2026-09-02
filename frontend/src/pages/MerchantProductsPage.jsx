import { useCallback, useEffect, useState } from "react";
import { Box, Button, Stack, Typography, CircularProgress } from "@mui/material";
import { Link, useNavigate } from "react-router-dom";
import AddIcon from "@mui/icons-material/Add";
import LocalOfferOutlinedIcon from "@mui/icons-material/LocalOfferOutlined";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";

import { API_BASE } from "../config";
import PromotionsPanel from "../components/merchant/PromotionsPanel";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/**
 * The store's own stock list.
 *
 * This reads /merchant/products rather than /merchant/catalog on purpose:
 * the catalogue endpoint answers buying agents and only ever shows what is
 * genuinely for sale, while the shop owner needs to see drafts too. Same
 * collection, two audiences, and conflating them would either hide the
 * operator's unpublished work or let agents buy it.
 */
export default function MerchantProductsPage() {
  const navigate = useNavigate();
  const [state, setState] = useState({ status: "loading", products: [], error: null });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, status: "loading" }));
    try {
      const res = await fetch(`${API_BASE}/merchant/products`);
      if (!res.ok) throw new Error(`Store returned ${res.status}`);
      const data = await res.json();
      setState({ status: "ready", products: data.products ?? [], error: null });
    } catch (err) {
      setState({ status: "error", products: [], error: String(err.message ?? err) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const { status, products, error } = state;

  return (
    <Box sx={{ p: 3, maxWidth: 1180, mx: "auto" }}>
      <Stack
        direction="row"
        sx={{ alignItems: "center", justifyContent: "space-between", mb: 2.5, gap: 2 }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <LocalOfferOutlinedIcon sx={{ fontSize: 18, color: "text.secondary" }} />
          <Typography variant="h6" sx={{ fontSize: 19, fontWeight: 600 }}>
            Products
          </Typography>
        </Stack>

        {products.length > 0 && (
          <Button
            variant="contained"
            size="small"
            startIcon={<AddIcon sx={{ fontSize: 16 }} />}
            component={Link}
            to="/merchant/products/new"
          >
            Add product
          </Button>
        )}
      </Stack>

      {status === "loading" && (
        <Stack sx={{ alignItems: "center", py: 8 }}>
          <CircularProgress size={22} />
        </Stack>
      )}

      {status === "error" && (
        <Box
          sx={{
            p: 2,
            borderRadius: 2,
            border: "1px solid",
            borderColor: "error.main",
            bgcolor: "rgba(239,68,68,0.08)",
          }}
        >
          <Typography variant="body2" sx={{ color: "error.main", fontWeight: 600 }}>
            Couldn't read the catalogue
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {error} — is the backend running on {API_BASE}?
          </Typography>
        </Box>
      )}

      {status === "ready" && products.length === 0 && (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2.5,
            bgcolor: "background.paper",
            px: 4,
            py: 6,
            textAlign: "center",
          }}
        >
          <Typography sx={{ fontWeight: 600, fontSize: 17, mb: 0.75 }}>
            Add your products
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 2.5 }}>
            Start by stocking the store with something an agent can find and buy.
          </Typography>
          <Button
            variant="contained"
            startIcon={<AddIcon sx={{ fontSize: 16 }} />}
            onClick={() => navigate("/merchant/products/new")}
          >
            Add product
          </Button>
        </Box>
      )}

      {status === "ready" && products.length > 0 && (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2.5,
            bgcolor: "background.paper",
            overflow: "hidden",
          }}
        >
          <Stack
            direction="row"
            sx={{
              px: 2, py: 1.25, gap: 2,
              borderBottom: "1px solid", borderColor: "divider",
              color: "text.secondary",
            }}
          >
            <Typography variant="caption" sx={{ flex: 1, fontWeight: 600, fontSize: 11 }}>
              PRODUCT
            </Typography>
            <Typography variant="caption" sx={{ width: 90, fontWeight: 600, fontSize: 11 }}>
              STATUS
            </Typography>
            <Typography variant="caption" sx={{ width: 90, fontWeight: 600, fontSize: 11, textAlign: "right" }}>
              STOCK
            </Typography>
            <Typography variant="caption" sx={{ width: 110, fontWeight: 600, fontSize: 11, textAlign: "right" }}>
              PRICE
            </Typography>
          </Stack>

          {products.map((product, index) => {
            const draft = (product.status ?? "active") !== "active";
            return (
              <Stack
                key={product.id}
                direction="row"
                sx={{
                  px: 2, py: 1.5, gap: 2, alignItems: "center",
                  borderTop: index === 0 ? "none" : "1px solid",
                  borderColor: "divider",
                }}
              >
                <Stack direction="row" spacing={1.5} sx={{ flex: 1, minWidth: 0, alignItems: "center" }}>
                  <Box
                    sx={{
                      width: 36, height: 36, borderRadius: 1.5, flexShrink: 0,
                      border: "1px solid", borderColor: "divider",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      overflow: "hidden", bgcolor: "rgba(255,255,255,0.04)",
                    }}
                  >
                    {product.image ? (
                      <Box
                        component="img"
                        src={product.image}
                        alt=""
                        sx={{ width: "100%", height: "100%", objectFit: "cover" }}
                      />
                    ) : (
                      <ImageOutlinedIcon sx={{ fontSize: 16, color: "text.disabled" }} />
                    )}
                  </Box>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="body2" noWrap sx={{ fontWeight: 500, fontSize: 13 }}>
                      {product.name}
                    </Typography>
                    <Typography variant="caption" noWrap sx={{ color: "text.secondary", fontSize: 11.5 }}>
                      {product.category ?? "Uncategorised"}
                    </Typography>
                  </Box>
                </Stack>

                <Box sx={{ width: 90 }}>
                  <Typography
                    variant="caption"
                    sx={{
                      fontSize: 11, fontWeight: 600,
                      px: 0.9, py: 0.25, borderRadius: 1,
                      color: draft ? "warning.main" : "success.main",
                      bgcolor: draft ? "rgba(245,158,11,0.12)" : "rgba(34,197,94,0.12)",
                    }}
                  >
                    {draft ? "Draft" : "Active"}
                  </Typography>
                </Box>

                <Typography
                  variant="body2"
                  sx={{
                    width: 90, textAlign: "right", fontSize: 13,
                    fontVariantNumeric: "tabular-nums",
                    color: (product.stock ?? 0) > 0 ? "text.primary" : "error.main",
                  }}
                >
                  {product.stock ?? 0}
                </Typography>

                <Typography
                  variant="body2"
                  sx={{ width: 110, textAlign: "right", fontWeight: 600, fontSize: 13, fontVariantNumeric: "tabular-nums" }}
                >
                  {inr(product.price_paise)}
                </Typography>
              </Stack>
            );
          })}
        </Box>
      )}

      {status === "ready" && products.length > 0 && (
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 1.5 }}>
          Drafts are stored but kept out of the UCP catalogue, so a buying agent can
          neither discover nor check one out until it is published.
        </Typography>
      )}

      {status === "ready" && <PromotionsPanel products={products} />}
    </Box>
  );
}
