"""
EVERY SUITE, IN ONE COMMAND.

    python tests/run_all.py            # everything
    python tests/run_all.py --offline  # no network, no Firestore, no model
    python tests/run_all.py --list     # what each suite needs, and why

WHY THE SUITES ARE SPLIT BY WHAT THEY NEED

Most of these talk to something real: live eBay listings, the project's
Firestore, a local model. That is deliberate — a suite that mocks the
marketplace proves the mock works — but it means a run's result depends on
things outside the code, and a reader deserves to know which result is
which. `--offline` is the subset whose outcome is a fact about this
repository and nothing else. It is the one to run before every change.

The full run is the one that catches the interesting failures, because the
interesting failures are in the seams. It is also the one that can go red
because eBay changed its inventory overnight, which is a real cost of
testing against real data and is not pretended away here.

WHAT A GREEN RUN DOES NOT MEAN

No suite here captures a payment. Six payments HAVE been captured on this
Razorpay test account, all netbanking — but a person made them by clicking
through the bank simulator, which is exactly why no test can: the only rail
this account completes needs a human at the bank's login page. Order
creation, signature verification, the webhook and every gate are exercised
automatically; the capture is not, and cannot be.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent

# What each suite needs to run, and what it is for. Written down rather than
# inferred: a grep for "httpx" cannot tell a live call from a helper that
# happens to live in a module with a network client in it, and guessing
# wrong would either skip a real test or fail an offline run.
#
#   net       live eBay Browse API (credentials in .env)
#   store     the project's Firestore
#   model     the local Ollama model
SUITES = [
    ("audit_1_integrity",    {"store"},         "Nothing fabricated; the risk gate, mandate chain and fulfilment guard all fire"),
    ("audit_2_agent",        {"model"},         "The agent's reasoning is computed, not written by a model"),
    ("audit_3_live",         {"net", "store"},  "The live path end to end, against real listings"),
    ("audit_4_refine",       set(),             "Follow-up turns narrow the previous results instead of re-searching"),
    ("audit_5_direct_buy",   {"net", "store"},  "Buy-now skips the shortlist without skipping a gate"),
    ("audit_6_preferences",  {"store"},         "History informs ties and nothing else"),
    ("audit_7_explain",      set(),             "The explanation names only facts the listing carries"),
    ("audit_8_quality",      {"net"},           "Quality scoring and Bayesian shrinkage over seller feedback"),
    ("audit_9_brands",       {"net"},           "Brand standing comes from eBay's own aspect distribution"),
    ("audit_10_refund",      {"net", "store"},  "Refunds, and the abandonment trail"),
    ("audit_11_pii",         {"store"},         "Inventory of every field stored anywhere — a report, not a pass/fail"),
    ("audit_12_category",    {"net", "model"},  "Category inference from free text"),
    ("audit_13_attributes",  {"net", "model"},  "Measurements and specs are attributes, not search words"),
    ("audit_14_matching",    {"model"},         "Model numbers are mandatory; accessories are demoted"),
    ("audit_15_capability",  {"net", "model"},  "The capability claims in the README, each exercised"),
    ("audit_16_generation",  {"net", "model"},  "Generated copy is grounded in listing fields"),
    ("audit_17_conversation", set(),            "The five conversation routes, 86 assertions, no model call"),
    ("audit_18_autonomy",    {"store"},         "Level 5: prediction, the five gates, and the dry run"),
    ("audit_19_engines",     set(),             "The dual engine boundary — GenAI cannot name a product"),
    ("audit_20_adapters",    {"net"},           "The venue seam: a third channel plugs in without core changes"),
    ("audit_21_sponsored",   {"store"},         "Retail media: the ranking cannot be bought"),
    ("audit_dials",          {"net", "model"},  "Every tunable setting is read somewhere that matters"),
    ("audit_22_surfaces",    {"net", "store"},  "All 15 documented routes, asserted on real content"),
    ("audit_23_pipeline",    {"net", "store"},  "14 of the 15 pipeline stages, each with a case built to fail it"),
    # Needs the datastore only. The growth agents read the store's own
    # records and spend the merchant's margin — no marketplace, no payment
    # provider — so this suite still runs when eBay is rate-limiting or
    # Razorpay is unreachable, which is a property worth keeping.
    ("audit_24_growth",      {"store"},         "The merchant-side gate: five bounds, and campaigns that can end"),
]

# Suites that report in their own words rather than "N passed · N failed".
# Their exit status still decides pass/fail; this only stops the summary
# claiming it could not find a result.
NARRATIVE = {"audit_11_pii", "audit_dials"}

# Assertions important enough to quote even when their suite passes.
# Normally only failing suites have their output shown, which is right —
# but it means a green run reports "audit_3_live: 20 passed" and says
# nothing about whether the money actually reconciled. That is the one
# result somebody reading this at a distance needs stated, not inferred
# from a total.
HIGHLIGHT = (
    "confirmed by Razorpay",
    "payment moved money without this app recording",
    "Every stored payment id names a payment Razorpay actually took",
    "Orders we call refunded are refunded at Razorpay too",
)

RESULT = re.compile(r"(\d+) passed\s*·\s*(\d+) failed")
DIALS = re.compile(r"(\d+)/(\d+) dials verified")


def run(name: str) -> dict:
    started = time.time()
    proc = subprocess.run(
        [sys.executable, str(HERE / f"{name}.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(BACKEND),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    took = time.time() - started

    passed = failed = None
    match = RESULT.search(out)
    if match:
        passed, failed = int(match.group(1)), int(match.group(2))
    elif DIALS.search(out):
        got, total = (int(g) for g in DIALS.search(out).groups())
        passed, failed = got, total - got

    return {"name": name, "passed": passed, "failed": failed,
            "took": took, "code": proc.returncode, "output": out}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true",
                        help="only suites needing no network, Firestore or model")
    parser.add_argument("--list", action="store_true",
                        help="show what each suite needs and exit")
    parser.add_argument("--only", metavar="NAME",
                        help="run one suite by name (or a substring of it)")
    args = parser.parse_args()

    if args.list:
        for name, needs, why in SUITES:
            tag = ", ".join(sorted(needs)) or "offline"
            print(f"  {name:<22} [{tag:<16}] {why}")
        return 0

    chosen = [s for s in SUITES
              if (not args.offline or not s[1])
              and (not args.only or args.only in s[0])]
    if not chosen:
        print("No suites matched.")
        return 1

    scope = "offline" if args.offline else "full"
    print(f"Running {len(chosen)} {scope} suite(s)\n")

    results = []
    for name, needs, _why in chosen:
        tag = ",".join(sorted(needs)) or "offline"
        print(f"  {name:<22} [{tag}] … ", end="", flush=True)
        outcome = run(name)
        results.append(outcome)
        if outcome["passed"] is None and name in NARRATIVE:
            # audit_11_pii inventories every field the project stores. It has
            # nothing to assert — the output IS the finding — so it reports
            # rather than passing, and saying "no result" would read as broken.
            print(f"report, exit {outcome['code']}  ({outcome['took']:.1f}s)")
        elif outcome["passed"] is None:
            print(f"NO RESULT (exit {outcome['code']}, {outcome['took']:.1f}s)")
        else:
            state = "ok" if not outcome["failed"] else f"{outcome['failed']} FAILED"
            print(f"{outcome['passed']} passed, {state}  ({outcome['took']:.1f}s)")

    total_pass = sum(r["passed"] or 0 for r in results)
    total_fail = sum(r["failed"] or 0 for r in results)
    broken = [r for r in results
              if r["passed"] is None and r["name"] not in NARRATIVE]
    # A report suite still has to exit cleanly; it just has nothing to count.
    broken += [r for r in results
               if r["name"] in NARRATIVE and r["code"] != 0]

    print("\n" + "=" * 68)
    ran = len(results) - len(broken)
    print(f"  {total_pass} assertions passed · {total_fail} failed "
          f"across {ran} suites "
          f"({sum(r['took'] for r in results):.0f}s)")
    if broken:
        # Saying "0 failed" while suites were crashing is the kind of green
        # that hides a red. A suite that could not run is not a suite that
        # passed, and the headline has to say so.
        print(f"  {len(broken)} SUITE(S) COULD NOT RUN — the count above "
              f"covers {ran} of {len(results)}:")
        for r in broken:
            out = [ln.strip() for ln in r["output"].splitlines() if ln.strip()]
            # The LAST line is not reliably the informative one — a suite can
            # die on a quota error and then emit a deprecation warning on the
            # way out, which is what gets printed and tells the reader
            # nothing. Prefer the last line that actually looks like a
            # failure.
            blame = next((ln for ln in reversed(out)
                          if any(k in ln for k in
                                 ("Error", "Exception", "Quota", "Traceback",
                                  "refused", "timeout"))), out[-1] if out else "")
            print(f"    {r['name']}: {blame[:86] or 'no output'}")

    highlighted = [ln.strip() for r in results
                   for ln in r["output"].splitlines()
                   if any(h in ln for h in HIGHLIGHT)]
    if highlighted:
        print("\n  Money reconciliation:")
        for line in highlighted:
            print(f"    {line}")

    for result in results:
        if result["failed"]:
            print(f"\n--- {result['name']} ---")
            for line in result["output"].splitlines():
                if "[FAIL]" in line or line.strip().startswith("FAILED:"):
                    print(f"  {line.strip()}")
    for result in broken:
        print(f"\n--- {result['name']} produced no result line ---")
        print("\n".join(f"  {ln}" for ln in result["output"].splitlines()[-12:]))

    return 1 if (total_fail or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
