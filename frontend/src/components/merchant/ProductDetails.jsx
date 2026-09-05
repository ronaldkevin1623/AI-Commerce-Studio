import { useState } from "react";
import {
  Box, Button, MenuItem, Select, Stack, TextField, Typography, CircularProgress,
} from "@mui/material";

import { API_BASE } from "../../config";
import { compress } from "./MediaUpload";

/**
 * THE EXPANDED ROW: everything about one product, and the controls to
 * change it.
 *
 * WHY THE FORM IS THE DETAIL VIEW
 *
 * A read-only panel plus a separate edit screen means the merchant looks at
 * a price in one place and changes it in another, and the two can disagree
 * about what is true. The fields here ARE the record: what is on screen is
 * what is stored, and saving sends only what was touched.
 *
 * PUBLISHING SITS IN THE SAME PLACE AS EVERYTHING ELSE, AND SAYS WHAT IT
 * MEANS
 *
 * Status is the one control here that is not about the product but about
 * the shop's exposure to buying agents. It is a plain dropdown rather than
 * a special ceremony, because a merchant should be able to pull something
 * off sale as easily as they put it on — but the line underneath states
 * the consequence in both directions, because "Active" on its own does not
 * tell anybody that an AI can now buy it.
 */
export default function ProductDetails({ product, onSaved, onRequestRemove }) {
  const [form, setForm] = useState({
    name: product.name ?? "",
    price_paise: product.price_paise ?? 0,
    stock: product.stock ?? 0,
    category: product.category ?? "",
    description: product.description ?? "",
    status: (product.status ?? "active").toLowerCase(),
    // `undefined` means untouched. `null` means the merchant removed it,
    // which is a different instruction from "I did not change the photo" —
    // and only one of them should reach the server.
    image: undefined,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  // Removal is confirmed in one place — the dialog the page owns — so the
  // panel and the row ask the same question and cannot drift apart.

  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
    setSaved(false);
    setError(null);
  };

  // Only what actually changed. Sending the whole record would rewrite
  // fields the merchant never touched, and would carry the image back and
  // forth on every edit for no reason.
  const changed = () => {
    const patch = {};
    if (form.name !== (product.name ?? "")) patch.name = form.name;
    if (Number(form.price_paise) !== (product.price_paise ?? 0)) {
      patch.price_paise = Number(form.price_paise);
    }
    if (Number(form.stock) !== (product.stock ?? 0)) patch.stock = Number(form.stock);
    if (form.category !== (product.category ?? "")) patch.category = form.category;
    if (form.description !== (product.description ?? "")) {
      patch.description = form.description;
    }
    if (form.status !== (product.status ?? "active").toLowerCase()) {
      patch.status = form.status;
    }
    // Sent only when actually touched, so an edit to the price does not
    // re-upload a picture that has not changed.
    if (form.image !== undefined) patch.image = form.image ?? "";
    return patch;
  };

  const save = async () => {
    const patch = changed();
    if (Object.keys(patch).length === 0) {
      setError("Nothing has changed.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/merchant/products/${product.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `Store returned ${res.status}`);
      setSaved(true);
      onSaved?.(data);
    } catch (err) {
      setError(String(err.message ?? err));
    } finally {
      setSaving(false);
    }
  };

  const live = form.status === "active";
  // `undefined` means untouched, so fall back to what is stored; `null`
  // means removed, so show nothing.
  const shownImage = form.image === undefined ? product.image : form.image;

  return (
    <Box sx={{ px: 2.5, pb: 2.5, pt: 0.5 }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2.5}>
        {/* The picture at a size worth looking at, not a 46px hint. */}
        <Box sx={{ width: { xs: "100%", md: 168 }, flexShrink: 0 }}>
          <Box
          sx={{
            width: "100%", height: 168,
            borderRadius: 2, border: "1px solid", borderColor: "divider",
            bgcolor: "rgba(255,255,255,0.04)", overflow: "hidden",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          {shownImage ? (
            <Box component="img" src={shownImage} alt=""
                 sx={{ width: "100%", height: "100%", objectFit: "contain" }} />
          ) : (
            <Typography variant="caption" sx={{ color: "text.disabled" }}>
              No photo
            </Typography>
          )}
          </Box>

          {/* Replacing the picture is an edit like any other: staged here,
              written on Save, so a mis-click is undone by not saving. */}
          <Stack direction="row" spacing={1} sx={{ mt: 1, justifyContent: "center" }}>
            <Button component="label" size="small"
                    sx={{ textTransform: "none", fontSize: 11.5 }}>
              {shownImage ? "Replace photo" : "Add photo"}
              <input
                type="file"
                accept="image/*"
                hidden
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  setError(null);
                  setSaved(false);
                  try {
                    // Await first: the state updater is a plain function
                    // and cannot await inside it.
                    const shrunk = await compress(file);
                    setForm((f) => ({ ...f, image: shrunk }));
                  } catch (err) {
                    setError(err?.message || "That image could not be read.");
                  }
                }}
              />
            </Button>
            {shownImage && (
              <Button
                size="small"
                onClick={() => { setForm((f) => ({ ...f, image: null })); setSaved(false); }}
                sx={{ textTransform: "none", fontSize: 11.5, color: "text.secondary" }}
              >
                Remove
              </Button>
            )}
          </Stack>
        </Box>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 1.5 }}>
            <TextField
              label="Name" value={form.name} onChange={set("name")}
              size="small" fullWidth
            />
            <TextField
              label="Category" value={form.category} onChange={set("category")}
              size="small" fullWidth placeholder="uncategorised"
            />
          </Stack>

          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 1.5 }}>
            <TextField
              label="Price in paise" value={form.price_paise}
              onChange={set("price_paise")} size="small" fullWidth
              // Paise, not rupees, because that is what is stored. A field
              // that silently multiplies by 100 is a field that will
              // eventually be off by 100.
              helperText={`₹${(Number(form.price_paise) || 0) / 100}`}
            />
            <TextField
              label="Stock" value={form.stock} onChange={set("stock")}
              size="small" fullWidth
            />
            <Box sx={{ minWidth: 160 }}>
              <Select
                value={form.status}
                onChange={set("status")}
                size="small"
                fullWidth
              >
                <MenuItem value="draft">Draft</MenuItem>
                <MenuItem value="active">Active</MenuItem>
              </Select>
            </Box>
          </Stack>

          <TextField
            label="Description" value={form.description}
            onChange={set("description")} size="small" fullWidth
            multiline minRows={2}
            placeholder="What it is, in the words a buyer would use."
            sx={{ mb: 1.5 }}
          />

          <Typography
            variant="caption"
            sx={{ display: "block", color: live ? "#4ADE80" : "warning.main", mb: 1.5 }}
          >
            {live
              ? "Active — published in the UCP catalogue. A buying agent can discover this and check it out."
              : "Draft — kept out of the UCP catalogue. No agent can discover or buy it until you make it active."}
          </Typography>

          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
            <Button
              variant="contained" size="small" onClick={save} disabled={saving}
              sx={{ textTransform: "none" }}
            >
              {saving ? <CircularProgress size={16} /> : "Save changes"}
            </Button>
            {saved && (
              <Typography variant="caption" sx={{ color: "#4ADE80" }}>
                Saved, and written to the audit trail.
              </Typography>
            )}
            {error && (
              <Typography variant="caption" sx={{ color: "error.main" }}>
                {error}
              </Typography>
            )}
            <Box sx={{ flex: 1 }} />

            <Button
              size="small" onClick={() => onRequestRemove?.(product)}
              sx={{ textTransform: "none", color: "text.secondary" }}
            >
              Remove product
            </Button>

            <Typography variant="caption" sx={{ color: "text.disabled", fontFamily: "monospace" }}>
              {product.id}
            </Typography>
          </Stack>
        </Box>
      </Stack>
    </Box>
  );
}
