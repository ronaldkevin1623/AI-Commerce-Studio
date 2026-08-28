import { useRef, useState } from "react";
import { Box, Button, Drawer, IconButton, Stack, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";

import { useCart } from "../../context/CartContext";
import { API_BASE } from "../../config";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * The cart, as a right-hand panel.
 *
 * Checking out here goes through /cart-checkout, which applies the spending
 * bound to the TOTAL rather than to each line — otherwise a cart of ten
 * items each just under the limit would clear a gate meant to stop exactly
 * that. If the total escalates, the cart parks for a human on the approvals
 * page rather than quietly proceeding.
 */
export default function CartPanel({ onOrderCreated }) {
  const { items, totals, open, setOpen, remove, setQuantity, clear } = useCart();
  const [status, setStatus] = useState("idle"); // idle | checking | error | escalated
  const [message, setMessage] = useState(null);

  // One key per checkout attempt, held across retries.
  //
  // This is the half that makes the server-side idempotency worth having: a
  // fresh key on every click would let a retry after a timeout create a
  // second Razorpay order, which is exactly the failure the header exists to
  // prevent. Cleared only once an order actually comes back, so the next
  // checkout is a genuinely new intent rather than a replay of the last one.
  const attemptKey = useRef(null);

  const checkout = async () => {
    setStatus("checking");
    setMessage(null);
    if (!attemptKey.current) {
      attemptKey.current =
        crypto.randomUUID?.() ?? `cp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
    try {
      const res = await fetch(`${API_BASE}/cart-checkout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "idempotency-key": attemptKey.current,
          "UCP-Agent": 'profile="commerce-studio-console"',
          "request-id": crypto.randomUUID?.() ?? String(Date.now()),
        },
        body: JSON.stringify({ items }),
      });
      const data = await res.json().catch(() => ({}));

      if (res.status === 409) {
        const detail = data.detail ?? {};
        setStatus("escalated");
        setMessage(detail.reason ?? "A human needs to approve this.");
        return;
      }
      if (!res.ok) {
        setStatus("error");
        setMessage(typeof data.detail === "string" ? data.detail : "Checkout was refused.");
        return;
      }

      setStatus("idle");
      setOpen(false);
      clear();
      attemptKey.current = null; // this intent is done; the next one is new
      onOrderCreated?.(data, items);
    } catch {
      setStatus("error");
      setMessage("Couldn't reach the backend.");
    }
  };

  const total = totals.subtotal_paise;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={() => setOpen(false)}
      slotProps={{
        paper: {
          sx: {
            width: { xs: "100%", sm: 372 },
            bgcolor: "background.default",
            borderLeft: "1px solid",
            borderColor: "divider",
            backgroundImage: "none",
          },
        },
      }}
    >
      <Stack
        direction="row"
        sx={{
          alignItems: "center", justifyContent: "space-between",
          px: 2, py: 1.75, borderBottom: "1px solid", borderColor: "divider",
        }}
      >
        <Typography variant="body2" fontWeight={600}>
          Cart{totals.count ? ` · ${totals.count} item${totals.count === 1 ? "" : "s"}` : ""}
        </Typography>
        <CloseIcon onClick={() => setOpen(false)} sx={{ fontSize: 18, color: "text.secondary", cursor: "pointer" }} />
      </Stack>

      <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 2 }}>
        {items.length === 0 ? (
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            Nothing in the cart yet. Open a product and add it.
          </Typography>
        ) : (
          <Stack spacing={1.5}>
            {items.map((item) => (
              <Stack
                key={item.id}
                direction="row"
                spacing={1.5}
                sx={{
                  alignItems: "flex-start", p: 1.25, borderRadius: 2,
                  border: "1px solid", borderColor: "divider",
                }}
              >
                {item.image ? (
                  <Box component="img" src={item.image} alt=""
                    sx={{ width: 46, height: 46, borderRadius: 1.5, objectFit: "cover", bgcolor: "#fff", flexShrink: 0 }} />
                ) : (
                  <Box sx={{ width: 46, height: 46, borderRadius: 1.5, bgcolor: "rgba(255,255,255,0.05)", flexShrink: 0 }} />
                )}

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 600, display: "-webkit-box", WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical", overflow: "hidden", lineHeight: 1.4,
                    }}
                  >
                    {item.name}
                  </Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary", display: "block", fontSize: 10.5 }}>
                    {item.condition ?? "Condition not stated"}
                  </Typography>

                  <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", mt: 0.75 }}>
                    <QtyButton label="−" onClick={() => setQuantity(item.id, item.quantity - 1)} />
                    <Typography
                      variant="caption"
                      sx={{ width: 22, textAlign: "center", fontVariantNumeric: "tabular-nums" }}
                    >
                      {item.quantity}
                    </Typography>
                    <QtyButton label="+" onClick={() => setQuantity(item.id, item.quantity + 1)} />
                    <Box sx={{ flex: 1 }} />
                    <Typography variant="caption" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                      {inr((item.price_paise ?? 0) * item.quantity)}
                    </Typography>
                    <IconButton size="small" onClick={() => remove(item.id)} sx={{ color: "text.secondary" }}>
                      <DeleteOutlineIcon sx={{ fontSize: 15 }} />
                    </IconButton>
                  </Stack>
                </Box>
              </Stack>
            ))}
          </Stack>
        )}
      </Box>

      {items.length > 0 && (
        <Box sx={{ px: 2, py: 2, borderTop: "1px solid", borderColor: "divider" }}>
          <Stack direction="row" sx={{ justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>Subtotal</Typography>
            <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums" }}>{inr(total)}</Typography>
          </Stack>
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "baseline", mb: 1.5 }}>
            <Typography variant="body2" fontWeight={700}>Total</Typography>
            <Typography variant="body1" fontWeight={700} sx={{ fontVariantNumeric: "tabular-nums" }}>
              {inr(total)}
            </Typography>
          </Stack>

          {message && (
            <Typography
              variant="caption"
              sx={{ color: status === "escalated" ? "warning.main" : "error.main", display: "block", mb: 1.25 }}
            >
              {message}
              {status === "escalated" && " Approve it on the Approvals page."}
            </Typography>
          )}

          <Button
            fullWidth
            variant="contained"
            disabled={status === "checking"}
            onClick={checkout}
            sx={{ py: 1.1 }}
          >
            {status === "checking" ? "Running the gate…" : `Checkout · ${inr(total)}`}
          </Button>

          <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", justifyContent: "center", mt: 1.25 }}>
            <ShieldOutlinedIcon sx={{ fontSize: 12, color: "text.secondary" }} />
            <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 10.5 }}>
              The spending bound applies to the whole cart, not per item
            </Typography>
          </Stack>
        </Box>
      )}
    </Drawer>
  );
}

function QtyButton({ label, onClick }) {
  return (
    <Box
      component="button"
      onClick={onClick}
      sx={{
        width: 20, height: 20, borderRadius: 1, cursor: "pointer",
        border: "1px solid", borderColor: "divider", bgcolor: "transparent",
        color: "text.primary", fontFamily: "inherit", fontSize: 12, lineHeight: 1,
        "&:hover": { bgcolor: "rgba(255,255,255,0.06)" },
      }}
    >
      {label}
    </Box>
  );
}
