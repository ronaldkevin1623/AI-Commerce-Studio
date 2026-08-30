import { useCallback, useEffect, useState } from "react";
import { Box, Button, Stack, TextField, Typography } from "@mui/material";

import { API_BASE } from "../../config";

/**
 * Return money for an order the agent got wrong.
 *
 * An agent that spends on someone's behalf has to make "this was a mistake"
 * a first-class outcome rather than an apology, so this sits on the order
 * itself rather than in a support flow nobody can reach.
 *
 * The refundable figure comes from Razorpay, not from our own record of what
 * was charged, and the server recomputes it before moving anything — this
 * component cannot name an amount and have it believed. When nothing can be
 * returned the panel says why instead of offering a button that fails.
 *
 * A reason is required because the audit trail is the point: "₹319.55
 * returned" is a fact, and "returned because the wrong variant arrived" is
 * a record someone can actually use later.
 */
export default function RefundPanel({ razorpayOrderId, onRefunded }) {
  const [state, setState] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/refundable/${razorpayOrderId}`);
      setState(await res.json());
    } catch {
      setState({ refundable_paise: 0, reason: "Could not reach the server." });
    }
  }, [razorpayOrderId]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/refund`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payment_id: state.payment_id,
          order_id: razorpayOrderId,
          reason: reason.trim(),
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        // The server's refusal is the message worth showing — it names the
        // actual reason rather than "something went wrong".
        setError(body.detail || "The refund was refused.");
      } else {
        setDone(body);
        onRefunded?.(body);
        load();
      }
    } catch (e) {
      setError(e.message || "The refund could not be sent.");
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  if (!state) return null;

  const amount = state.refundable_paise || 0;
  const rupees = (paise) =>
    `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

  return (
    <Box
      sx={{
        mt: 5,
        p: 2.5,
        borderRadius: 2.5,
        border: "1px solid",
        borderColor: done ? "info.dark" : "divider",
        bgcolor: done ? "rgba(96,165,250,0.08)" : "background.paper",
      }}
    >
      <Typography variant="overline" sx={{ letterSpacing: 1, color: "text.secondary" }}>
        Refund
      </Typography>

      {done ? (
        <Typography variant="body2" sx={{ mt: 1, lineHeight: 1.7 }}>
          {rupees(done.amount_paise)} returned through the Razorpay Refunds API.
          Refund id <strong>{done.razorpay_refund_id}</strong>.
          {done.remaining_paise > 0
            ? ` ${rupees(done.remaining_paise)} of this order remains captured.`
            : " The full amount has been returned."}
        </Typography>
      ) : amount <= 0 ? (
        <Typography variant="body2" sx={{ mt: 1, color: "text.secondary", lineHeight: 1.7 }}>
          {state.reason || "Nothing on this order can be returned."}
        </Typography>
      ) : (
        <>
          <Typography variant="body2" sx={{ mt: 1, color: "text.secondary", lineHeight: 1.7 }}>
            {rupees(amount)} can be returned to the buyer.
            {state.already_refunded_paise > 0 &&
              ` ${rupees(state.already_refunded_paise)} has already been returned.`}{" "}
            The amount is taken from Razorpay's record of the capture, not from this page.
          </Typography>

          <TextField
            size="small"
            fullWidth
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why is this being refunded? — it goes in the audit trail"
            sx={{ mt: 2 }}
            disabled={busy}
          />

          {error && (
            <Typography variant="body2" sx={{ mt: 1.5, color: "warning.main", lineHeight: 1.6 }}>
              {error}
            </Typography>
          )}

          <Stack direction="row" spacing={1.5} sx={{ mt: 2, alignItems: "center" }}>
            {confirming ? (
              <>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Return {rupees(amount)}?
                </Typography>
                <Button size="small" variant="contained" onClick={submit} disabled={busy}>
                  {busy ? "Returning…" : "Yes, refund"}
                </Button>
                <Button size="small" onClick={() => setConfirming(false)} disabled={busy}>
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                size="small"
                variant="outlined"
                disabled={!reason.trim() || busy}
                onClick={() => setConfirming(true)}
              >
                Refund {rupees(amount)}
              </Button>
            )}
          </Stack>

          {!reason.trim() && (
            <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 1 }}>
              A reason is required — the refund is recorded with it.
            </Typography>
          )}
        </>
      )}
    </Box>
  );
}
