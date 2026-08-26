import { useEffect, useMemo, useRef, useState } from "react";
import { Box, TextField, IconButton, Stack, Typography } from "@mui/material";
import SendIcon from "@mui/icons-material/ArrowForward";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";

import { useAgentSocket } from "../hooks/useAgentSocket";
import PageBanner from "../components/shared/PageBanner";
import ReasoningStream from "../components/console/ReasoningStream";
import RiskGateIndicator from "../components/console/RiskGateIndicator";
import TopMatches from "../components/console/TopMatches";
import TransactionTimeline from "../components/console/TransactionTimeline";
import ToolChips from "../components/console/ToolChips";
import EscalationBanner from "../components/console/EscalationBanner";

const API_BASE = "http://localhost:8000";
const RAZORPAY_KEY_ID = import.meta.env.VITE_RAZORPAY_KEY_ID;

const cardSx = {
  bgcolor: "background.paper",
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  p: 2.5,
};

function PaymentStatusBanner({ status }) {
  if (!status) return null;
  const isConfirmed = status === "confirmed";
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 1,
        px: 1.75,
        py: 0.85,
        borderRadius: 999,
        bgcolor: isConfirmed ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
        mb: 2.5,
      }}
    >
      {isConfirmed ? (
        <CheckCircleIcon sx={{ fontSize: 16, color: "#22C55E" }} />
      ) : (
        <ErrorOutlineIcon sx={{ fontSize: 16, color: "#EF4444" }} />
      )}
      <Typography variant="body2" fontWeight={600} sx={{ color: isConfirmed ? "#22C55E" : "#EF4444" }}>
        {isConfirmed ? "Payment confirmed by Razorpay" : "Payment not completed"}
      </Typography>
    </Box>
  );
}

function deriveState(events) {
  let product = null;
  let candidates = [];
  let riskGate = { state: "idle", reason: null };
  let orderInfo = null;
  const completedKeys = new Set();
  let activeKey = null;

  for (const event of events) {
    if (event.type === "step") {
      if (event.payload.toLowerCase().includes("parsing intent")) activeKey = "intent";
      if (event.payload.toLowerCase().includes("matching")) activeKey = "match";
      if (event.payload.toLowerCase().includes("ranking")) activeKey = "match";
      if (event.payload.toLowerCase().includes("risk check")) activeKey = "risk_gate";
      if (event.payload.toLowerCase().includes("creating razorpay")) activeKey = "order_created";
    }
    if (event.type === "candidates") {
      candidates = event.payload;
    }
    if (event.type === "match") {
      product = event.payload.product;
      completedKeys.add("intent");
      completedKeys.add("match");
    }
    if (event.type === "risk_gate") {
      riskGate = { state: event.payload.decision, reason: event.payload.reason };
      if (event.payload.decision === "allowed") completedKeys.add("risk_gate");
    }
    if (event.type === "order_created") {
      orderInfo = event.payload;
      completedKeys.add("risk_gate");
      completedKeys.add("order_created");
      activeKey = "order_created";
    }
  }

  return { product, candidates, riskGate, orderInfo, completedKeys, activeKey };
}

export default function AgentConsolePage() {
  const [input, setInput] = useState("");
  const [paymentStatus, setPaymentStatus] = useState(null); // null | "confirmed" | "failed"
  const checkoutTriggeredRef = useRef(false);

  const { events, isRunning, pendingApproval, sendIntent, respondToEscalation } = useAgentSocket();

  const { product, candidates, riskGate, orderInfo, completedKeys, activeKey } = useMemo(
    () => deriveState(events),
    [events]
  );

  const handleSend = () => {
    checkoutTriggeredRef.current = false;
    setPaymentStatus(null);
    if (input.trim()) sendIntent(input.trim());
  };

  // The moment a real Razorpay order exists, open the real Checkout.js
  // popup — this is the actual payment step, not a simulation.
  useEffect(() => {
    if (!orderInfo || checkoutTriggeredRef.current) return;
    checkoutTriggeredRef.current = true;

    const options = {
      key: RAZORPAY_KEY_ID,
      amount: orderInfo.amount_paise,
      currency: "INR",
      name: "CartPilot",
      description: orderInfo.product_name,
      order_id: orderInfo.razorpay_order_id,
      handler: async (response) => {
        // response contains real Razorpay fields: razorpay_payment_id,
        // razorpay_order_id, razorpay_signature
        try {
          const res = await fetch(`${API_BASE}/verify-payment`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_order_id: response.razorpay_order_id,
              customer_id: orderInfo.customer_id,
            }),
          });
          setPaymentStatus(res.ok ? "confirmed" : "failed");
        } catch {
          setPaymentStatus("failed");
        }
      },
      modal: {
        // If the user closes the popup without paying, reflect that honestly
        ondismiss: () => setPaymentStatus("failed"),
      },
      theme: { color: "#3B82F6" },
    };

    const rzp = new window.Razorpay(options);
    rzp.open();
  }, [orderInfo]);

  const timelineKeys = useMemo(() => {
    const keys = new Set(completedKeys);
    if (paymentStatus === "confirmed") keys.add("payment_confirmed");
    return keys;
  }, [completedKeys, paymentStatus]);

  const timelineActiveKey = paymentStatus === "confirmed" ? null : activeKey;

  return (
    <Box>
      <PageBanner
        title="Agent console"
        subtitle="Give the agent a task and watch it reason, check itself, and spend"
      />

      <Box sx={{ maxWidth: 1000, mx: "auto", px: 3, py: 4 }}>
        <Stack
          direction="row"
          spacing={1}
          sx={{ bgcolor: "background.paper", border: "1px solid", borderColor: "divider", borderRadius: 2.5, p: 0.5, mb: 2.5 }}
        >
          <TextField
            fullWidth
            variant="standard"
            placeholder="Wireless earbuds under ₹2000, fast delivery"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            disabled={isRunning}
            InputProps={{ disableUnderline: true, sx: { px: 1.5, py: 1 } }}
          />
          <IconButton color="primary" onClick={handleSend} disabled={isRunning || !input.trim()}>
            <SendIcon />
          </IconButton>
        </Stack>

        <PaymentStatusBanner status={paymentStatus} />

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1.4fr 1fr" }, gap: 3 }}>
          <Box sx={cardSx}>
            <ReasoningStream events={events} isRunning={isRunning} />
          </Box>

          {candidates.length > 0 && (
            <Box sx={{ ...cardSx, mt: 2.5 }}>
              <ToolChips candidates={candidates} product={product} riskGate={riskGate} orderInfo={orderInfo} />
            </Box>
          )}

          <Stack spacing={2.5}>
            <Box sx={cardSx}>
              <RiskGateIndicator state={riskGate.state} reason={riskGate.reason} />
              {pendingApproval && (
                <Box sx={{ mt: 1.5 }}>
                  <EscalationBanner
                    onApprove={() => respondToEscalation(true)}
                    onDeny={() => respondToEscalation(false)}
                  />
                </Box>
              )}
            </Box>

            <Box sx={cardSx}>
              <TopMatches candidates={candidates} chosenId={product?.id} />
            </Box>

            <Box sx={cardSx}>
              <TransactionTimeline completedKeys={timelineKeys} activeKey={timelineActiveKey} />
            </Box>
          </Stack>
        </Box>
      </Box>
    </Box>
  );
}