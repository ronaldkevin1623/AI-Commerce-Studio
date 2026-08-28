import { useState } from "react";
import { Box, Typography, Stack, Button, Collapse } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import ReplayIcon from "@mui/icons-material/Replay";
import ReasoningStream from "./ReasoningStream";
import HiveCanvas from "../hive/HiveCanvas";
import RiskGateIndicator from "./RiskGateIndicator";
import ProductCarousel from "./ProductCarousel";
import TransactionTimeline from "./TransactionTimeline";
import EscalationBanner from "./EscalationBanner";
import MandateChainCard from "./MandateChainCard";

// The WebSocket pipeline only ever runs the buyer specialists, so a turn
// shows the buyer band rather than the whole hive. Module-level so the
// array identity is stable and the canvas doesn't relayout every render.
const BUYER_ONLY = ["buyer"];

/**
 * The agent's answer in prose.
 *
 * Assembled strictly from events that actually fired: the listing count from
 * Scout, the flagged count from Trust, the one-line justification from Value.
 * Nothing is added to make it read better — if Trust flagged nothing, the
 * sentence about flagging simply isn't there.
 */
function deriveAnswer(events) {
  let listings = null;
  let flagged = null;
  let shown = null;
  let pick = null;
  let reason = null;
  let blocked = null;
  // Which venues actually came back with something. The agent used to
  // announce "live eBay listings" unconditionally, which stopped being true
  // the moment a second venue was added — and a sentence that names the
  // wrong seller is worse than one that names none.
  let merchantName = null;
  let sawEbay = false;

  for (const event of events) {
    if (event.type === "step") {
      const flaggedMatch = event.payload.match(/Flagged (\d+) of (\d+) listings/);
      if (flaggedMatch) {
        flagged = Number(flaggedMatch[1]);
        listings = Number(flaggedMatch[2]);
      }
      const allPassed = event.payload.match(/All (\d+) listings passed/);
      if (allPassed) {
        listings = Number(allPassed[1]);
        flagged = 0;
      }
    }
    if (event.type === "candidates") {
      shown = event.payload.length;
      for (const candidate of event.payload) {
        if (candidate.source === "merchant") merchantName = candidate.merchant_name ?? "a UCP merchant";
        else sawEbay = true;
      }
    }
    if (event.type === "match") {
      pick = event.payload.product?.name;
      reason = event.payload.reason;
    }
    if (event.type === "error") blocked = event.payload;
    if (event.type === "risk_gate" && event.payload.decision === "blocked") {
      blocked = event.payload.reason;
    }
  }

  if (blocked) return blocked;
  if (!shown && !pick) return null;

  const parts = [];
  if (listings) {
    const venues = [sawEbay && "live eBay listings", merchantName && `${merchantName}'s catalogue`]
      .filter(Boolean)
      .join(" and ");
    parts.push(
      `I searched ${venues || "live listings"} and found ${listings}` +
        (flagged ? `, though Trust flagged ${flagged} as suspect and left ${flagged === 1 ? "it" : "them"} out of the ranking` : "")
    );
  }
  if (shown) {
    parts.push(`${parts.length ? "Here are" : "I found"} the top ${shown} for you`);
  }
  if (pick && reason) {
    const trimmed = reason.replace(/\s*$/, "").replace(/\.$/, "");
    parts.push(`I'd go with the ${pick} — ${trimmed.charAt(0).toLowerCase()}${trimmed.slice(1)}`);
  }
  return parts.length ? `${parts.join(". ")}.` : null;
}

function deriveState(events) {
  let product = null;
  let candidates = [];
  let riskGate = { state: "idle", reason: null };
  let orderInfo = null;
  let selectionPrompt = null;
  // Once the backend confirms the choice it emits "Proceeding with …",
  // so the picker stays interactive until that arrives. Deriving this
  // from the event stream is more reliable than a separate flag.
  let selectionResolved = false;
  let mandateVerification = null;
  let mandateChain = null;
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
    if (event.type === "mandate" && event.payload.stage === "verify") {
      mandateVerification = event.payload;
      mandateChain = event.payload.summary;
    }
    if (event.type === "candidates") candidates = event.payload;
    if (event.type === "await_selection") selectionPrompt = event.payload;
    if (event.type === "step" && event.payload.toLowerCase().startsWith("proceeding with")) {
      selectionResolved = true;
    }
    if (event.type === "risk_gate" || event.type === "order_created") {
      selectionResolved = true;
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

  return {
    product, candidates, riskGate, orderInfo, completedKeys, activeKey,
    selectionPrompt, selectionResolved, mandateChain, mandateVerification,
  };
}

export default function ConversationTurn({
  turn,
  isLive,
  isRunning,
  pendingApproval,
  pendingSelection,
  onSelectProduct,
  onApprove,
  onDeny,
  paymentStatus,
  onRetryPayment,
  onRepick,
  onOpenProduct,
}) {
  const {
    product, candidates, riskGate, orderInfo, completedKeys, activeKey,
    selectionPrompt, selectionResolved, mandateChain, mandateVerification,
  } = deriveState(turn.events);

  const answer = deriveAnswer(turn.events);
  const [showWorking, setShowWorking] = useState(false);

  const timelineKeys = new Set(completedKeys);
  if (paymentStatus === "confirmed") timelineKeys.add("payment_confirmed");

  const awaitingChoice = Boolean(selectionPrompt) && isLive && !selectionResolved;
  // Always stacked: the layout should never reflow between loading,
  // choosing, and paying — a shifting page mid-flow is disorienting.
  // Once the order exists the agent has finished its work, so the
  // "thinking" spinner stops even if the socket lingers.
  const stillThinking = isLive && isRunning && !orderInfo;
  // Once the agent's socket is closed — after a failed payment, or on a
  // session revisited later — the person can still act on the results.
  // Confirming goes through a REST re-pick, which creates a fresh order
  // and runs the same risk gate server-side, so it's gated and logged
  // exactly like the original attempt.
  const resumable = !isLive && Boolean(selectionPrompt);
  const canRepick =
    Boolean(selectionPrompt) && (resumable || (isLive && paymentStatus === "failed"));

  const cardSx = {
    bgcolor: "background.paper",
    border: "1px solid",
    borderColor: "divider",
    borderRadius: 2.5,
    p: 2,
  };

  return (
    <Box sx={{ mb: 4 }}>
      <Stack direction="row" sx={{ justifyContent: "flex-end", mb: 2 }}>
        {/* A raised neutral surface rather than a saturated fill — the
            person's own words don't need to be the loudest thing on screen. */}
        <Box
          sx={{
            bgcolor: "rgba(255,255,255,0.06)",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: "14px 14px 4px 14px",
            px: 1.75,
            py: 1.1,
            maxWidth: "75%",
          }}
        >
          <Typography variant="body2" sx={{ color: "text.primary" }}>
            {turn.query}
          </Typography>
        </Box>
      </Stack>

      <Stack spacing={2}>
        {/* The agent's answer, in prose. Every clause is assembled from a
            real event — the counts from Scout, the flags from Trust, the
            sentence from Value — so this reads conversationally without
            anything being invented to make it flow. */}
        {stillThinking && !answer && (
          <Box sx={cardSx}>
            <ReasoningStream events={turn.events} isRunning />
          </Box>
        )}

        {answer && (
          <Box>
            <Typography variant="body2" sx={{ color: "text.primary", lineHeight: 1.75, mb: 1.5 }}>
              {answer}
            </Typography>

            {selectionPrompt && (
              <>
                <ProductCarousel
                  products={selectionPrompt.candidates}
                  recommendedId={selectionPrompt.recommended_id}
                  onOpen={(product) => onOpenProduct?.(product, selectionPrompt.candidates)}
                />
                <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 1.25 }}>
                  {awaitingChoice || canRepick
                    ? "Open a product to see its detail, add it to the cart, or buy it."
                    : "This choice is already made — open a product to see its detail."}
                </Typography>
              </>
            )}

            {/* The trace is the project's whole claim, so it stays — but
                folded away, because nobody reads it on every turn. */}
            <Box sx={{ mt: 2 }}>
              <Button
                size="small"
                onClick={() => setShowWorking((v) => !v)}
                startIcon={
                  <ExpandMoreIcon
                    sx={{
                      fontSize: 16,
                      transform: showWorking ? "rotate(180deg)" : "none",
                      transition: "transform 180ms",
                    }}
                  />
                }
                sx={{ color: "text.secondary", fontSize: 12, px: 1, ml: -1 }}
              >
                {showWorking ? "Hide how I got here" : "How I got here"}
              </Button>

              <Collapse in={showWorking} unmountOnExit>
                <Box sx={{ ...cardSx, mt: 1 }}>
                  <ReasoningStream events={turn.events} isRunning={false} />
                </Box>
                {turn.events.some((e) => e.type === "agent") && (
                  <Box sx={{ ...cardSx, mt: 1.5 }}>
                    <HiveCanvas mode="live" events={turn.events} clusters={BUYER_ONLY} />
                  </Box>
                )}
              </Collapse>
            </Box>
          </Box>
        )}

        {/* Payment failed / cancelled — offer a real retry rather than
            leaving the person stuck with a dead order. */}
        {isLive && paymentStatus === "failed" && orderInfo && (
          <Box
            sx={{
              ...cardSx,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 2,
              borderColor: "error.main",
              bgcolor: "rgba(239,68,68,0.08)",
            }}
          >
            <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
              <ErrorOutlineIcon sx={{ fontSize: 18, color: "error.main" }} />
              <Box>
                <Typography variant="body2" fontWeight={600} sx={{ color: "error.main" }}>
                  Payment not completed
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Retry this order, or pick a different product above.
                </Typography>
              </Box>
            </Stack>
            <Button
              size="small"
              variant="contained"
              startIcon={<ReplayIcon sx={{ fontSize: 16 }} />}
              onClick={onRetryPayment}
            >
              Retry payment
            </Button>
          </Box>
        )}

        {mandateChain && (
          <MandateChainCard chain={mandateChain} verification={mandateVerification} />
        )}

        {/* The gate verdict and the transaction timeline only say anything
            once a purchase is actually under way. Rendering them next to a
            list of search results meant every turn carried a "Waiting — no
            purchase in progress" card and an all-empty checklist, which is
            two cards of nothing. */}
        {selectionResolved && (
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
            <Box sx={cardSx}>
              <RiskGateIndicator state={riskGate.state} reason={riskGate.reason} />
              {isLive && pendingApproval && (
                <Box sx={{ mt: 1.5 }}>
                  <EscalationBanner onApprove={onApprove} onDeny={onDeny} />
                </Box>
              )}
            </Box>

            <Box sx={cardSx}>
              <TransactionTimeline
                completedKeys={timelineKeys}
                activeKey={paymentStatus === "confirmed" ? null : activeKey}
              />
            </Box>
          </Box>
        )}
      </Stack>
    </Box>
  );
}