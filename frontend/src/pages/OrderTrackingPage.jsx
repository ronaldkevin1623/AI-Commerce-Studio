import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Box, Button, Stack, Typography } from "@mui/material";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

import LoadingState from "../components/shared/LoadingState";
import TrackingStepper from "../components/orders/TrackingStepper";
import OrderItemsTable from "../components/orders/OrderItemsTable";
import OrderTotals from "../components/orders/OrderTotals";
import RefundPanel from "../components/orders/RefundPanel";
import { inr, shortDate } from "../components/orders/format";

import { API_BASE } from "../config";

const STATUS_TONE = {
  paid: "#22C55E",
  created: "#F59E0B",
  failed: "#EF4444",
  refunded: "#60A5FA",
};

const STATUS_LABEL = {
  paid: "Paid",
  created: "Awaiting payment",
  failed: "Payment failed",
  attempted: "Payment attempted",
};

/** One field in the details strip. */
function Field({ label, children, tone }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 0.5 }}>
        {label}
      </Typography>
      <Typography
        variant="body2"
        sx={{ fontWeight: 600, color: tone ?? "text.primary", fontVariantNumeric: "tabular-nums" }}
      >
        {children}
      </Typography>
    </Box>
  );
}

function SectionHeading({ children, action }) {
  return (
    <Stack
      direction="row"
      sx={{ alignItems: "center", justifyContent: "space-between", gap: 2, mb: 2 }}
    >
      <Typography variant="h2" sx={{ fontSize: 20 }}>
        {children}
      </Typography>
      {action}
    </Stack>
  );
}

/**
 * Builds a real invoice from the order the page is already showing — no
 * second source, nothing recomputed on the client. Downloading it is a
 * genuine export of the stored record rather than a button that looks busy.
 */
function invoiceCsv(order) {
  const rows = [
    ["AI Commerce Studio order", order.id],
    ["Razorpay order", order.razorpay_order_id],
    ["Placed", order.created_at ?? ""],
    ["Payment status", order.status ?? ""],
    [],
    ["Item", "Condition", "Qty", "Unit price (INR)"],
    ...(order.items ?? []).map((i) => [
      i.name ?? "",
      i.condition ?? "",
      i.quantity ?? 1,
      ((i.price_paise ?? 0) / 100).toFixed(2),
    ]),
    [],
    ["Subtotal", ((order.totals?.subtotal_paise ?? 0) / 100).toFixed(2)],
    ["Discount", ((order.totals?.discount_paise ?? 0) / 100).toFixed(2)],
    ["Delivery", ((order.totals?.shipping_paise ?? 0) / 100).toFixed(2)],
    ["Total", ((order.totals?.total_paise ?? 0) / 100).toFixed(2)],
    ["Charged via Razorpay", ((order.totals?.charged_paise ?? 0) / 100).toFixed(2)],
    [],
    ["Note", "Fulfilment is not tracked by AI Commerce Studio. Delivery dates shown are eBay estimates."],
  ];
  return rows
    .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
    .join("\n");
}

export default function OrderTrackingPage() {
  const { orderId } = useParams();
  const [order, setOrder] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/orders/${orderId}`);
        if (!res.ok) throw new Error("not found");
        const data = await res.json();
        if (live) {
          setOrder(data);
          setStatus("ready");
        }
      } catch {
        if (live) setStatus("error");
      }
    })();
    return () => {
      live = false;
    };
  }, [orderId]);

  const download = useCallback(() => {
    if (!order) return;
    const blob = new Blob([invoiceCsv(order)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `commerce-studio-${order.id}.csv`;
    a.click();
    // Revoking in the same tick can cancel the download before the browser
    // has read the blob — defer it rather than racing the save.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [order]);

  if (status === "loading") {
    return (
      <Box sx={{ maxWidth: 900, mx: "auto", px: 3, py: 8 }}>
        <LoadingState label="Loading order" />
      </Box>
    );
  }

  if (status === "error") {
    return (
      <Box sx={{ maxWidth: 900, mx: "auto", px: 3, py: 8, textAlign: "center" }}>
        <Typography variant="h2" sx={{ fontSize: 20, mb: 1 }}>
          Order not found
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          No order with id {orderId} is stored in Firestore.
        </Typography>
        <Button component={Link} to="/orders" variant="outlined" sx={{ boxShadow: "none" }}>
          Back to orders
        </Button>
      </Box>
    );
  }

  const eta = shortDate(order.delivery_estimate_from);
  const etaTo = shortDate(order.delivery_estimate_to);

  return (
    <Box sx={{ maxWidth: 900, mx: "auto", px: 3, py: 5 }}>
      <Box
        component={Link}
        to="/orders"
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 0.75,
          mb: 3,
          fontSize: 13,
          color: "text.secondary",
          textDecoration: "none",
          "&:hover": { color: "primary.light" },
        }}
      >
        <ArrowBackIcon sx={{ fontSize: 15 }} /> All orders
      </Box>

      <Box sx={{ textAlign: "center", mb: 5 }}>
        <Typography variant="h1" sx={{ fontSize: 28, mb: 1.5 }}>
          Order tracking
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ maxWidth: 560, mx: "auto", lineHeight: 1.7 }}
        >
          Everything AI Commerce Studio genuinely knows about this order, read from the Razorpay payment
          record and the decisions logged to Firestore as it ran.
        </Typography>
      </Box>

      <SectionHeading
        action={
          <Button
            variant="contained"
            size="small"
            onClick={download}
            startIcon={<DownloadOutlinedIcon sx={{ fontSize: 17 }} />}
            sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" } }}
          >
            Download invoice
          </Button>
        }
      >
        Order details
      </SectionHeading>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(5, 1fr)" },
          gap: 3,
          mb: 5,
          pb: 4,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Field label="Order number">
          <Box component="span" sx={{ fontFamily: "monospace", fontSize: 13 }}>
            {order.id}
          </Box>
        </Field>
        <Field label="Order placed">{shortDate(order.created_at) ?? "—"}</Field>
        <Field label="Estimated delivery">{eta ? (etaTo && etaTo !== eta ? `${eta} – ${etaTo}` : eta) : "Not reported"}</Field>
        <Field label="No of items">
          {order.item_count} item{order.item_count === 1 ? "" : "s"}
        </Field>
        <Field label="Status" tone={STATUS_TONE[order.status] ?? "text.primary"}>
          {STATUS_LABEL[order.status] ?? order.status}
        </Field>
      </Box>

      <SectionHeading
        action={
          <Typography
            variant="body2"
            sx={{ color: "text.secondary", fontFamily: "monospace", fontSize: 13 }}
          >
            {order.razorpay_order_id}
          </Typography>
        }
      >
        Order tracking
      </SectionHeading>

      <Box sx={{ mb: 5 }}>
        <TrackingStepper stages={order.stages} />
        {eta && (
          <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 1.5 }}>
            eBay estimated delivery for this listing: <strong>{eta}</strong>
            {etaTo && etaTo !== eta ? ` – ${etaTo}` : ""}. Captured at purchase time from the
            seller's own shipping options — an estimate, not a confirmed date.
          </Typography>
        )}
      </Box>

      <SectionHeading>Items from the order</SectionHeading>
      <Box sx={{ mb: 4 }}>
        <OrderItemsTable items={order.items} fallbackName={order.product_name} />
      </Box>

      <OrderTotals totals={order.totals} priceIsConverted={order.price_is_converted} />

      {/* Returning money belongs on the order, not in a support flow.
          The panel asks Razorpay what is actually refundable and
          disables itself with a stated reason when nothing is. */}
      <RefundPanel
        razorpayOrderId={order.razorpay_order_id}
        onRefunded={() => window.location.reload()}
      />

      {/* The gate decisions behind this order — the audit trail, scoped. */}
      {order.decisions?.length > 0 && (
        <Box sx={{ mt: 5 }}>
          <Typography
            variant="overline"
            sx={{ letterSpacing: 1, color: "text.secondary", display: "block", mb: 1.5 }}
          >
            Logged decisions for this order
          </Typography>
          <Stack spacing={1}>
            {order.decisions.map((d, i) => (
              <Stack
                key={i}
                direction="row"
                spacing={1.5}
                sx={{ alignItems: "baseline", flexWrap: "wrap" }}
              >
                <Typography
                  variant="caption"
                  sx={{ color: "text.secondary", fontFamily: "monospace", flexShrink: 0 }}
                >
                  {shortDate(d.at) ?? "—"}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{ color: "primary.light", fontWeight: 600, flexShrink: 0 }}
                >
                  {d.action_type}
                </Typography>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  {d.reason}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  );
}
