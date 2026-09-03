"""
PUT THE DEMO BACK, IN ONE COMMAND.

    python tests/seed_demo.py

The Firestore emulator keeps nothing between runs — stop it and every
product, promotion and order is gone. That is fine for a demo and awful
five minutes before recording, so this re-creates exactly what the demo
script in docs/DEMO.md expects:

    the merchant catalogue          6 products
    a promotion on the USB-C hub    so the retail-media strip has something
    two replenishment histories     one that clears every gate, one that
                                    is deliberately too expensive and gets
                                    blocked, so the demo can show both

Everything it writes is marked. Seeded orders carry `demo_seeded: true` and
`status: "demo_paid"`, never `paid` — the integrity suite asserts that no
order is marked paid without a real payment id, and demo data must not be
the thing that breaks it.

Safe to run against the real project too, but there is rarely a reason to:
the point of it is the emulator, which starts empty every time.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
sys.stdout.reconfigure(encoding="utf-8")

import httpx

# Overridable so the refusal paths can be exercised against a stub server
# without a real backend, and with no possibility of a real write.
BASE = os.environ.get("CARTPILOT_SEED_BASE", "http://127.0.0.1:8010")

# Priced so the live eBay result lands under the Rs1,500 per-order cap for
# the cable and over it for the coffee. That contrast is the demo: the
# agent buying unattended, and the agent refusing to, side by side.
HISTORIES = [
    {"product": "USB C charging cable braided 2m", "price_paise": 39900,
     "cycle_days": 30, "purchases": 4},
    {"product": "Nescafe Gold Instant Coffee Refill 200g", "price_paise": 49900,
     "cycle_days": 30, "purchases": 4},
]


def step(label: str, fn) -> bool:
    try:
        detail = fn()
        print(f"  [ok]   {label}" + (f" — {detail}" if detail else ""))
        return True
    except Exception as exc:
        print(f"  [FAIL] {label} — {exc}")
        return False


def main() -> int:
    try:
        # ASK THE SERVER WHICH STORE IT IS ON, do not infer it.
        #
        # This used to read this process's own environment and .env text.
        # That was wrong in a way that gets worse now .env never changes:
        # the seeder writes through a RUNNING SERVER over HTTP, and that
        # server's datastore is fixed by how IT was launched. The two can
        # disagree, and the seeder would then announce "emulator" while
        # filling real Firestore with demo rows.
        health = httpx.get(f"{BASE}/health", timeout=5)
        health.raise_for_status()
    except Exception:
        print(f"\nNothing is listening on {BASE}.")
        print("Start the backend first, then run this again.\n")
        return 1

    binding = (health.json() or {}).get("datastore")
    if not binding:
        # An older server that does not report it. Refusing beats guessing:
        # seeding demo rows into real Firestore by accident is the exact
        # mistake this check exists to prevent.
        print("\nThat server does not report which datastore it uses.")
        print("Refusing to seed rather than guess.\n")
        return 1

    emulator = binding.startswith("emulator")
    if not emulator and "--allow-real" not in sys.argv:
        # REFUSE, do not merely warn.
        #
        # This writes demo rows — seeded orders, a demo promotion, a stub
        # catalogue. Once they are in the store they are indistinguishable
        # from real activity, and the money reconciliation reads that same
        # store. A warning printed above a wall of progress output is not a
        # decision anybody actually makes. Requiring the flag is.
        print(f"\nThat server is on REAL Firestore ({binding}).")
        print("Refusing to seed demo rows into real data.")
        print("\nIf that is genuinely what you want: re-run with --allow-real\n")
        return 1

    print(f"\nSeeding demo state via {BASE} -> {binding}"
          f"{'' if emulator else '   *** REAL FIRESTORE, --allow-real given ***'}\n")

    ok = True
    ok &= step("merchant catalogue", lambda: str(
        httpx.post(f"{BASE}/merchant/seed", params={"force": "true"},
                   timeout=60).json().get("products")) + " products")

    def promo():
        r = httpx.post(f"{BASE}/merchant/promotions", timeout=30, json={
            "product_id": "cds-usbc-hub", "bid_paise": 200,
            "daily_budget_paise": 5000, "active": True})
        r.raise_for_status()
        return "USB-C hub, Rs2.00 per placement, Rs50.00/day"
    ok &= step("retail-media promotion", promo)

    for history in HISTORIES:
        def seed(h=history):
            r = httpx.post(f"{BASE}/autonomy/demo/seed", json=h, timeout=60)
            r.raise_for_status()
            return f"{h['purchases']} purchases, {h['cycle_days']}-day cycle"
        ok &= step(f"history: {history['product'][:38]}", seed)

    def on():
        httpx.post(f"{BASE}/autonomy/kill-switch", json={"enabled": True},
                   timeout=30).raise_for_status()
        return "ON — the agent will buy unattended"
    ok &= step("autonomy kill switch", on)

    # The already_bought gate refuses to buy the same item twice inside its
    # replenishment cycle. That is correct, and it means a demo run after a
    # previous one will show a BLOCK rather than a purchase. Worth saying
    # here rather than letting it be a surprise on camera.
    try:
        history = httpx.get(f"{BASE}/autonomy/history", timeout=30).json()
        bought = [h for h in (history.get("actions") or history.get("history") or [])
                  if str(h.get("outcome")) == "bought"]
    except Exception:
        bought = []
    if bought:
        print()
        print(f"  NOTE: {len(bought)} autonomous purchase(s) already on record.")
        print("        The already_bought gate will block a repeat of those items.")
        print("        For a clean run that ends in a purchase, restart the")
        print("        emulator (it keeps nothing) and run this again.")

    venues = httpx.get(f"{BASE}/venues", timeout=30).json()
    live = [v["name"] for v in venues["venues"] if v["available"]]
    print(f"\n  venues live: {', '.join(live)}")
    print(f"  {venues['searchable']} searchable · {venues['fulfillable']} can ship\n")
    if "sponsored" not in live:
        print("  NOTE: the sponsored venue is not live — the promoted strip")
        print("        will not appear. Check /merchant/promotions.\n")

    print("Demo state ready.\n" if ok else "Some steps failed — see above.\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
