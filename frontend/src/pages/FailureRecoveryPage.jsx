import { useCallback, useEffect, useState } from "react";
import { Box, Button, CircularProgress, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import ReplayOutlinedIcon from "@mui/icons-material/ReplayOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlineOutlined";

import { API_BASE } from "../config";
import FailedPurchaseCard from "../components/recovery/FailedPurchaseCard";
import { useRetryCheckout } from "../hooks/useRetryCheckout";

/**
 * FAILURE RECOVERY, AS A QUEUE OF THINGS SOMEBODY STILL WANTS.
 *
 * The page used to be organised around the decision log: what failed, when,
 * and a timeline of it. That is the auditor's view, and the auditor already
 * has a whole page. The person who arrives here has a different problem —
 * they tried to buy something and did not get it — so the unit here is the
 * PURCHASE, not the log line.
 *
 * Every entry is a real Razorpay failure. There is no simulation and no
 * toggle: on this account a card attempt genuinely fails every time, so a
 * failure is a thing you produce by trying to buy something with a card, not
 * a thing you switch on.
 */

const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
  p: 2,
};

const when = (epoch) => {
  if (!epoch) return "";
  return new Date(epoch * 1000).toLocaleString("en-IN", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
};

export default function FailureRecoveryPage() {
  const navigate = useNavigate();
  const [purchases, setPurchases] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [busy, setBusy] = useState("");
  const [resolved, setResolved] = useState(null);
  const [paid, setPaid] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/failed-purchases`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setPurchases(data.purchases ?? []);
      setError(null);
    } catch (err) {
      setError(String(err.message ?? err));
      setPurchases([]);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/transaction-policy`);
        if (!res.ok || !live) return;
        const data = await res.json();
        setPolicy((data.behaviours ?? []).find((b) => b.key === "auto_retry_payment"));
      } catch {
        /* the card falls back to its own wording */
      }
    })();
    return () => { live = false; };
  }, []);

  // "Try again" opens a real checkout rather than reporting that it could.
  // See useRetryCheckout for why the retry is a FRESH gated order and not a
  // resumption of the one that failed.
  const { retry, busy: retrying, error: retryError } = useRetryCheckout({
    onAuthorised: (authorised) => setResolved(authorised),
    onPaid: (result) => {
      setResolved(null);
      setPaid(result);
      load();
    },
    onFailed: () => {
      setResolved(null);
      load();
    },
  });

  const onChoose = useCallback(async (key, purchase) => {
    if (key === "retry") { retry(purchase); return; }
    setBusy(purchase.id);
    try {
      await fetch(`${API_BASE}/failed-purchases/${purchase.id}/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome: "cancelled" }),
      });
      setResolved(null);
      await load();
    } finally {
      setBusy("");
    }
  }, [load, retry]);

  return (
    <Box sx={{ px: 3, py: 4, maxWidth: 900, mx: "auto" }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <ReplayOutlinedIcon sx={{ fontSize: 19, color: "text.secondary" }} />
        <Typography sx={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.01em" }}>
          Failure recovery
        </Typography>
      </Stack>
      <Typography variant="body2"
                  sx={{ color: "text.secondary", mt: 0.5, mb: 3.5, maxWidth: 640,
                        lineHeight: 1.65 }}>
        Purchases that did not complete, what stopped them, and whether any
        rail on this account could finish them. Every entry is a real Razorpay
        failure carrying the error Razorpay itself reported.
      </Typography>

      {purchases === null && !error && (
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center", py: 4 }}>
          <CircularProgress size={16} />
          <Typography variant="body2" color="text.secondary">
            Reading the recovery queue…
          </Typography>
        </Stack>
      )}

      {error && (
        <Box sx={{ ...CARD, borderColor: "error.main", bgcolor: "rgba(239,68,68,0.08)" }}>
          <Typography variant="body2" sx={{ color: "error.main", fontWeight: 600, mb: 0.5 }}>
            Couldn't read the recovery queue
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>{error}</Typography>
        </Box>
      )}

      {purchases?.length === 0 && !error && (
        <Box sx={{ ...CARD, textAlign: "center", py: 5, mb: 3 }}>
          <CheckCircleOutlineIcon sx={{ fontSize: 24, color: "success.main", mb: 1.5 }} />
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.75 }}>
            Nothing waiting to be recovered
          </Typography>
          <Typography variant="body2"
                      sx={{ color: "text.secondary", maxWidth: 460, mx: "auto",
                            lineHeight: 1.7 }}>
            Nothing here is scripted, so this fills only when a payment
            actually fails. Buy something and pay by <b>card</b> — this
            account rejects them, so the attempt will fail for real and the
            item will appear here.
          </Typography>
          <Button size="small" variant="outlined" onClick={() => navigate("/console")}
                  sx={{ mt: 2, textTransform: "none", borderColor: "divider" }}>
            Open the console
          </Button>
        </Box>
      )}

      {paid && (
        <Box sx={{ ...CARD, mb: 2.5, borderColor: "rgba(74,222,128,0.45)",
                   bgcolor: "rgba(74,222,128,0.07)" }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.75 }}>
            <CheckCircleOutlineIcon sx={{ fontSize: 17, color: "success.main" }} />
            <Typography variant="body2" sx={{ fontWeight: 700, fontSize: 13.5 }}>
              {paid.ok ? "Paid" : "Paid, but not verified"} — {paid.product?.name}
            </Typography>
          </Stack>
          <Typography variant="body2"
                      sx={{ color: "text.secondary", fontSize: 12.5, lineHeight: 1.7 }}>
            {paid.ok
              ? "Razorpay captured it and this app confirmed the capture against Razorpay before recording it."
              : "Razorpay reported a payment but this app could not verify it, so the order has NOT been marked paid. That refusal is in the audit trail."}
            {" "}Payment {paid.payment_id} against order {paid.order_id}.
          </Typography>
          <Button size="small" variant="outlined" onClick={() => navigate("/orders")}
                  sx={{ mt: 1.5, textTransform: "none", borderColor: "divider" }}>
            See the order
          </Button>
        </Box>
      )}

      {resolved && !paid && (
        <Box sx={{ ...CARD, mb: 2.5, borderColor: "rgba(74,222,128,0.3)",
                   bgcolor: "rgba(74,222,128,0.05)" }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 0.75 }}>
            Fresh attempt — {resolved.product?.name}
          </Typography>
          <Typography variant="body2"
                      sx={{ color: "text.secondary", fontSize: 13, lineHeight: 1.7 }}>
            {resolved.note} A new order has been created and gated from the
            top, and Razorpay is opening on that rail. Finish it at the bank
            page — that step is a person's, not the agent's.
          </Typography>
        </Box>
      )}

      {retryError && (
        <Box sx={{ ...CARD, mb: 2.5, borderColor: "error.main",
                   bgcolor: "rgba(239,68,68,0.08)" }}>
          <Typography variant="body2" sx={{ color: "error.main", fontWeight: 600, mb: 0.5 }}>
            The retry did not open
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.65 }}>
            {retryError}
          </Typography>
        </Box>
      )}

      {purchases?.length > 0 && (
        <Stack spacing={2} sx={{ mb: 3.5 }}>
          {purchases.map((purchase) => (
            <Box key={purchase.id}>
              <Typography variant="caption"
                          sx={{ display: "block", mb: 0.75, color: "text.disabled",
                                fontSize: 11 }}>
                {when(purchase.created_at)}
              </Typography>
              <FailedPurchaseCard
                purchase={purchase}
                policy={policy}
                onChoose={onChoose}
                busy={busy === purchase.id || retrying === purchase.id}
              />
            </Box>
          ))}
        </Stack>
      )}

      <Typography variant="caption"
                  sx={{ color: "text.disabled", lineHeight: 1.7, px: 0.5 }}>
        No silent retries. Every step — the failure, the authorisation of a
        fresh attempt, and closing an item off this queue — is written to the
        audit trail.
      </Typography>
    </Box>
  );
}
