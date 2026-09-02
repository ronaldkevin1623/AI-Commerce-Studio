/**
 * The hive topology — one source of truth for every node the canvas draws.
 *
 * HONESTY RULE: `state` here is not decoration. "live" means the agent is
 * wired and runs against real services today; "planned" means it does not
 * exist yet and the canvas says so, in dashed outline, with "Not built yet"
 * in its detail panel. Nothing on this canvas claims capability the
 * codebase doesn't have — a graph that flatters the project is worth less
 * than one a judge can trust.
 */

/**
 * The nodes that actually change what the agent does.
 *
 * Each of these owns a section in the backend's settings spec, so its dials
 * are read at run time by the code that makes the decision — moving Trust's
 * outlier floor from 10 to 80 takes the same twenty-five live listings from
 * 0 flagged to 10. Everything else on the canvas is real machinery too, but
 * it has nothing to turn: Payment creates a Razorpay order, Fulfilment moves
 * an order forward, and neither takes a parameter a person would set.
 *
 * Derived from the backend spec rather than guessed: if a section is added
 * there and not here, the node simply is not marked, which is the failure
 * that costs nothing.
 */
export const TUNABLE = new Set([
  "intent", "scout", "trust", "value", "budget", "risk", "negotiator",
  "ollama", "ebay",
]);

export const isTunable = (id) => TUNABLE.has(id);

export const TIER = { YOU: 0, HIVE: 1, CLUSTER: 2, SPECIALIST: 3, TOOL: 4 };

/** Tier 4 — the external services agents actually call. */
export const TOOLS = [
  {
    id: "ollama",
    label: "The AI model",
    technical: "Ollama · qwen2.5:7b",
    what: "Local LLM inference, qwen2.5:7b. Runs on this machine — no API key, no cloud round-trip, no per-token cost.",
  },
  {
    id: "ebay",
    label: "eBay",
    technical: "eBay Browse API",
    what: "OAuth2 client-credentials, item_summary/search. Production keyset, free tier. EBAY_US marketplace — India isn't supported by Browse, so prices are converted at a fixed approximate rate.",
  },
  {
    id: "firestore",
    label: "Records",
    technical: "Firestore",
    what: "Firebase free tier. Collections: customers, decisions, orders, refunds. Every gated financial action is written here.",
  },
  {
    id: "razorpay",
    label: "Razorpay",
    technical: "Razorpay API",
    what: "Test mode. Orders API, Checkout.js, Payments API, Refunds API.",
  },
];

/** Tier 2 — the three halves of the product, each a surface you can enter. */
export const CLUSTERS = [
  {
    id: "storefront",
    label: "Your shop",
    technical: "Storefront",
    glyph: "▥",
    route: "/merchant/products",
    state: "live",
    what: "The seller half: the shop an agent can discover, read, buy from and be paid through. Every node here runs today.",
  },
  {
    id: "buyer",
    label: "Buying for you",
    technical: "Buyer Hive",
    glyph: "◉",
    route: "/console",
    state: "live",
    what: "The AI buyer. Takes a free-text request, finds real listings, screens them, recommends one, gates the purchase, and pays.",
  },
  {
    id: "growth",
    label: "Growing the shop",
    technical: "Growth Hive",
    glyph: "◈",
    route: "/merchant",
    state: "partial",
    what: "The merchant half of the track: reads the decisions already in Firestore and turns them into revenue actions. Insights is built; recovery and offers are not.",
  },
  {
    id: "aftercare",
    label: "After you buy",
    technical: "Post-Purchase",
    glyph: "◍",
    route: "/recovery",
    state: "partial",
    what: "What happens around and after the transaction — talking to sellers, refunds, and watching prices.",
  },
];

/**
 * Tier 3 — the specialists. `tools` lists the services each one really
 * touches; Trust deliberately has none, because it is pure statistics over
 * data Scout already fetched. Inventing an edge there to make the diagram
 * look fuller would be exactly the kind of lie this project refuses.
 */
export const SPECIALISTS = [
  // ── Storefront ───────────────────────────────────────────────────────
  //
  // The merchant's own machinery. Listed as `live` because each one is
  // exercised by a real request today: the discovery document is served,
  // the catalogue is read by the buyer agent, sessions are opened, and
  // settlement refuses a payment id Razorpay will not confirm.
  {
    id: "discovery",
    label: "Lets agents find you",
    technical: "UCP discovery",
    glyph: "◈",
    cluster: "storefront",
    state: "live",
    tools: [],
    what: "Publishes the shop at /.well-known/ucp — the document an agent reads to learn what this store sells and how to pay it. Without it the shop is invisible to any buyer that is not a person with a browser.",
    op: "GET /merchant/.well-known/ucp",
  },
  {
    id: "catalogue",
    label: "Your products",
    technical: "Catalog",
    glyph: "▤",
    cluster: "storefront",
    state: "live",
    tools: ["firestore"],
    what: "The products an agent can actually buy: active, in stock, priced in rupees. Anything draft or out of stock is withheld rather than shown and refused later.",
    op: "GET /merchant/catalog",
  },
  {
    id: "storecheckout",
    label: "Opens the checkout",
    technical: "Checkout session",
    glyph: "▣",
    cluster: "storefront",
    state: "live",
    tools: ["firestore"],
    what: "Prices the basket from the shop's own record — never from what the buyer says it costs — and holds a session until it is paid for.",
    op: "POST /merchant/checkout",
  },
  {
    id: "settlement",
    label: "Confirms you were paid",
    technical: "Settlement",
    glyph: "⬡",
    cluster: "storefront",
    state: "live",
    tools: ["razorpay", "firestore"],
    what: "Checks the payment with Razorpay before releasing stock. An agent that simply asserts it paid is refused — that refusal has already happened 24 times against this store.",
    op: "POST /merchant/checkout/{id}/settle → razorpay.payment.fetch",
  },
  {
    id: "fulfilment",
    label: "Moves the order along",
    technical: "Fulfilment",
    glyph: "↦",
    cluster: "storefront",
    state: "live",
    tools: ["firestore"],
    what: "Paid to packed to shipped to delivered, forward only, and only once the money has actually arrived. The buyer's tracking page reads the same transitions.",
    op: "POST /merchant/checkout/{id}/fulfil",
  },
  // ── Buyer ────────────────────────────────────────────────────────────
  {
    id: "intent",
    label: "Understands you",
    technical: "Intent",
    glyph: "◈",
    cluster: "buyer",
    state: "live",
    tools: ["ollama"],
    what: "Parses free text into structured constraints: category, max price in paise, and what the person cares most about.",
    op: "ollama.chat → strict JSON {category, max_price_paise, priority}",
  },
  {
    id: "scout",
    label: "Finds products",
    technical: "Scout",
    glyph: "◎",
    cluster: "buyer",
    state: "live",
    tools: ["ebay"],
    what: "Searches real live eBay listings under the parsed budget and normalises them into one shape the rest of the pipeline expects.",
    op: "GET buy/browse/v1/item_summary/search",
  },
  {
    id: "trust",
    label: "Spots bad listings",
    technical: "Trust",
    glyph: "◇",
    cluster: "buyer",
    state: "live",
    tools: [],
    what: "Screens listings before ranking, so a suspect item never becomes the recommendation. Three real signals: price outliers against the set median, seller feedback percentage, and risky condition strings.",
    op: "Pure statistics over Scout's results — no tool call, no LLM",
  },
  {
    id: "value",
    label: "Picks the best one",
    technical: "Value",
    glyph: "◆",
    cluster: "buyer",
    state: "live",
    tools: ["ollama"],
    what: "Ranks the listings that survived Trust and explains the pick in one sentence.",
    op: "ollama.chat → {chosen_id, reason}",
  },
  {
    id: "budget",
    label: "Watches your spending",
    technical: "Budget",
    glyph: "▤",
    cluster: "buyer",
    state: "live",
    tools: ["firestore"],
    what: "Judges the running total, not the single order — cumulative spend against a session ceiling read from the customer record.",
    op: "customers/{id}.total_spend_paise vs session ceiling",
  },
  {
    id: "risk",
    label: "Approves or stops",
    technical: "Risk",
    glyph: "⬡",
    cluster: "buyer",
    state: "live",
    tools: ["firestore"],
    what: "The gate every purchase passes before any Razorpay call: stock, duplicate window, trust score, and the per-order spending bound. Returns allowed, escalated, or blocked.",
    op: "Writes the verdict + reason to decisions/",
  },
  {
    id: "payment",
    label: "Takes the payment",
    technical: "Payment",
    glyph: "▣",
    cluster: "buyer",
    state: "live",
    tools: ["razorpay", "firestore"],
    what: "Creates the real Razorpay order once the gate allows it, saves it, and hands the order id to Checkout.js.",
    op: "POST /v1/orders → orders/{receipt}",
  },

  // ── Growth ───────────────────────────────────────────────────────────
  {
    id: "insights",
    label: "Sales insights",
    technical: "Insights",
    glyph: "▦",
    cluster: "growth",
    state: "live",
    tools: ["firestore"],
    what: "Abandonment rate by stage, block reasons, funnel drop-off, and the real price and discount spread of every listing AI Commerce Studio has searched — all derived from logged rows, none estimated.",
    op: "GET /growth-insights over decisions, orders, refunds, market_scans",
  },
  {
    id: "recovery",
    label: "Wins back dropped carts",
    technical: "Cart Recovery",
    glyph: "↺",
    cluster: "growth",
    state: "planned",
    tools: ["firestore", "ollama", "razorpay"],
    what: "Reads real run_abandoned decisions, drafts a recovery nudge, and issues a genuine Razorpay Payment Link so the abandoned cart can still convert.",
    op: "Not built yet",
  },
  {
    id: "offer",
    label: "Tests discounts",
    technical: "Offer",
    glyph: "%",
    cluster: "growth",
    state: "planned",
    tools: ["firestore"],
    what: "Tests whether discounted listings actually convert better in this project's own order history, and sizes a discount from that evidence rather than a guess.",
    op: "Not built yet",
  },

  // ── Post-purchase ────────────────────────────────────────────────────
  {
    id: "negotiator",
    label: "Asks the seller",
    technical: "Negotiator",
    glyph: "✉",
    cluster: "aftercare",
    state: "live",
    tools: ["ollama", "firestore"],
    what: "Drafts a real message to the seller — grounded in that listing's actual price, condition, seller feedback and whatever Trust flagged on it. AI Commerce Studio cannot send on your behalf: eBay's Browse API is read-only and messaging needs the Sell API plus your own account OAuth. So it writes the message and hands you the listing's contact link.",
    op: "ollama.chat → draft, logged to decisions/",
  },
  {
    id: "refund",
    label: "Handles refunds",
    technical: "Refund",
    glyph: "⤺",
    cluster: "aftercare",
    state: "live",
    tools: ["razorpay", "firestore"],
    what: "Issues a real Razorpay refund against a captured payment and logs it.",
    op: "POST /v1/payments/{id}/refund → refunds/",
  },
  {
    id: "pricewatch",
    label: "Watches the price",
    technical: "Price Watch",
    glyph: "◷",
    cluster: "aftercare",
    state: "planned",
    tools: ["ebay", "firestore"],
    what: "Re-queries eBay for an item already ordered and compares today's price against the price recorded at order time.",
    op: "Not built yet",
  },
];

/**
 * Human wording for enum setting values, scoped per node — the same raw
 * value means different things in different places. "price" on Value is
 * "rank by lowest price"; "price" on Negotiator is "ask the seller for a
 * better one". A single flat map got that wrong.
 */
export const ENUM_LABELS = {
  value: {
    auto: "Auto — from request",
    discount: "Biggest discount",
    price: "Lowest price",
    rating: "Best rated",
    delivery_days: "Fastest delivery",
  },
  negotiator: {
    condition: "Condition",
    authenticity: "Proof it's genuine",
    price: "A better price",
    shipping: "Shipping",
  },
};

export function enumLabel(node, value) {
  if (typeof value === "boolean") return value ? "On" : "Off";
  return ENUM_LABELS[node]?.[value] ?? value;
}

export const BY_ID = Object.fromEntries(
  [...CLUSTERS, ...SPECIALISTS, ...TOOLS].map((n) => [n.id, n])
);

/** Which specialists depend on a given tool — read straight off the graph. */
export function dependentsOf(toolId) {
  return SPECIALISTS.filter((s) => s.tools?.includes(toolId));
}
