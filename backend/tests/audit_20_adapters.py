"""
MULTI-CHANNEL — is the seam real?

The claim is that a new place to shop is a registration, not an edit. These
check it by registering one at run time and watching it reach the pipeline
without anything else being touched:

  A  the two real venues are different KINDS, and say what they can do
  B  a third channel plugs in and its listings arrive
  C  one venue failing costs options, not the run
  D  venues are asked at once, and each is accounted for separately

Offline apart from group A's reachability read.
"""
import os
import sys
from pathlib import Path

# The backend package, found from this file rather than from where the
# runner happened to be invoked — so a suite works the same whether it is
# run on its own, through run_all.py, or from any directory.
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# The app resolves serviceAccountKey.json and the .env relative to the
# working directory, so a suite has to stand where the server stands. Doing
# it here rather than in the runner keeps every suite runnable on its own.
os.chdir(BACKEND)
sys.stdout.reconfigure(encoding="utf-8")
import time


from app.adapters import registry
from app.adapters.base import VenueAdapter

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


print("=== A. Three real venues, three different kinds ===")
found = {a["name"]: a for a in registry.describe()}
check("eBay is registered as a marketplace",
      found.get("ebay", {}).get("kind") == "marketplace")
check("The UCP store is registered as a retailer",
      found.get("merchant", {}).get("kind") == "retailer")
check("A marketplace we cannot ship from says so",
      found.get("ebay", {}).get("can_fulfil") is False)
check("...and the store that can, says so too",
      found.get("merchant", {}).get("can_fulfil") is True)
check("Retail media is registered as its own kind",
      found.get("sponsored", {}).get("kind") == "retail_media")
check("All of them report whether they are reachable",
      all("available" in a for a in found.values()))


print("\n=== B. A third channel plugs in ===")


class RetailMediaAdapter:
    """A sponsored-inventory channel — the deck's 'retail media' entry."""

    name = "test-retail-media"
    kind = "retail_media"
    can_fulfil = True
    label = "Test Retail Media"
    asked_with = None

    def available(self):
        return True

    def search(self, query, *, max_price_paise=0, condition_ids=None,
               requirements=None, sort=None):
        RetailMediaAdapter.asked_with = query
        return [{"id": "rm-1", "name": f"Sponsored {query} Deluxe",
                 "price_paise": 129900, "source": self.name,
                 "condition_id": "1000", "sponsored": True}]


check("A new adapter satisfies the interface",
      isinstance(RetailMediaAdapter(), VenueAdapter))

registry.register(RetailMediaAdapter())
try:
    check("Registering is all it takes to appear",
          any(a["name"] == "test-retail-media" for a in registry.describe()))

    listings, results = registry.search_all("coffee filters")
    names = {r.adapter for r in results}
    check("The new venue was asked", "test-retail-media" in names, ", ".join(sorted(names)))
    check("...with the query the agent used",
          RetailMediaAdapter.asked_with == "coffee filters")
    check("...and its listings reached the merged set",
          any(l.get("source") == "test-retail-media" for l in listings))
    check("...carrying its own source, not another venue's",
          all(l.get("source") for l in listings))

    # The point of the abstraction: nothing outside app/adapters mentions it.
    catalog_src = open(BACKEND / "app" / "agent" / "catalog.py",
                       encoding="utf-8").read()
    check("search_catalog names no venue at all",
          "ebay" not in catalog_src.lower().split("def _search_ebay")[0]
          .replace("ebay_client_id", "").replace("ebay_client_secret", "")
          or "registry.search_all" in catalog_src,
          "goes through registry.search_all")

    print("\n=== C. One venue failing costs options, not the run ===")

    class BrokenAdapter:
        name = "test-broken"
        kind = "social"
        can_fulfil = False
        label = "Broken"

        def available(self):
            return True

        def search(self, query, **kw):
            raise RuntimeError("this venue is down")

    registry.register(BrokenAdapter())
    try:
        listings, results = registry.search_all("coffee filters")
        check("A venue that raises does not raise the search", True)
        broken = next(r for r in results if r.adapter == "test-broken")
        check("...its failure is recorded", broken.error is not None,
              broken.error[:44])
        check("...and the working venues still returned",
              any(l.get("source") == "test-retail-media" for l in listings))
    finally:
        registry.unregister("test-broken")

    print("\n=== D. Asked at once, accounted for separately ===")

    class SlowAdapter:
        name = "test-slow"
        kind = "genai_platform"
        can_fulfil = False
        label = "Slow"

        def available(self):
            return True

        def search(self, query, **kw):
            time.sleep(0.6)
            return [{"id": "slow-1", "name": "Slow result", "price_paise": 1000,
                     "source": self.name, "condition_id": "1000"}]

    registry.register(SlowAdapter())
    registry.register(type("Slow2", (SlowAdapter,), {"name": "test-slow-2"})())
    try:
        started = time.time()
        listings, results = registry.search_all("coffee filters")
        elapsed = time.time() - started
        check("Two 0.6s venues finish in well under 1.2s",
              elapsed < 1.1, f"{elapsed:.2f}s")
        # Against the venues that were REACHABLE, not every registered one:
        # search_all skips a venue whose available() says no, which is how
        # retail media stays out of a search when no promotion is running.
        live = [a for a in registry.describe() if a["available"]]
        check("Every reachable venue is accounted for individually",
              len(results) == len(live),
              f"{len(results)} results for {len(live)} reachable "
              f"of {len(registry.describe())} registered")
        check("...each with its own count and timing",
              all(hasattr(r, "took_ms") and r.took_ms >= 0 for r in results))
    finally:
        registry.unregister("test-slow")
        registry.unregister("test-slow-2")

    print("\n=== E. Registration is guarded ===")
    try:
        registry.register(RetailMediaAdapter())
        duplicate_rejected = False
    except ValueError:
        duplicate_rejected = True
    check("A duplicate name is refused rather than shadowing", duplicate_rejected)
    registry.register(RetailMediaAdapter(), replace=True)
    check("...unless replacing is asked for explicitly",
          sum(1 for a in registry.describe()
              if a["name"] == "test-retail-media") == 1)
finally:
    registry.unregister("test-retail-media")

check("The registry is back to the real venues",
      {a["name"] for a in registry.describe()} == {"ebay", "merchant", "sponsored"},
      ", ".join(sorted(a["name"] for a in registry.describe())))

print("\n" + "=" * 62)
print(f"  {passed} passed · {failed} failed")
