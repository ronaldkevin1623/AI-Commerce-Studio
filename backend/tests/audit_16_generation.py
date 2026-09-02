"""
A Galaxy S6 is not an answer to "the best Samsung under ₹30,000".

The request was for a good camera; the results included a 2015 Galaxy S6 and
several 2016 S7s. The honest fix people reach for is "check the internet
whether it is still made" — but this project has no web-search integration,
and a claim resting on scraping a search engine would be less reliable than
the data already in hand.

Product lines are numbered, and the numbering is ordered. That an S22 is
later than an S7 is arithmetic, not knowledge, and it needs no external
source. So the claim made here is narrow and provable: within this result
set, a Galaxy S7 is seventeen generations behind the newest Galaxy S on
offer.

What is tested as hard as the behaviour is the boundary of the claim: it
must never compare across lines, never assert a release year, never assert
that anything is discontinued, and never empty the page.
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

PASS, FAIL = [], []
def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

from app.agent import generation as G

print("\n=== A. Reading a model out of a title ===")
for title, expected in [
    ("Samsung Galaxy S22 | S22+ 5G 128GB", ("galaxy s", 22)),
    ("Samsung Galaxy S6 G920 32GB Factory Unlocked", ("galaxy s", 6)),
    ("Samsung Galaxy Note 5 N920T 32GB", ("galaxy note", 5)),
    ("Samsung Galaxy Note20 Ultra 5G", ("galaxy note", 20)),
    ("Samsung Galaxy Z Flip6: 512GB", ("galaxy z flip", 6)),
    ("Apple iPhone 15 Pro Max 256GB", ("iphone", 15)),
    ("Google Pixel 8 Pro", ("pixel", 8)),
    ("Samsung SM-G360T Galaxy Core Prime", None),
    ("Braided USB-C Cable 2 metre", None),
]:
    got = G.identify(title)
    check(f"{title[:40]!r} -> {expected}", got == expected, f"got {got}")

print("\n=== B. Lines are never compared with each other ===")
mixed = [{"name": "Samsung Galaxy Note20 Ultra"},
         {"name": "Samsung Galaxy S22 Ultra"},
         {"name": "Samsung Galaxy Z Flip6"}]
out = G.drop_superseded(list(mixed))
check("A Note20 is not 'behind' an S22", len(out["candidates"]) == 3,
      f"{len(out['candidates'])}/3 kept")
check("A Z Flip6 is not 'behind' an S22 either", not out["dropped"])

print("\n=== C. Superseded models within one line are set aside ===")
samsung = [{"name": f"Samsung Galaxy S{n} 128GB"} for n in (6, 7, 10, 22, 24)]
out = G.drop_superseded(list(samsung))
kept = {G.identify(c["name"])[1] for c in out["candidates"]}
check("The newest survives", 24 in kept, str(sorted(kept)))
check("Three generations back survives", 22 in kept, str(sorted(kept)))
check("The S6 and S7 are set aside",
      6 not in kept and 7 not in kept, str(sorted(kept)))

print("\n=== D. The note claims only what it can prove ===")
note = (out["note"] or "").lower()
check("It says 'behind the newest in these results'",
      "behind the newest model in these results" in note, note[:80])
check("It does NOT claim anything is discontinued",
      "discontinu" not in note and "out of production" not in note)
check("It says explicitly that it is not a production check",
      "not a check of whether a product is still in production" in note)
check("It names no release year",
      not any(str(y) in note for y in range(2000, 2031)), note[:100])

print("\n=== E. It stands down rather than emptying the page ===")
all_old = [{"name": "Samsung Galaxy S6 32GB"}, {"name": "Samsung Galaxy S7 32GB"}]
out = G.drop_superseded(list(all_old))
check("A set of only old models is returned intact",
      len(out["candidates"]) == 2 and not out["dropped"],
      f"{len(out['candidates'])} kept")

lonely = [{"name": "Samsung Galaxy S6 32GB"}, {"name": "Bamboo Monitor Stand"}]
out = G.drop_superseded(list(lonely))
check("A model with no sibling in its line is never judged",
      len(out["candidates"]) == 2)

print("\n=== F. Live ===")
from app.agent.ollama_agent import fast_intent, screen_relevance
from app.agent.catalog import search_catalog

q = "Samsung mobile with good camera under 30000"
intent = fast_intent(q)
check("The request reads as 'best'",
      (intent.get("quality_bias") or "").lower() == "best",
      intent.get("quality_bias"))

items = search_catalog(intent["category"], intent["max_price_paise"])
scr = screen_relevance(list(items), q, intent["requirements"],
                       budget_paise=intent["max_price_paise"])
kept = scr["candidates"]
out = G.drop_superseded(kept)

survivors = []
for c in out["candidates"]:
    found = G.identify(c.get("name"))
    if found and found[0] == "galaxy s":
        survivors.append(found[1])
print(f"    Galaxy S generations surviving: {sorted(set(survivors))}")
check("No Galaxy S6 or S7 survives when newer ones are on offer",
      not ({6, 7} & set(survivors)) or not out["dropped"],
      str(sorted(set(survivors))))
check("Something is still returned", len(out["candidates"]) > 0,
      f"{len(out['candidates'])} of {len(kept)}")

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
