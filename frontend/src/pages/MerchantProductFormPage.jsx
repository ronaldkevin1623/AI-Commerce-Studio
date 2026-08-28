import { useState } from "react";
import {
  Box, Button, Stack, Typography, TextField, MenuItem, InputAdornment, CircularProgress,
  Autocomplete,
} from "@mui/material";
import { Link, useNavigate } from "react-router-dom";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import LocalOfferOutlinedIcon from "@mui/icons-material/LocalOfferOutlined";

import { API_BASE } from "../config";
import MediaUpload from "../components/merchant/MediaUpload";

/**
 * Add a product to the store.
 *
 * WHAT IS AND ISN'T HERE:
 * The reference admin's form carries variants, metafields, SEO listings,
 * theme templates, collections, vendors, tax codes, HS codes and package
 * dimensions. None of those mean anything to this store, and rendering
 * inputs that quietly discard what you type into them would be worse than
 * leaving them out — you would fill in a weight, press Save, and the weight
 * would simply cease to exist. Every field below is persisted to Firestore
 * and every one of them is read by something: price and stock by checkout,
 * name and description by the agent's relevance screen, status by the UCP
 * catalogue.
 *
 * The layout follows the reference — main column of cards, a narrower
 * organisation column — because that part is genuinely good and familiar.
 */

const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
  p: 2,
};

const CONDITIONS = ["New", "Refurbished", "Open box", "Used"];

// The standard retail taxonomy, offered as suggestions rather than enforced.
// Free text still saves: the store's own search matches a product's category
// alongside its name and description, and "computer accessories" is a far
// better matching signal than "Electronics". Narrowing everything to a fixed
// list would make the existing catalogue less findable, not more tidy.
const CATEGORIES = [
  "Animals & Pet Supplies",
  "Apparel & Accessories",
  "Arts & Entertainment",
  "Baby & Toddler",
  "Business & Industrial",
  "Cameras & Optics",
  "Electronics",
  "Food, Beverages & Tobacco",
  "Furniture",
  "Hardware",
  "Health & Beauty",
  "Home & Garden",
  "Luggage & Bags",
  "Mature",
  "Media",
  "Office Supplies",
  "Religious & Ceremonial",
  "Software",
  "Sporting Goods",
  "Toys & Games",
  "Vehicles & Parts",
  "Gift Cards",
  "Uncategorized",
  "Services",
  "Product Add-Ons",
  "Bundles",
];

export default function MerchantProductFormPage() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    name: "",
    description: "",
    category: "",
    image: "",
    price: "",
    stock: "0",
    condition: "New",
    status: "active",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));

  // The store rejects these too — it has to, since nothing stops a request
  // arriving without going through this form. Checking here as well just
  // means you find out before a round trip.
  const priceValue = Number(form.price);
  const stockValue = Number(form.stock);
  const valid =
    form.name.trim().length > 0
    && Number.isFinite(priceValue) && priceValue > 0
    && Number.isFinite(stockValue) && stockValue >= 0;

  const save = async () => {
    if (!valid || saving) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/merchant/products`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name.trim(),
          description: form.description.trim() || null,
          category: form.category.trim() || null,
          image: form.image.trim() || null,
          // Rupees on screen, paise on the wire — the whole backend counts in
          // paise, and a float rupee amount is how rounding errors get into
          // money.
          price_paise: Math.round(priceValue * 100),
          stock: Math.trunc(stockValue),
          condition: form.condition,
          status: form.status,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail ?? `Store returned ${res.status}`);
      navigate("/merchant/products");
    } catch (err) {
      setError(String(err.message ?? err));
      setSaving(false);
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1180, mx: "auto" }}>
      <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", mb: 2.5 }}>
        <Box
          component={Link}
          to="/merchant/products"
          sx={{ display: "flex", color: "text.secondary", textDecoration: "none" }}
        >
          <LocalOfferOutlinedIcon sx={{ fontSize: 17 }} />
        </Box>
        <ChevronRightIcon sx={{ fontSize: 15, color: "text.disabled" }} />
        <Typography variant="h6" sx={{ fontSize: 19, fontWeight: 600 }}>
          Add product
        </Typography>
      </Stack>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "minmax(0,1fr) 300px" },
          gap: 2,
          alignItems: "start",
        }}
      >
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Box sx={CARD}>
            <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.75 }}>
              Title
            </Typography>
            <TextField
              fullWidth
              size="small"
              placeholder="Warm LED Desk Lamp, 3 brightness levels"
              value={form.name}
              onChange={set("name")}
            />

            <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mt: 2, mb: 0.75 }}>
              Description
            </Typography>
            <TextField
              fullWidth
              multiline
              minRows={4}
              size="small"
              placeholder="What it is, in the words a buyer would use."
              value={form.description}
              onChange={set("description")}
            />
            <Typography variant="caption" sx={{ color: "text.secondary", mt: 0.75, display: "block" }}>
              The agent's relevance screen reads this, so plain description beats marketing copy.
            </Typography>

            <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mt: 2, mb: 0.75 }}>
              Media
            </Typography>
            <MediaUpload
              value={form.image}
              onChange={(image) => setForm((f) => ({ ...f, image }))}
            />

            <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mt: 2, mb: 0.75 }}>
              Category
            </Typography>
            <Autocomplete
              freeSolo
              autoHighlight
              options={CATEGORIES}
              value={form.category}
              onChange={(_, next) => setForm((f) => ({ ...f, category: next ?? "" }))}
              onInputChange={(_, next) => setForm((f) => ({ ...f, category: next }))}
              renderInput={(params) => (
                <TextField {...params} size="small" placeholder="Search categories" />
              )}
            />
            <Typography variant="caption" sx={{ color: "text.secondary", mt: 0.75, display: "block" }}>
              Pick one or type your own — the store's search reads this alongside the name
              and description, so a specific category makes a product easier for an agent to find.
            </Typography>
          </Box>

          <Box sx={CARD}>
            <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.75 }}>
              Price
            </Typography>
            <TextField
              size="small"
              type="number"
              value={form.price}
              onChange={set("price")}
              placeholder="0.00"
              slotProps={{
                input: {
                  startAdornment: <InputAdornment position="start">₹</InputAdornment>,
                },
              }}
              sx={{ width: 200 }}
            />
            <Typography variant="caption" sx={{ color: "text.secondary", mt: 0.75, display: "block" }}>
              What the store charges. A buying agent cannot propose its own price — this
              is the only number checkout will use.
            </Typography>
          </Box>

          <Box sx={CARD}>
            <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.75 }}>
              Inventory
            </Typography>
            <Stack direction="row" spacing={2}>
              <TextField
                size="small"
                type="number"
                label="Quantity"
                value={form.stock}
                onChange={set("stock")}
                sx={{ width: 160 }}
              />
              <TextField
                select
                size="small"
                label="Condition"
                value={form.condition}
                onChange={set("condition")}
                sx={{ width: 180 }}
              >
                {CONDITIONS.map((c) => (
                  <MenuItem key={c} value={c}>{c}</MenuItem>
                ))}
              </TextField>
            </Stack>
            <Typography variant="caption" sx={{ color: "text.secondary", mt: 1, display: "block" }}>
              Checked at checkout and decremented on payment, so this is a real count
              rather than a label.
            </Typography>
          </Box>
        </Stack>

        <Stack spacing={2}>
          <Box sx={CARD}>
            <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.75 }}>
              Status
            </Typography>
            <TextField select fullWidth size="small" value={form.status} onChange={set("status")}>
              <MenuItem value="active">Active</MenuItem>
              <MenuItem value="draft">Draft</MenuItem>
            </TextField>
            <Typography variant="caption" sx={{ color: "text.secondary", mt: 1, display: "block", lineHeight: 1.6 }}>
              A draft is stored but stays out of the UCP catalogue — agents can neither
              discover it nor check it out until you publish.
            </Typography>
          </Box>

          <Box sx={{ ...CARD, bgcolor: "transparent" }}>
            <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.65, display: "block" }}>
              Variants, collections, tax codes and SEO fields from a full storefront admin
              are not here. This store has no model for them, and inputs that discarded what
              you typed would be worse than their absence.
            </Typography>
          </Box>
        </Stack>
      </Box>

      {error && (
        <Box
          sx={{
            mt: 2, p: 1.5, borderRadius: 2,
            border: "1px solid", borderColor: "error.main",
            bgcolor: "rgba(239,68,68,0.08)",
          }}
        >
          <Typography variant="caption" sx={{ color: "error.main" }}>{error}</Typography>
        </Box>
      )}

      <Stack direction="row" spacing={1.5} sx={{ justifyContent: "flex-end", mt: 2.5 }}>
        <Button component={Link} to="/merchant/products" size="small" sx={{ color: "text.secondary" }}>
          Cancel
        </Button>
        <Button
          variant="contained"
          size="small"
          disabled={!valid || saving}
          onClick={save}
          startIcon={saving ? <CircularProgress size={13} color="inherit" /> : null}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
      </Stack>
    </Box>
  );
}
