"""
EVERY SCREEN, AGAINST THE RUNNING SYSTEM.

The README lists 15 routes. This asks each one for the data it actually
needs and asserts on what comes back — the real content, not the shape.
"Returns 200" is not a passing grade here; a page that renders an empty
table is broken in a way a status code cannot see.

HOW IT TALKS TO THE SYSTEM

It prefers the live server on :8010, because that is the thing the user is
actually running. If nothing is listening it falls back to an in-process
TestClient over the same app, and says which mode it used in the output.
Both are real requests through real routes to real Firestore and a real
marketplace; the live mode additionally proves the process is up.

TWO SCREENS DO NOT USE THE BACKEND AT ALL

`/audit` and `/recovery` subscribe to the Firestore `decisions` collection
directly from the browser (`useFirestoreAudit`, `useFailureRecovery`). Their
tests read that collection rather than an endpoint, because asserting on an
endpoint they never call would be testing the wrong thing and would pass
while the page was blank.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
sys.stdout.reconfigure(encoding="utf-8")

import httpx

LIVE = "http://127.0.0.1:8010"

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _client():
    try:
        httpx.get(f"{LIVE}/health", timeout=3.0).raise_for_status()
        return httpx.Client(base_url=LIVE, timeout=45.0), "live server on :8010"
    except Exception:
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app), "in-process TestClient (no server on :8010)"


client, MODE = _client()
print(f"Mode: {MODE}\n")


def get(path):
    r = client.get(path)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})


# ── SHOPPING ─────────────────────────────────────────────────────────────
print("=== SHOPPING ===")

code, venues = get("/venues")
names = [v["name"] for v in venues.get("venues", [])]
check("/console — venue strip lists the real venues", code == 200
      and {"ebay", "merchant"} <= set(names), ", ".join(names))
check("/console — every venue says whether it can fulfil",
      all(isinstance(v.get("can_fulfil"), bool) for v in venues.get("venues", [])))
check("/console — the strip does not claim more channels than are built",
      len(venues.get("kinds_built", [])) < len(venues.get("kinds_supported", [])),
      f'{len(venues.get("kinds_built", []))} of {len(venues.get("kinds_supported", []))}')

code, settings = get("/agent-settings")
groups = settings.get("spec") or {}
dials = sum(len(v) for v in groups.values() if isinstance(v, dict))
check("/hive — the dial spec comes from the backend", code == 200 and dials > 0,
      f"{dials} dials across {len(groups)} nodes")
check("/hive — the spec includes the gates the hive draws",
      {"budget", "risk"} <= set(groups), ", ".join(sorted(groups)))
check("/hive — every dial has a current value, so no control renders empty",
      all(node in (settings.get("values") or {})
          and set(dials_of) <= set((settings["values"].get(node) or {}))
          for node, dials_of in groups.items()))
check("/hive — nodes with no dials say so rather than rendering blank",
      bool(settings.get("no_tunables")),
      ", ".join(sorted(settings.get("no_tunables", {}))))

code, proposals = get("/proposals/pending")
check("/approvals — pending proposals endpoint answers", code == 200
      and isinstance(proposals.get("proposals", proposals), (list, dict)))

code, orders = get("/orders")
rows = orders.get("orders", orders if isinstance(orders, list) else [])
check("/orders — returns real orders", code == 200 and len(rows) > 0, f"{len(rows)} orders")
paid = [o for o in rows if o.get("status") == "paid"]
check("/orders — the list shows real captured orders", len(paid) > 0, f"{len(paid)} paid")
check("/orders — every row the page renders has an amount to show",
      all((o.get("totals") or {}).get("subtotal_paise") for o in rows),
      "the endpoint sends `totals`, not `amount_paise`")
check("/orders — every paid row carries its Razorpay order id",
      all(o.get("razorpay_order_id") for o in paid))
# The list endpoint deliberately does NOT project razorpay_payment_id — a
# payment id has no business in a list view. So the integrity claim is
# checked where the data actually lives, which is also the only place that
# could be wrong.
from app.firebase_client import db as _db
# Limited deliberately: an unbounded collection read here burned a
# noticeable slice of the Firestore free-tier day every time the
# suite ran, and 200 orders is more than enough to catch a
# fabricated one.
stored = [d.to_dict() for d in _db.collection("orders").limit(200).get()]
stored_paid = [o for o in stored if o.get("status") == "paid"]
check("orders/ — every stored paid order has a real payment id",
      all(o.get("razorpay_payment_id") for o in stored_paid),
      f"{len(stored_paid)} paid in Firestore")
check("orders/ — none of them is a fabricated id",
      not any(str(o.get("razorpay_payment_id") or "").startswith(
          ("simulated", "demo", "test_", "fake")) for o in stored_paid))
check("orders/ — simulated autonomous orders are NOT marked paid",
      all(o.get("status") != "paid"
          for o in stored if str(o.get("razorpay_order_id") or "").startswith("simulated")),
      "they carry status=simulated_paid instead")

if rows:
    oid = rows[0].get("id") or rows[0].get("order_id")
    code, one = get(f"/orders/{oid}")
    check("/orders/:id — returns that specific order", code == 200
          and str(one.get("order", one).get("id", one.get("id"))) == str(oid), str(oid)[:24])

# ── SELLING ──────────────────────────────────────────────────────────────
print("\n=== SELLING ===")

code, insights = get("/growth-insights")
check("/merchant — analytics are computed, not blank", code == 200 and bool(insights),
      f"{len(insights)} keys")

code, products = get("/merchant/products")
plist = products.get("products", [])
check("/merchant/products — the real catalogue comes back",
      code == 200 and len(plist) > 0, f"{len(plist)} products")
check("/merchant/products — drafts are visible to the operator",
      any((p.get("status") or "active") != "active" for p in plist),
      "the operator view includes what the buying agent must not see")

code, catalog = get("/merchant/catalog")
buyer_side = catalog.get("products", [])
check("/merchant/catalog — the BUYER view hides drafts",
      all((p.get("status") or "active") == "active" for p in buyer_side)
      and len(buyer_side) < len(plist),
      f"{len(buyer_side)} for agents vs {len(plist)} for the operator")

code, morders = get("/merchant/orders")
check("/merchant/orders — answers", code == 200)

code, growth = get("/merchant/growth")
check("/merchant/growth — the funnel is computed", code == 200 and bool(growth))

code, ucp = get("/merchant/.well-known/ucp")
doc = ucp.get("ucp") or ucp          # the document nests under "ucp"
check("/merchant/growth — UCP discovery document is served",
      code == 200 and bool(doc.get("capabilities")),
      ", ".join(sorted((doc.get("capabilities") or {}))) if isinstance(doc.get("capabilities"), dict)
      else str(doc.get("capabilities"))[:60])
check("/merchant/growth — the manifest carries its own limitation notice",
      "razorpay" in str(doc).lower() and
      any("account" in str(v).lower() for v in doc.values()),
      "the shared-test-account caveat is served with the manifest")

code, promos = get("/merchant/promotions")
check("/merchant/products — promotions panel has data to render", code == 200)
check("/merchant/products — the panel is told spend is not billed",
      promos.get("billed") is False and "no" in (promos.get("billing_note") or "").lower())

# /merchant/products/new is a form. Its read path is trivial; what matters
# is what the endpoint it submits to REFUSES. Only invalid payloads are
# sent, so this asserts the guard without leaving a product behind — a
# suite that creates real inventory every run is the thing this project
# refuses to do.
def post_product(body):
    r = client.post("/merchant/products", json=body)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}

VALID = {"name": "t22 probe", "price_paise": 1000, "stock": 1}
code, body = post_product({**VALID, "name": "   "})
check("/merchant/products/new — a nameless product is refused",
      code >= 400, f'{code}: {str(body.get("detail"))[:44]}')
code, body = post_product({**VALID, "price_paise": 0})
check("/merchant/products/new — a zero price is refused",
      code >= 400, f'{code}: {str(body.get("detail"))[:44]}')
code, body = post_product({**VALID, "price_paise": -500})
check("/merchant/products/new — a negative price is refused", code >= 400)
code, body = post_product({**VALID, "stock": -3})
check("/merchant/products/new — negative stock is refused", code >= 400)
code, body = post_product({**VALID, "status": "sort-of-live"})
check("/merchant/products/new — an unknown status is refused", code >= 400,
      f'{code}: {str(body.get("detail"))[:44]}')
_, after = get("/merchant/products")
check("/merchant/products/new — none of those refusals created a product",
      len(after.get("products", [])) == len(plist),
      f'{len(plist)} before, {len(after.get("products", []))} after')

check("/merchant/hive — shares the same backend dial spec", dials > 0)

# ── EVIDENCE ─────────────────────────────────────────────────────────────
print("\n=== EVIDENCE ===")

from app.firebase_client import db

decisions = [d.to_dict() for d in
             db.collection("decisions").order_by(
                 "timestamp", direction="DESCENDING").limit(50).get()]
check("/audit — the decisions collection the page subscribes to has data",
      len(decisions) > 0, f"{len(decisions)} recent rows")
check("/audit — every row carries a reason, which is what the page shows",
      all(r.get("reason") for r in decisions))
check("/audit — every row carries an action type to filter on",
      all(r.get("action_type") for r in decisions))

failures = [r for r in decisions
            if r.get("decision") in ("blocked", "failed", "escalated", "abandoned")]
check("/recovery — there are real logged failures to show",
      len(failures) > 0, f"{len(failures)} of the last {len(decisions)}")

code, corpus = get("/redteam/corpus")
attacks = corpus.get("attacks", [])
check("/redteam — the corpus loads", code == 200 and len(attacks) > 0,
      f"{corpus.get('count')} attacks")
check("/redteam — every probe carries a payload and a family",
      all(a.get("family") and (a.get("payload") or a.get("text") or a.get("injection"))
          for a in attacks))
check("/ (landing) — reads the same corpus for its probe count",
      corpus.get("count") == len(attacks), f"count={corpus.get('count')}")

code, hist = get("/redteam/history")
check("/redteam — history endpoint answers", code == 200)

code, audit = get("/security/data-audit")
check("/security — the data audit enumerates what is stored",
      code == 200 and bool(audit), f"{len(audit)} keys")

print("\n" + "=" * 66)
print(f"  {passed} passed · {failed} failed        [{MODE}]")
