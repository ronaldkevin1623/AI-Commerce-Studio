import { useCallback, useEffect, useState } from "react";
import {
  Box, Button, MenuItem, Stack, TextField, Tooltip, Typography,
} from "@mui/material";
import CampaignOutlinedIcon from "@mui/icons-material/CampaignOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined";

import { API_BASE } from "../../config";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/**
 * What a merchant can buy from the shopping agent.
 *
 * The panel leads with the limits rather than burying them, because the
 * limits are the product: a promotion buys consideration for searches that
 * landed in the same category, and a label if the product then earns a
 * place. It buys nothing in the ranking, and this says so before the form
 * that takes a bid.
 *
 * The counters are the honest part. `Considered` is what was paid for the
 * chance at, `shown` is what a shopper actually saw and was charged for,
 * and `screened out` is what the agent's own filters dropped — with the
 * stage named, because "dropped at precision" usually means the catalogue
 * says out of stock and is a thing the merchant can go and fix.
 */
export default function PromotionsPanel({ products = [] }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  const [form, setForm] = useState({ product_id: "", bid_inr: "1", budget_inr: "20" });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/merchant/promotions`);
      if (!res.ok) throw new Error(`Store returned ${res.status}`);
      setState({ status: "ready", data: await res.json(), error: null });
    } catch (err) {
      setState({ status: "error", data: null, error: String(err.message ?? err) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const res = await fetch(`${API_BASE}/merchant/promotions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_id: form.product_id,
          bid_paise: Math.round(Number(form.bid_inr) * 100),
          daily_budget_paise: Math.round(Number(form.budget_inr) * 100),
          active: true,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? `Store returned ${res.status}`);
      setForm((f) => ({ ...f, product_id: "" }));
      await load();
    } catch (err) {
      setFormError(String(err.message ?? err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (productId) => {
    await fetch(`${API_BASE}/merchant/promotions/${productId}`, { method: "DELETE" });
    await load();
  };

  const { data } = state;
  const rows = data?.promotions ?? [];
  const named = (id) => products.find((p) => p.id === id)?.name ?? id;
  const sellable = products.filter((p) => (p.status ?? "active") === "active");

  return (
    <Box sx={{ mt: 4 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
        <CampaignOutlinedIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="h6" sx={{ fontSize: 15, fontWeight: 600 }}>
          Promoted placements
        </Typography>
      </Stack>

      <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 2 }}>
        Pay to be considered for searches that landed in your category and would
        otherwise have missed you.
      </Typography>

      <Stack
        component="form"
        onSubmit={submit}
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        sx={{ mb: 2, alignItems: { sm: "flex-end" } }}
      >
        <TextField
          select size="small" label="Product" required
          value={form.product_id}
          onChange={(e) => setForm((f) => ({ ...f, product_id: e.target.value }))}
          sx={{ minWidth: 240, flex: 1 }}
        >
          {sellable.map((p) => (
            <MenuItem key={p.id} value={p.id}>
              {p.name} · {p.category ?? "uncategorised"}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small" label="Bid per placement (₹)" type="number" required
          slotProps={{ htmlInput: { min: 1, step: "0.5" } }}
          value={form.bid_inr}
          onChange={(e) => setForm((f) => ({ ...f, bid_inr: e.target.value }))}
          sx={{ width: 170 }}
        />
        <TextField
          size="small" label="Daily budget (₹)" type="number" required
          slotProps={{ htmlInput: { min: 1, step: "1" } }}
          value={form.budget_inr}
          onChange={(e) => setForm((f) => ({ ...f, budget_inr: e.target.value }))}
          sx={{ width: 150 }}
        />
        <Button type="submit" variant="contained" size="medium" disabled={saving || !form.product_id}>
          {saving ? "Saving…" : "Promote"}
        </Button>
      </Stack>

      {formError && (
        <Typography variant="caption" sx={{ color: "error.main", display: "block", mb: 2 }}>
          {formError}
        </Typography>
      )}

      {state.status === "error" && (
        <Typography variant="caption" sx={{ color: "error.main" }}>
          Could not read promotions — {state.error}
        </Typography>
      )}

      {rows.length === 0 && state.status === "ready" && (
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          Nothing promoted. Products still appear in agent searches on their own
          merit — a promotion only widens which searches consider them.
        </Typography>
      )}

      {rows.length > 0 && (
        <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, overflowX: "auto" }}>
          <Stack
            direction="row"
            sx={{ px: 2, py: 1, gap: 2, bgcolor: "rgba(255,255,255,0.03)", minWidth: 720 }}
          >
            {["PRODUCT", "BID", "SPENT TODAY", "CONSIDERED", "SCREENED OUT", "SHOWN", "CHOSEN", ""]
              .map((head, i) => (
                <Typography
                  key={head || i}
                  variant="caption"
                  sx={{
                    fontWeight: 600, fontSize: 11,
                    flex: i === 0 ? 1 : "none",
                    width: i === 0 ? "auto" : i === 7 ? 40 : 96,
                    textAlign: i === 0 ? "left" : i === 7 ? "center" : "right",
                  }}
                >
                  {head}
                </Typography>
              ))}
          </Stack>

          {rows.map((row, index) => (
            <Stack
              key={row.product_id}
              direction="row"
              sx={{
                px: 2, py: 1.5, gap: 2, alignItems: "center", minWidth: 720,
                borderTop: index === 0 ? "none" : "1px solid", borderColor: "divider",
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" noWrap sx={{ fontSize: 13, fontWeight: 500 }}>
                  {named(row.product_id)}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    fontSize: 11,
                    color: row.exhausted ? "warning.main" : row.active ? "success.main" : "text.disabled",
                  }}
                >
                  {row.exhausted
                    ? "Budget spent for today — resumes tomorrow"
                    : row.active ? "Running" : "Paused"}
                  {row.last_screened_out_at
                    ? ` · last drop at ${row.last_screened_out_at}`
                    : ""}
                </Typography>
              </Box>
              {[inr(row.bid_paise),
                `${inr(row.spent_today_paise)} / ${inr(row.daily_budget_paise)}`,
                row.considered, row.screened_out, row.placed, row.chosen].map((cell, i) => (
                  <Typography
                    key={i}
                    variant="body2"
                    sx={{
                      width: 96, textAlign: "right", fontSize: 12.5,
                      fontVariantNumeric: "tabular-nums",
                      color: i >= 2 ? "text.secondary" : "text.primary",
                    }}
                  >
                    {cell}
                  </Typography>
                ))}
              <Tooltip title="Stop promoting">
                <Button
                  size="small"
                  onClick={() => remove(row.product_id)}
                  sx={{ minWidth: 40, width: 40, color: "text.secondary" }}
                >
                  <DeleteOutlineIcon sx={{ fontSize: 17 }} />
                </Button>
              </Tooltip>
            </Stack>
          ))}
        </Box>
      )}

      {data && (
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 1.5, lineHeight: 1.7 }}>
          {inr(data.accrued_today_paise)} accrued today across {rows.length}{" "}
          {rows.length === 1 ? "promotion" : "promotions"}. {data.billing_note}
        </Typography>
      )}
    </Box>
  );
}
