import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Box, Stack, Typography } from "@mui/material";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";

import PageBanner from "../components/shared/PageBanner";
import LoadingState from "../components/shared/LoadingState";
import { inr, shortDate } from "../components/orders/format";

import { API_BASE } from "../config";

const TONE = {
  paid: { color: "#22C55E", bg: "rgba(34,197,94,0.12)", label: "Paid" },
  created: { color: "#F59E0B", bg: "rgba(245,158,11,0.12)", label: "Awaiting payment" },
  failed: { color: "#EF4444", bg: "rgba(239,68,68,0.12)", label: "Payment failed" },
};

export default function OrdersPage() {
  const [orders, setOrders] = useState([]);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/orders`);
        if (!res.ok) throw new Error("bad status");
        const data = await res.json();
        if (live) {
          setOrders(data.orders ?? []);
          setStatus("ready");
        }
      } catch {
        if (live) setStatus("error");
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  const [tab, setTab] = useState("paid");

  // Filter tabs rather than a hard "paid only" list.
  //
  // Showing only completed payments would empty this page entirely right now,
  // and it would delete the one thing that makes the record trustworthy: an
  // order that was created and never paid is a real financial event, and this
  // project logs abandonments precisely so a started purchase cannot quietly
  // vanish. The tab defaults to Paid so the ordinary view is clean, and the
  // unpaid ones stay one click away instead of being erased.
  const counts = {
    paid: orders.filter((o) => o.status === "paid").length,
    created: orders.filter((o) => o.status === "created").length,
    failed: orders.filter((o) => o.status === "failed").length,
    all: orders.length,
  };

  const TABS = [
    { key: "paid", label: "Paid" },
    { key: "created", label: "Awaiting payment" },
    { key: "failed", label: "Failed" },
    { key: "all", label: "All" },
  ];

  const visible = tab === "all" ? orders : orders.filter((o) => o.status === tab);
  const unpaid = orders.filter((o) => o.status !== "paid").length;

  return (
    <Box>
      <PageBanner
        title="Orders"
        subtitle="Every Razorpay order AI Commerce Studio has created, newest first. Open one to see its real payment lifecycle."
      />

      <Box sx={{ maxWidth: 900, mx: "auto", px: 3, py: 4 }}>
        {status === "loading" && <LoadingState label="Loading orders" />}

        {status === "error" && (
          <Typography variant="body2" sx={{ color: "error.main" }}>
            Couldn't reach the backend. Check that uvicorn is running on port 8000.
          </Typography>
        )}

        {status === "ready" && orders.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No orders yet. Run a purchase from the console and one will appear here.
          </Typography>
        )}

        {/* Worth stating plainly rather than leaving someone to notice: no
            order has ever reached "paid", which is the Razorpay test-mode
            card rejection showing through, not a gap in this page. */}
        {status === "ready" && orders.length > 0 && (
          <Stack direction="row" spacing={0.75} sx={{ mb: 2.5, flexWrap: "wrap" }}>
            {TABS.map((t) => {
              const active = tab === t.key;
              return (
                <Box
                  key={t.key}
                  component="button"
                  type="button"
                  onClick={() => setTab(t.key)}
                  sx={{
                    px: 1.5, py: 0.6, borderRadius: 2, cursor: "pointer",
                    border: "1px solid",
                    borderColor: active ? "rgba(255,255,255,0.22)" : "divider",
                    bgcolor: active ? "rgba(255,255,255,0.07)" : "transparent",
                    color: active ? "text.primary" : "text.secondary",
                    fontSize: 12.5,
                    fontWeight: active ? 600 : 500,
                    "&:hover": { bgcolor: "rgba(255,255,255,0.05)" },
                  }}
                >
                  {t.label} · {counts[t.key]}
                </Box>
              );
            })}
          </Stack>
        )}

        {status === "ready" && tab === "paid" && counts.paid === 0 && (
          <Box sx={{ p: 2, mb: 2.5, borderRadius: 2, border: "1px solid", borderColor: "divider" }}>
            <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
              No order has completed payment yet
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
              {counts.all} orders were created for real and are waiting on checkout. This test
              account rejects cards and has UPI disabled, so Netbanking is the instrument that
              completes. The unpaid ones are under "Awaiting payment".
            </Typography>
          </Box>
        )}

        {status === "ready" && tab === "all" && orders.length > 0 && unpaid === orders.length && (
          <Box
            sx={{
              mb: 3,
              p: 2,
              borderRadius: 2.5,
              bgcolor: "rgba(245,158,11,0.07)",
              border: "1px solid",
              borderColor: "rgba(245,158,11,0.25)",
            }}
          >
            <Typography variant="body2" sx={{ color: "warning.main", fontWeight: 600, mb: 0.5 }}>
              None of these {orders.length} orders reached payment
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.6 }}>
              Every order is stuck at "created". That's the Razorpay test-mode card rejection —
              the orders are real and were created successfully, but checkout never completed.
            </Typography>
          </Box>
        )}

        <Stack spacing={1.5}>
          {visible.map((order) => {
            const tone = TONE[order.status] ?? {
              color: "#9AA3B2",
              bg: "rgba(255,255,255,0.05)",
              label: order.status,
            };
            return (
              <Box
                key={order.id}
                component={Link}
                to={`/orders/${order.id}`}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 2,
                  px: 2.5,
                  py: 2,
                  bgcolor: "background.paper",
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 2.5,
                  textDecoration: "none",
                  color: "inherit",
                  transition: "border-color 150ms",
                  "&:hover": { borderColor: "primary.main" },
                }}
              >
                {order.items?.[0]?.image ? (
                  <Box
                    component="img"
                    src={order.items[0].image}
                    alt=""
                    sx={{ width: 44, height: 44, borderRadius: 1.5, objectFit: "cover", bgcolor: "#fff", flexShrink: 0 }}
                  />
                ) : (
                  <Box sx={{ width: 44, height: 44, borderRadius: 1.5, bgcolor: "rgba(255,255,255,0.05)", flexShrink: 0 }} />
                )}

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" fontWeight={600} noWrap>
                    {order.product_name}
                  </Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary", fontFamily: "monospace", fontSize: 11 }}>
                    {order.id} · {shortDate(order.created_at) ?? "—"}
                  </Typography>
                </Box>

                <Box
                  sx={{
                    px: 1.25,
                    py: 0.4,
                    borderRadius: 999,
                    bgcolor: tone.bg,
                    color: tone.color,
                    fontSize: 11.5,
                    fontWeight: 600,
                    flexShrink: 0,
                  }}
                >
                  {tone.label}
                </Box>

                <Typography
                  variant="body2"
                  fontWeight={600}
                  sx={{ fontVariantNumeric: "tabular-nums", flexShrink: 0, width: 96, textAlign: "right" }}
                >
                  {inr(order.totals?.total_paise)}
                </Typography>

                <ChevronRightIcon sx={{ fontSize: 18, color: "text.secondary", flexShrink: 0 }} />
              </Box>
            );
          })}
        </Stack>
      </Box>
    </Box>
  );
}
