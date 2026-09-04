import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Chip, Stack, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import FlightTakeoffIcon from "@mui/icons-material/FlightTakeoffOutlined";
import CloseIcon from "@mui/icons-material/CloseOutlined";

import { useConversation } from "../context/ConversationContext";
import { useRole } from "../context/RoleContext";
import ChatSidebar from "../components/console/ChatSidebar";
import ConversationTurn from "../components/console/ConversationTurn";
import ClarifyCard from "../components/console/ClarifyCard";
import PromptBar from "../components/console/PromptBar";
import TripItinerary from "../components/console/TripItinerary";
import AbandonRunDialog from "../components/console/AbandonRunDialog";
import ProductDetailDrawer from "../components/console/ProductDetailDrawer";
import CheckoutSheet from "../components/console/CheckoutSheet";
import FailedPurchaseCard from "../components/recovery/FailedPurchaseCard";
import OrderConfirmation from "../components/console/OrderConfirmation";
import CartPanel from "../components/console/CartPanel";
import RecommendationStrip from "../components/console/RecommendationStrip";
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

  // The shell carries a sidebar once a role is chosen, so the console only
  // renders its own when there is none — otherwise there are two.
  const { role } = useRole();
  const sidebarLayout = Boolean(role);

  const [drawerProduct, setDrawerProduct] = useState(null);
  const [drawerAlternatives, setDrawerAlternatives] = useState([]);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  // The last real payment failure, as the server recorded it. Held so the
  // console can show what stopped the agent from retrying, rather than a
  // bare "payment failed".
  const [lastFailure, setLastFailure] = useState(null);
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
  // Trip results live beside the product transcript rather than
  // inside it: an itinerary is one answer, not a turn in a search.
  const [trip, setTrip] = useState(null);
  const [tripBusy, setTripBusy] = useState(false);
  const [bookingStay, setBookingStay] = useState(false);
  // WHICH SECTOR THE AGENT IS CURRENTLY FOR.
  //
  // Sticky, not per-message. Naming a sector is a statement about what
  // you are doing next — you plan a trip over several turns, refining
  // it. Requiring "/trip" on every line would make the prefix a chore
  // and the mode a fiction. Products stays the default, and typing
  // /products returns to it.
  const [activeSector, setActiveSector] = useState("products");
  // WHAT THE AGENT ALREADY KNOWS ABOUT THIS TRIP, and which question it is
  // waiting on. Planning is a conversation — "Kolkata for 3 days" then
  // "Delhi" — and without carrying this the second message reads as a
  // brand new trip TO Delhi and the first one is silently thrown away.
  const [tripNeed, setTripNeed] = useState({});
  const [tripAwaiting, setTripAwaiting] = useState("");

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

  // Only an explicit `/trip` reaches the trip sector. With no prefix this
  // is the products path it has always been, called the same way — the
  // requirement was that the default behaviour not change, and the way to
  // keep that promise is for the default to not go through new code.
  const handleSend = (text, meta) => {
    // An explicit prefix wins for this message; otherwise the active
    // sector handles it. With no sector ever chosen this is "products",
    // which is the path the app has always taken.
    const sector = meta?.sectorId ?? activeSector;
    if (sector === "trip") {
      runTrip(text, meta?.sectorId ? "explicit_slash" : "active_sector");
      return;
    }
    // A products search clears any itinerary on screen. Leaving it pinned
    // above the results meant a stale "Still needed: Flying from?" sat over
    // a search for a phone, reading as though the agent were still waiting
    // on an answer it had stopped caring about.
    setTrip(null);
    const started = startRun(text);
    if (started) checkoutTriggeredRef.current = false;
  };

  const runTrip = async (text, source) => {
    setTripBusy(true);
    setTrip({ question: text, plan: null });
    try {
      const res = await fetch(`${API_BASE}/trip/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Everything established so far travels with each message, and
        // `answer_for` says which question this text answers — so "Delhi"
        // fills the origin instead of replacing the destination.
        body: JSON.stringify({
          ...tripNeed,
          text,
          answer_for: tripAwaiting || "",
          sector_source: source,
        }),
      });
      const plan = await res.json();
      // Remember what it now knows, and what it is still waiting for.
      if (plan?.understood) setTripNeed((n) => ({ ...n, ...plan.understood }));
      if (plan?.ok) {
        setTripAwaiting("");
      } else {
        setTripAwaiting(plan?.needs?.[0]?.name || "");
      }
      setTrip({ question: text, plan });
    } catch {
      setTrip({
        question: text,
        plan: { ok: false, detail: "The trip sector could not be reached." },
      });
    } finally {
      setTripBusy(false);
    }
  };

  // The one payable leg. It sends the hotel's record id and nothing about
  // the price — the amount is derived server-side from that row, so what
  // is charged cannot be changed from here.
  const bookStay = async (payable) => {
    setBookingStay(true);
    try {
      const res = await fetch(`${API_BASE}/trip/book`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // The originating request travels with the booking so the server can
        // re-run the itinerary and confirm this hotel is the one that won.
        // Sending only the record id would let any dataset row be charged
        // for at an honest price but under a false claim about which
        // itinerary it belonged to.
        body: JSON.stringify({
          hotel_record_id: payable.record_id,
          nights: payable.nights,
          text: trip?.question || "",
        }),
      });
      const data = await res.json();
      if (data.ok) {
        openCheckout({
          razorpay_order_id: data.razorpay_order_id,
          amount_paise: data.amount_paise,
          product_name: `${data.hotel.name} — ${data.breakdown.nights} night(s)`,
        });
      }
    } finally {
      setBookingStay(false);
    }
  };

  const handleImage = (payload) => {
    checkoutTriggeredRef.current = false;
    setTrip(null);
    startPhotoSearch(payload);
  };

  const handleNewChat = () => {
    checkoutTriggeredRef.current = false;
    setTrip(null);
    setActiveSector("products");
    setTripNeed({});
    setTripAwaiting("");
    newChat();
  };

  // Switching sector clears the other sector's answer off the screen —
  // an itinerary sitting above a product search reads as though the agent
  // were still working on it.
  // What the agent says it is for right now. One place, so the heading,
  // the hint and the mode chip can never disagree with the routing.
  const SECTOR_FACE = {
    products: {
      heading: "What should I buy for you?",
      hint: 'Try "wireless earbuds under ₹2000, fast delivery" — or type / for templates',
    },
    trip: {
      heading: "Let's plan your trip",
      hint: "Tell me where you are going, from where, and for how many nights — type /products to go back to shopping",
    },
  };

  const handleSectorChange = (sectorId) => {
    setActiveSector(sectorId);
    if (sectorId !== "trip") setTrip(null);
    // Leaving or re-entering the sector starts a fresh trip. Carrying a
    // half-answered itinerary across a mode switch would surface as the
    // agent remembering something the person thought they had left.
    setTripNeed({});
    setTripAwaiting("");
  };


  const orderInfo = useMemo(() => {
    if (cartOrder) return cartOrder;
    const orderEvent = events.find((e) => e.type === "order_created");
    return orderEvent ? orderEvent.payload : null;
  }, [events, cartOrder]);

  // Extracted so both the automatic open and the "Retry payment"
  // button reuse exactly the same real Razorpay checkout flow.
  const openCheckout = useCallback(async (order) => {
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

    const rzp = new window.Razorpay(options);

    // RAZORPAY'S OWN FAILURE EVENT.
    //
    // A card rejected inside the checkout modal never reaches `handler`, so
    // until this existed the server never heard about it at all — the most
    // common failure on this account was the one nothing recorded. The
    // payload is Razorpay's, passed through unedited, and it carries the
    // product so the purchase can be picked up again on Failure recovery
    // rather than just disappearing.
    rzp.on("payment.failed", async (event) => {
      const error = event?.error ?? {};
      const item = purchasedProduct ?? {};
      try {
        const res = await fetch(`${API_BASE}/payment-failure`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            razorpay_order_id: order.razorpay_order_id,
            amount_paise: order.amount_paise,
            customer_id: order.customer_id,
            product: {
              id: item.id, name: order.product_name ?? item.name,
              image: item.image, price_paise: order.amount_paise,
              source: item.source, url: item.url,
            },
            error: {
              code: error.code, description: error.description,
              reason: error.reason, step: error.step, source: error.source,
            },
          }),
        });
        if (res.ok) setLastFailure(await res.json());
      } catch {
        // The failure still happened; losing the record of it is bad but
        // must not also break the screen.
      }
      setPaymentStatus("failed");
    });

    rzp.open();
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
        {/* THE STOP, WHERE THE PERSON IS.
            A refusal that only shows up on another page is a refusal nobody
            sees. This sits at the top of the console until it is acted on,
            because "the agent stopped and is waiting for you" is the most
            important thing on the screen while it is true. */}
        {lastFailure && (
          <Box sx={{ px: 3, pt: 3 }}>
            <Box sx={{ maxWidth: COLUMN, mx: "auto" }}>
              <FailedPurchaseCard
                purchase={lastFailure}
                onChoose={(key) => {
                  setLastFailure(null);
                  setPaymentStatus(null);
                  // "Try again" is a FRESH attempt, not a retry of the one
                  // that failed — it re-enters the same gated path from the
                  // top. The agent still cannot do this on its own.
                  if (key === "retry" && orderInfo) openCheckout(orderInfo);
                }}
              />
            </Box>
          </Box>
        )}

        {/* Empty state: greeting and composer centred in the viewport,
            so a fresh session feels like an invitation rather than a
            blank page with a toolbar stuck to the bottom. */}
        {transcript.length === 0 && !trip ? (
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
                {(SECTOR_FACE[activeSector] ?? SECTOR_FACE.products).heading}
              </Typography>
            </Stack>

            <Box sx={{ width: "100%", maxWidth: COLUMN }}>
              <PromptBar onSend={handleSend} onImage={handleImage}
                          onSectorChange={handleSectorChange}
                          activeSector={activeSector}
                          disabled={busyThinking} tall />
            </Box>

            <Typography variant="caption" color="text.secondary" sx={{ mt: 2.5 }}>
              {(SECTOR_FACE[activeSector] ?? SECTOR_FACE.products).hint}
            </Typography>

            {/* Products first, because they are the useful thing on an empty
                screen. Clicking one opens it in the detail drawer, which
                re-fetches the listing live before anything can be bought —
                a card is a snapshot of a past order, and the price or the
                stock may have moved since. Searching again for a product
                already on screen would just be a slower way back to it. */}
            {/* Products only. These are ranked from past PURCHASES and
                product searches, so offering a USB-C cable to someone who
                just said they are planning a trip is the agent talking
                about the wrong thing. */}
            {activeSector === "products" && (
              <Box sx={{ width: "100%", maxWidth: COLUMN }}>
                <RecommendationStrip
                  onPick={(card, all) => handleOpenProduct(card, all)}
                />
              </Box>
            )}
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
            {trip && (
              <Box sx={{ mb: 2.5 }}>
                <Typography variant="body2" sx={{ mb: 1.25, fontWeight: 500 }}>
                  {trip.question}
                </Typography>
                {tripBusy ? (
                  <Typography variant="caption" color="text.secondary">
                    Assembling an itinerary from the flight, hotel and restaurant data…
                  </Typography>
                ) : (
                  <TripItinerary plan={trip.plan} onBook={bookStay} booking={bookingStay} />
                )}
              </Box>
            )}
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
        {(transcript.length > 0 || trip) && (
        <Box sx={{ px: 3, pt: 1, pb: 3 }}>
          <Box sx={{ maxWidth: COLUMN, mx: "auto" }}>
            {paymentStatus === "confirmed" && (
              <Box sx={{ mb: 1 }}>
                <PaymentStatusBanner status={paymentStatus} />
              </Box>
            )}
            {/* A mode you cannot see is a mode you will forget you are in,
                and then wonder why asking for earbuds returned a flight. */}
            {activeSector !== "products" && (
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
                <Chip
                  size="small"
                  icon={<FlightTakeoffIcon sx={{ fontSize: 14 }} />}
                  label="Planning a trip"
                  onDelete={() => handleSectorChange("products")}
                  deleteIcon={<CloseIcon sx={{ fontSize: 14 }} />}
                  sx={{ height: 22, fontSize: 11 }}
                />
                <Typography variant="caption" color="text.secondary">
                  Type <strong>/products</strong> to go back to shopping
                </Typography>
              </Stack>
            )}
            <PromptBar onSend={handleSend} onImage={handleImage}
                       onSectorChange={handleSectorChange}
                       activeSector={activeSector}
                       disabled={busyThinking} />
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