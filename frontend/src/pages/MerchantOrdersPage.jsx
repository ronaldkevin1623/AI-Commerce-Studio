import { useCallback, useEffect, useState } from "react";
import {
  Box, Button, Stack, Typography, CircularProgress, TextField,
} from "@mui/material";
import ReceiptLongOutlinedIcon from "@mui/icons-material/ReceiptLongOutlined";

import { API_BASE } from "../config";

const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
};

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

// The order a parcel actually moves through. Each step is only offered when
// it is the next one — a shop cannot ship what it has not packed.
const NEXT = { paid: "packed", packed: "shipped", shipped: "delivered" };

// THE PAYMENT SIDE, WHICH IS NOT THE FULFILMENT SIDE.
//
// A checkout with no fulfilment state was printed as "awaiting payment"
// regardless of what had actually happened to it, because the label keyed
// off `fulfilment_state` alone and never read `status`. A CANCELLED
// checkout therefore sat in the list looking like a live order waiting for
// the buyer to pay — on a page whose own subtitle promises "only mark what
// has actually happened".
//
// Anything not listed here falls through to the raw status rather than a
// friendly guess: an unknown state should look unknown, not invented.
const PAYMENT = {
  awaiting_payment: { label: "awaiting payment", color: "text.disabled" },
  cancelled: { label: "cancelled", color: "#EF4444" },
  expired: { label: "expired", color: "#F59E0B" },
  paid: { label: "paid \u2014 not yet fulfilled", color: "#60A5FA" },
};

const TONE = {
  paid: { label: "Paid", color: "#60A5FA", bg: "rgba(96,165,250,0.12)" },
  packed: { label: "Packed", color: "#A78BFA", bg: "rgba(167,139,250,0.12)" },
  shipped: { label: "Shipped", color: "#F59E0B", bg: "rgba(245,158,11,0.12)" },
  delivered: { label: "Delivered", color: "#22C55E", bg: "rgba(34,197,94,0.12)" },
};

/**
 * The seller's side of fulfilment.
 *
 * What a shop marks here, the buyer sees on their tracking page — the same
 * timestamps, the same carrier reference. That is the whole reason the
 * buyer's Shipped and Delivered stages can be solid for this store while
 * they stay dashed for an eBay listing: here there is a seller to ask, and
 * it is us.
 *
 * Nothing contacts a courier. This is a shop recording what it did, which is
 * what fulfilment is at this size, and the buyer's page says so.
 */
export default function MerchantOrdersPage() {
  const [state, setState] = useState({ status: "loading", orders: [] });
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/merchant/orders`);
      if (!res.ok) throw new Error(`Store returned ${res.status}`);
      const data = await res.json();
      setState({ status: "ready", orders: data.orders ?? [] });
    } catch (err) {
      setState({ status: "error", orders: [] });
      setError(String(err.message ?? err));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const advance = async (order) => {
    const next = NEXT[order.fulfilment_state];
    if (!next) return;
    setBusy(order.session_id);
    setError(null);
    try {
      const entry = draft[order.session_id] ?? {};
      const res = await fetch(
        `${API_BASE}/merchant/checkout/${order.session_id}/fulfil`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            state: next,
            carrier: entry.carrier || null,
            tracking_reference: entry.reference || null,
          }),
        },
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail ?? `Store returned ${res.status}`);
      await load();
    } catch (err) {
      setError(String(err.message ?? err));
    } finally {
      setBusy(null);
    }
  };

  const { status, orders } = state;
  const awaiting = orders.filter((o) => o.fulfilment_state && o.fulfilment_state !== "delivered");

  return (
    <Box sx={{ p: 3, maxWidth: 1080, mx: "auto" }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
        <ReceiptLongOutlinedIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="h6" sx={{ fontSize: 19, fontWeight: 600 }}>
          Orders
        </Typography>
      </Stack>

      <Typography variant="body2" sx={{ color: "text.secondary", mb: 2.5, maxWidth: "66ch", lineHeight: 1.7 }}>
        What an AI buyer has bought from this store, and where each parcel has got
        to. Marking an order here is what makes the buyer's tracking page show a
        real stage instead of "not tracked" — so only mark what has actually happened.
      </Typography>

      {status === "loading" && (
        <Stack sx={{ alignItems: "center", py: 8 }}><CircularProgress size={22} /></Stack>
      )}

      {error && (
        <Box sx={{ ...CARD, p: 1.75, mb: 2, borderColor: "error.main", bgcolor: "rgba(239,68,68,0.08)" }}>
          <Typography variant="caption" sx={{ color: "error.main" }}>{error}</Typography>
        </Box>
      )}

      {status === "ready" && orders.length === 0 && (
        <Box sx={{ ...CARD, px: 4, py: 6, textAlign: "center" }}>
          <Typography sx={{ fontWeight: 600, fontSize: 16, mb: 0.5 }}>
            No orders yet
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            When an agent checks out from this store, the order appears here.
          </Typography>
        </Box>
      )}

      {status === "ready" && orders.length > 0 && (
        <>
          <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 1.25 }}>
            {awaiting.length} awaiting fulfilment · {orders.length} total
          </Typography>

          <Stack spacing={1.25}>
            {orders.map((order) => {
              const stateKey = order.fulfilment_state;
              const tone = TONE[stateKey];
              const next = NEXT[stateKey];
              const entry = draft[order.session_id] ?? {};
              const needsReference = next === "shipped";
              const ready = !needsReference || Boolean((entry.reference ?? "").trim());

              return (
                <Box key={order.session_id} sx={{ ...CARD, p: 2 }}>
                  <Stack direction="row" sx={{ alignItems: "flex-start", gap: 2 }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.4 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5 }}>
                          {(order.line_items ?? [])
                            .map((l) => `${l.quantity} × ${l.name}`)
                            .join(", ") || "Order"}
                        </Typography>
                        {tone && (
                          <Typography
                            variant="caption"
                            sx={{ fontSize: 10.5, fontWeight: 700, px: 0.9, py: 0.25,
                                  borderRadius: 1, color: tone.color, bgcolor: tone.bg }}
                          >
                            {tone.label}
                          </Typography>
                        )}
                        {!stateKey && (
                          <Typography
                            variant="caption"
                            sx={{
                              fontSize: 11,
                              color: (PAYMENT[order.status] ?? {}).color
                                     ?? "text.disabled",
                            }}
                          >
                            {(PAYMENT[order.status] ?? {}).label
                             ?? order.status ?? "awaiting payment"}
                          </Typography>
                        )}
                      </Stack>

                      <Typography
                        variant="caption"
                        sx={{ color: "text.secondary", fontFamily: "monospace", fontSize: 11 }}
                      >
                        {order.session_id} · {inr(order.total_paise)}
                      </Typography>

                      {order.tracking_reference && (
                        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.4 }}>
                          {order.carrier} · {order.tracking_reference}
                        </Typography>
                      )}
                    </Box>

                    {next && (
                      <Stack spacing={0.75} sx={{ alignItems: "flex-end", flexShrink: 0 }}>
                        {needsReference && (
                          <Stack direction="row" spacing={0.75}>
                            <TextField
                              size="small"
                              placeholder="Carrier"
                              value={entry.carrier ?? ""}
                              onChange={(e) =>
                                setDraft((s) => ({
                                  ...s,
                                  [order.session_id]: { ...entry, carrier: e.target.value },
                                }))
                              }
                              sx={{ width: 116 }}
                            />
                            <TextField
                              size="small"
                              placeholder="Tracking ref"
                              value={entry.reference ?? ""}
                              onChange={(e) =>
                                setDraft((s) => ({
                                  ...s,
                                  [order.session_id]: { ...entry, reference: e.target.value },
                                }))
                              }
                              sx={{ width: 148 }}
                            />
                          </Stack>
                        )}
                        <Button
                          size="small"
                          variant="contained"
                          disabled={busy === order.session_id || !ready}
                          onClick={() => advance(order)}
                        >
                          {busy === order.session_id ? "Saving…" : `Mark ${next}`}
                        </Button>
                        {needsReference && !ready && (
                          <Typography variant="caption" sx={{ color: "text.disabled", fontSize: 10.5 }}>
                            A shipment needs a reference
                          </Typography>
                        )}
                      </Stack>
                    )}
                  </Stack>

                  {(order.fulfilment_history ?? []).length > 0 && (
                    <Stack spacing={0.3} sx={{ mt: 1.25, pt: 1.25, borderTop: "1px solid", borderColor: "divider" }}>
                      {order.fulfilment_history.map((h) => (
                        <Typography
                          key={`${h.state}-${h.at}`}
                          variant="caption"
                          sx={{ color: "text.secondary", fontSize: 11 }}
                        >
                          {new Date((h.at ?? 0) * 1000).toLocaleString("en-IN", {
                            day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
                          })}
                          {" — "}{h.note}
                          {h.tracking_reference ? ` (${h.carrier} ${h.tracking_reference})` : ""}
                        </Typography>
                      ))}
                    </Stack>
                  )}
                </Box>
              );
            })}
          </Stack>
        </>
      )}
    </Box>
  );
}
