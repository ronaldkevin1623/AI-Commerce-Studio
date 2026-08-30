import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Stack, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";

import { useConversation } from "../context/ConversationContext";
import ChatSidebar from "../components/console/ChatSidebar";
import { useRole } from "../context/RoleContext";
import ConversationTurn from "../components/console/ConversationTurn";
import ClarifyCard from "../components/console/ClarifyCard";
import PromptBar from "../components/console/PromptBar";
import AbandonRunDialog from "../components/console/AbandonRunDialog";
import ProductDetailDrawer from "../components/console/ProductDetailDrawer";
import CheckoutSheet from "../components/console/CheckoutSheet";
import OrderConfirmation from "../components/console/OrderConfirmation";
import CartPanel from "../components/console/CartPanel";
import { API_BASE, RAZORPAY_KEY_ID } from "../config";

// One column width for the whole console. The transcript used to be 900px
// wide while the composer sat at 680 and the empty-state composer at 640, so
// the thing you type into never lined up with the thing you'd just read.
const COLUMN = 820;

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
        mb: 2,
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

export default function AgentConsolePage() {
  const checkoutTriggeredRef = useRef(false);
  const transcriptEndRef = useRef(null);

  const { role } = useRole();
  const sidebarLayout = Boolean(role);

  const [drawerProduct, setDrawerProduct] = useState(null);
  const [drawerAlternatives, setDrawerAlternatives] = useState([]);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deliveryLocation, setDeliveryLocation] = useState(null);
  const [paymentRef, setPaymentRef] = useState(null);
  // The listing being bought. Kept because order_created only carries the
  // amount and a name — the delivery estimate, postage and image all live on
  // the product, and the checkout sheet needs them.
  const [purchasedProduct, setPurchasedProduct] = useState(null);
  // A cart checkout creates its own order outside the WebSocket run, so it
  // can't come from the order_created event like a single purchase does.
  const [cartOrder, setCartOrder] = useState(null);

  const {
    events,
    isRunning,
    pendingApproval,
    pendingSelection,
    clarify,
    answerClarify,
    selectProduct,
    respondToEscalation,
    transcript,
    sessionList,
    activeSessionId,
    paymentStatus,
    setPaymentStatus,
    sidebarCollapsed,
    setSidebarCollapsed,
    startRun,
    newChat,
    openSession,
    runStage,
    abandonPrompt,
    continueRun,
    terminateRun,
    startPhotoSearch,
  } = useConversation();

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events, transcript]);

  // Only block the composer while the agent is genuinely mid-thought. A run
  // paused at the product picker keeps its socket open, and treating that as
  // "busy" left no way to ask for anything else.
  const busyThinking = isRunning && !pendingSelection && !pendingApproval;

  const handleSend = (text) => {
    const started = startRun(text);
    if (started) checkoutTriggeredRef.current = false;
  };

  const handleImage = (payload) => {
    checkoutTriggeredRef.current = false;
    startPhotoSearch(payload);
  };

  const handleNewChat = () => {
    checkoutTriggeredRef.current = false;
    newChat();
  };


  const orderInfo = useMemo(() => {
    if (cartOrder) return cartOrder;
    const orderEvent = events.find((e) => e.type === "order_created");
    return orderEvent ? orderEvent.payload : null;
  }, [events, cartOrder]);

  // Extracted so both the automatic open and the "Retry payment"
  // button reuse exactly the same real Razorpay checkout flow.
  const openCheckout = useCallback((order) => {
    if (!order) return;
    setPaymentStatus(null);

    const options = {
      key: RAZORPAY_KEY_ID,
      amount: order.amount_paise,
      currency: "INR",
      name: "AI Commerce Studio",
      description: order.product_name,
      order_id: order.razorpay_order_id,
      handler: async (response) => {
        try {
          const res = await fetch(`${API_BASE}/verify-payment`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_order_id: response.razorpay_order_id,
              customer_id: order.customer_id,
            }),
          });
          setPaymentRef(response);
          setPaymentStatus(res.ok ? "confirmed" : "failed");
        } catch {
          setPaymentStatus("failed");
        }
      },
      modal: { ondismiss: () => setPaymentStatus("failed") },
      theme: { color: "#ECECEE" },
    };

    new window.Razorpay(options).open();
  }, []);

  // Re-pick after a failed payment: the agent's socket is closed, so a
  // fresh order is created over REST (server-side risk gate still runs).
  const handleRepick = useCallback(async (product) => {
    setPurchasedProduct(product);
    try {
      const res = await fetch(`${API_BASE}/repick-order`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product }),
      });
      if (!res.ok) {
        setPaymentStatus("failed");
        return;
      }
      const newOrder = await res.json();
      openCheckout(newOrder);
    } catch {
      setPaymentStatus("failed");
    }
  }, [openCheckout]);

  // Once the gate has allowed the order, show the checkout sheet rather than
  // throwing Razorpay's modal straight at the person. The delivery address
  // is collected here, and "Pay now" is what opens Razorpay — so the charge
  // is always a deliberate second action, not a popup that appeared.
  useEffect(() => {
    if (!orderInfo || checkoutTriggeredRef.current) return;
    checkoutTriggeredRef.current = true;
    setCheckoutOpen(true);
  }, [orderInfo]);

  // Payment confirmed — swap the sheet for the receipt.
  useEffect(() => {
    if (paymentStatus === "confirmed") {
      setCheckoutOpen(false);
      setConfirmOpen(true);
    }
  }, [paymentStatus]);

  const handleSelectProduct = useCallback(
    (product) => {
      setPurchasedProduct(product);
      selectProduct(product.id);
    },
    [selectProduct]
  );

  const handleOpenProduct = useCallback((product, all) => {
    setDrawerProduct(product);
    setDrawerAlternatives((all ?? []).filter((c) => String(c.id) !== String(product.id)));
  }, []);

  const handlePay = useCallback(
    (location) => {
      setDeliveryLocation(location);
      openCheckout(orderInfo);
    },
    [openCheckout, orderInfo]
  );

  return (
    <Box sx={{ display: "flex", height: "100%", minHeight: 0 }}>
      {/* The app shell already carries a sidebar with conversation history
          in it, so this second panel would be two nested lists of the same
          chats side by side. It stays for the roleless case only. */}
      {!sidebarLayout && (
        <ChatSidebar
          turns={sessionList}
          activeId={activeSessionId}
          onSelect={openSession}
          onNewChat={handleNewChat}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        />
      )}

      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Empty state: greeting and composer centred in the viewport,
            so a fresh session feels like an invitation rather than a
            blank page with a toolbar stuck to the bottom. */}
        {transcript.length === 0 ? (
          <Box
            sx={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              px: 3,
              pb: 8,
            }}
          >
            <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", mb: 3 }}>
              <AutoAwesomeIcon sx={{ fontSize: 26, color: "primary.light" }} />
              <Typography variant="h1" sx={{ fontSize: 30, fontWeight: 500 }}>
                What should I buy for you?
              </Typography>
            </Stack>

            <Box sx={{ width: "100%", maxWidth: COLUMN }}>
              <PromptBar onSend={handleSend} onImage={handleImage} disabled={busyThinking} tall />
            </Box>

            <Typography variant="caption" color="text.secondary" sx={{ mt: 2.5 }}>
              Try "wireless earbuds under ₹2000, fast delivery" — or type / for templates
            </Typography>
          </Box>
        ) : (
        <Box
          sx={{
            flex: 1,
            overflowY: "auto",
            px: 3,
            py: 3,
            // Reserving the scrollbar gutter on both edges keeps the centred
            // column centred. Without it the scrollbar eats 8px from one side
            // only, and the transcript sits 4px left of the composer below it.
            scrollbarGutter: "stable both-edges",
          }}
        >
          <Box sx={{ maxWidth: COLUMN, mx: "auto" }}>
            {transcript.map((turn) => (
              <Box key={turn.id} id={`turn-${turn.id}`}>
                <ConversationTurn
                  turn={turn}
                  isLive={turn.id === "live"}
                  isRunning={isRunning}
                  pendingApproval={turn.id === "live" && pendingApproval}
                  pendingSelection={turn.id === "live" && pendingSelection}
                  onSelectProduct={handleSelectProduct}
                  onApprove={() => respondToEscalation(true)}
                  onDeny={() => respondToEscalation(false)}
                  paymentStatus={turn.id === "live" ? paymentStatus : null}
                  onRetryPayment={() => openCheckout(orderInfo)}
                  onRepick={handleRepick}
                  onOpenProduct={handleOpenProduct}
                />
              </Box>
            ))}
            {/* The run is paused on the socket waiting for this, so it sits
                at the foot of the transcript where the next thing to do
                belongs. Skip answers it too — an unanswered question would
                hold the pipeline open indefinitely. */}
            {clarify && (
              <ClarifyCard
                questions={clarify.questions}
                candidateCount={clarify.candidate_count}
                onSubmit={answerClarify}
                onSkip={() => answerClarify({})}
              />
            )}

            <div ref={transcriptEndRef} />
          </Box>
        </Box>
        )}

        {/* Once a conversation exists the composer docks to the bottom.
            No hard divider — just breathing room and a soft shadow. */}
        {transcript.length > 0 && (
        <Box sx={{ px: 3, pt: 1, pb: 3 }}>
          <Box sx={{ maxWidth: COLUMN, mx: "auto" }}>
            {paymentStatus === "confirmed" && (
              <Box sx={{ mb: 1 }}>
                <PaymentStatusBanner status={paymentStatus} />
              </Box>
            )}
            <PromptBar onSend={handleSend} onImage={handleImage} disabled={busyThinking} />
          </Box>
        </Box>
        )}
      </Box>

      <AbandonRunDialog
        open={abandonPrompt}
        stage={runStage}
        onContinue={continueRun}
        onTerminate={terminateRun}
      />

      {/* A cart checkout produces the same shape of order as a single buy,
          so it drops into the same sheet → Razorpay → confirmation path. */}
      <CartPanel
        onOrderCreated={(order, items) => {
          setPurchasedProduct(items[0]);
          checkoutTriggeredRef.current = true;
          setCartOrder(order);
          setCheckoutOpen(true);
        }}
      />

      <ProductDetailDrawer
        open={Boolean(drawerProduct)}
        product={drawerProduct}
        alternatives={drawerAlternatives}
        query={transcript[transcript.length - 1]?.query}
        onClose={() => setDrawerProduct(null)}
        onSelectAlternative={(alt) => {
          setDrawerAlternatives((prev) =>
            [drawerProduct, ...prev].filter((c) => c && String(c.id) !== String(alt.id))
          );
          setDrawerProduct(alt);
        }}
        onBuyNow={(product) => {
          setDrawerProduct(null);
          if (pendingSelection) handleSelectProduct(product);
          else handleRepick(product);
        }}
      />

      <CheckoutSheet
        open={checkoutOpen}
        product={{
          // The listing supplies delivery, postage and imagery; the order
          // supplies the authoritative amount actually being charged.
          ...(purchasedProduct ?? {}),
          ...(orderInfo ?? {}),
          name: orderInfo?.product_name ?? purchasedProduct?.name,
          price_paise: orderInfo?.amount_paise ?? purchasedProduct?.price_paise,
          image: purchasedProduct?.image,
          shipping_cost_paise: purchasedProduct?.shipping_cost_paise,
          delivery_estimate_from: purchasedProduct?.delivery_estimate_from,
          delivery_estimate_to: purchasedProduct?.delivery_estimate_to,
        }}
        onClose={() => setCheckoutOpen(false)}
        onPay={handlePay}
        busy={false}
        error={paymentStatus === "failed" ? "Payment didn't complete. Try Netbanking." : null}
      />

      <OrderConfirmation
        open={confirmOpen}
        order={orderInfo ? { ...orderInfo, image: purchasedProduct?.image } : null}
        payment={paymentRef}
        location={deliveryLocation}
        onClose={() => setConfirmOpen(false)}
        onViewOrder={() => {
          setConfirmOpen(false);
          window.location.href = "/orders";
        }}
      />
    </Box>
  );
}