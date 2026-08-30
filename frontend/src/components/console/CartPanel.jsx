import { useEffect, useMemo, useRef, useState } from "react";
import {
  Box, Button, CircularProgress, Collapse, Drawer, IconButton, Stack, Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import ReportProblemOutlinedIcon from "@mui/icons-material/ReportProblemOutlined";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlineOutlined";

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

  const [overage, setOverage] = useState(null);
  const [confirmOverride, setConfirmOverride] = useState(false);

  // The safety check, and the exact basket it was run against.
  //
  // A green light belongs to one basket, not to the cart as a concept. If
  // an item is added, removed or requantified afterwards, the result on
  // screen would be describing something the person is no longer buying —
  // so the signature below invalidates it and the check has to be run
  // again. This is the whole integrity of the feature: without it, "checked"
  // would slowly come to mean "checked something, once".
  const [preflight, setPreflight] = useState(null);
  const [flight, setFlight] = useState("idle"); // idle | running | error
  const [flightError, setFlightError] = useState(null);

  const basketSignature = useMemo(
    () => items.map((i) => `${i.id}x${i.quantity}@${i.price_paise}`).join("|"),
    [items],
  );

  useEffect(() => {
    setPreflight(null);
    setFlight("idle");
    setFlightError(null);
  }, [basketSignature]);

  const runPreflight = async () => {
    setFlight("running");
    setFlightError(null);
    try {
      const res = await fetch(`${API_BASE}/preflight`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setFlight("error");
        setFlightError(
          typeof data.detail === "string" ? data.detail : "The check could not run.",
        );
        return;
      }
      setPreflight(data);
      setFlight("idle");
    } catch {
      setFlight("error");
      setFlightError("Couldn't reach the backend.");
    }
  };

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
        body: JSON.stringify({
          items,
          // Only ever true on the second click, after the amount
          // and the excess have been shown.
          confirm_over_ceiling: confirmOverride,
        }),
      });
      const data = await res.json().catch(() => ({}));

      if (res.status === 409) {
        const detail = data.detail ?? {};

        // The person's own ceiling, which they can lift by saying so. This
        // is not an escalation to somebody else — it is a question for them.
        if (detail.status === "over_ceiling" && detail.confirmable) {
          setStatus("over_ceiling");
          setOverage(detail);
          setMessage(null);
          return;
        }

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
      setOverage(null);
      setConfirmOverride(false);
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

          {overage ? (
            <Box
              sx={{
                p: 1.5, mb: 1.25, borderRadius: 1.5,
                border: "1px solid", borderColor: "warning.dark",
                bgcolor: "rgba(245,158,11,0.08)",
              }}
            >
              <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>
                {inr(overage.excess_paise)} over your own ceiling
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.6, display: "block" }}>
                {inr(overage.total_paise)} against a {inr(overage.ceiling_paise)} limit.
                That bound exists to stop the agent spending freely — it is not
                a limit on you. Confirm and it goes through, recorded in the
                audit trail as your decision.
              </Typography>
            </Box>
          ) : null}

          {/* The safety check, before the money moves. */}
          {preflight && <PreflightReport report={preflight} />}

          {flightError && (
            <Typography variant="caption" sx={{ color: "error.main", display: "block", mb: 1.25 }}>
              {flightError}
            </Typography>
          )}

          {!preflight ? (
            <Button
              fullWidth
              variant="contained"
              disabled={flight === "running" || !items.length}
              onClick={runPreflight}
              startIcon={
                flight === "running"
                  ? <CircularProgress size={14} color="inherit" />
                  : <ShieldOutlinedIcon sx={{ fontSize: 17 }} />
              }
              sx={{ py: 1.1 }}
            >
              {flight === "running" ? "Checking…" : "Check before buying"}
            </Button>
          ) : (
            <Button
              fullWidth
              variant="contained"
              // Blocked means the seller's own record disagrees with this
              // basket. There is no honest amount to charge, so this is the
              // one state the person cannot click past — re-check instead.
              color={preflight.verdict === "blocked"
                ? "inherit"
                : preflight.verdict === "attention" || overage ? "warning" : "success"}
              disabled={status === "checking" || preflight.verdict === "blocked"}
              onClick={() => {
                if (overage) setConfirmOverride(true);
                checkout();
              }}
              sx={{ py: 1.1 }}
            >
              {status === "checking"
                ? "Running the gate…"
                : preflight.verdict === "blocked"
                  ? "Cannot buy — see above"
                  : overage
                    ? `Buy anyway · ${inr(total)}`
                    : preflight.verdict === "attention"
                      ? `Buy anyway · ${inr(total)}`
                      : `Buy · ${inr(total)}`}
            </Button>
          )}

          {preflight && (
            <Button
              fullWidth
              size="small"
              onClick={runPreflight}
              disabled={flight === "running"}
              sx={{ mt: 0.75, color: "text.secondary" }}
            >
              {flight === "running" ? "Checking…" : "Run the check again"}
            </Button>
          )}

          {overage && (
            <Button
              fullWidth
              size="small"
              onClick={() => { setOverage(null); setConfirmOverride(false); }}
              sx={{ mt: 0.75, color: "text.secondary" }}
            >
              Keep the limit — cancel
            </Button>
          )}

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

const STATUS = {
  pass: { icon: CheckCircleOutlineIcon, color: "success.main" },
  warn: { icon: ReportProblemOutlinedIcon, color: "warning.main" },
  fail: { icon: ErrorOutlineIcon, color: "error.main" },
  unknown: { icon: HelpOutlineIcon, color: "text.disabled" },
};

const VERDICT = {
  clear: {
    line: "Safe to buy",
    plain: "Every check passed against this exact basket.",
    color: "success.main", tint: "rgba(34,197,94,0.08)", edge: "rgba(34,197,94,0.35)",
  },
  attention: {
    line: "Worth a look first",
    plain: "Nothing here stops the purchase — read it and decide.",
    color: "warning.main", tint: "rgba(245,158,11,0.08)", edge: "rgba(245,158,11,0.4)",
  },
  blocked: {
    line: "Not safe to buy",
    plain: "Something below has to be right before money moves.",
    color: "error.main", tint: "rgba(239,68,68,0.08)", edge: "rgba(239,68,68,0.4)",
  },
};

/**
 * The result of the pre-purchase check, in the cart drawer.
 *
 * The verdict comes first and in words — a person should not have to count
 * green ticks to learn whether they can buy. Every check is then listed
 * whether it passed or not: showing only the problems would leave someone
 * unable to tell a clean run from a run that never happened.
 *
 * Detail is folded for checks that passed and open for those that did not,
 * because the ones that did not are the reason the panel is on screen.
 */
function PreflightReport({ report }) {
  const [openRow, setOpenRow] = useState(null);
  const tone = VERDICT[report.verdict] ?? VERDICT.attention;

  return (
    <Box
      sx={{
        mb: 1.5, borderRadius: 1.5, overflow: "hidden",
        border: "1px solid", borderColor: tone.edge,
      }}
    >
      <Box sx={{ px: 1.5, py: 1.25, bgcolor: tone.tint }}>
        <Typography variant="caption" sx={{ fontWeight: 700, color: tone.color, display: "block" }}>
          {tone.line}
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 11, lineHeight: 1.5 }}>
          {tone.plain}
        </Typography>
      </Box>

      <Box sx={{ px: 1.5, py: 0.5 }}>
        {report.checks.map((check) => {
          const meta = STATUS[check.status] ?? STATUS.unknown;
          const Icon = meta.icon;
          const failed = check.status !== "pass";
          const expanded = openRow === null ? failed : openRow === check.id;
          return (
            <Box key={check.id} sx={{ py: 0.6 }}>
              <Stack
                direction="row"
                spacing={1}
                onClick={() => setOpenRow(expanded && openRow === check.id ? "" : check.id)}
                sx={{ alignItems: "flex-start", cursor: "pointer" }}
              >
                <Icon sx={{ fontSize: 15, color: meta.color, mt: "1px", flexShrink: 0 }} />
                <Typography variant="caption" sx={{ fontSize: 11.5, lineHeight: 1.45, flex: 1 }}>
                  {check.label}
                </Typography>
              </Stack>
              <Collapse in={expanded} unmountOnExit>
                <Typography
                  variant="caption"
                  sx={{ display: "block", pl: 3, pr: 0.5, pt: 0.25, fontSize: 10.5,
                        lineHeight: 1.55, color: "text.secondary" }}
                >
                  {check.detail}
                </Typography>
              </Collapse>
            </Box>
          );
        })}
      </Box>
    </Box>
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
