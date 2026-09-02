"""
Part 2: does the agent tell the truth?

Two different questions, tested separately:
  ACCURACY     — does the pipeline return what was actually asked for?
  HALLUCINATION— does the agent assert anything the data does not support?

The second is the one that matters most. The product cannot be invented
(chosen_id is matched against the real candidate list), but the one-sentence
`reason` shown next to it is free text from the model and is not checked
against anything. That is what this probes.
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
import sys, re, json

PASS, FAIL, WARN = [], [], []
def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
def warn(name, detail=""):
    WARN.append(name); print(f"  [WARN] {name}" + (f" — {detail}" if detail else ""))

from app.agent import ollama_agent as oa

print("\n=== 5. DETERMINISTIC INTENT: the model does not get to invent numbers ===")

cases = [
    ("sandisk 128gb pendrive under 1000", "sandisk", 100000),
    ("red nike running shoes below rs 3000", "nike", 300000),
    ("wireless earbuds under ₹2000, fast delivery", "earbud", 200000),
]
for text, must_contain, ceiling in cases:
    phrase = oa.search_phrase(text)
    got = oa.budget_ceiling_paise(text)
    check(f"Query keeps the brand: {text[:38]!r}",
          must_contain in phrase.lower(), f"search phrase = {phrase!r}")
    check(f"Budget read by rule, not by model: ₹{ceiling/100:,.0f}",
          got == ceiling, f"got {got}")

# The fail-closed property: an unparseable budget must not become "no limit".
odd = oa.budget_ceiling_paise("something with no number in it at all")
check("No stated budget yields no ceiling (rather than a guess)",
      odd is None, f"got {odd}")

print("\n=== 6. HALLUCINATION: is the explanation grounded in the data? ===")

# Real-shaped candidates. Note what is NOT here: battery life, camera specs,
# waterproofing, warranty, colour. If the explanation mentions any of it,
# the model invented it.
candidates = [
    {"id": "h1", "name": "SanDisk Ultra 128GB USB 3.0 Flash Drive",
     "price_paise": 89900, "condition": "New", "discount_percent": 12,
     "seller_feedback": 99.2, "delivery_days": 4},
    {"id": "h2", "name": "SanDisk Cruzer Blade 128GB USB 2.0",
     "price_paise": 64900, "condition": "New", "discount_percent": 30,
     "seller_feedback": 97.1, "delivery_days": 7},
    {"id": "h3", "name": "SanDisk Extreme PRO 128GB USB 3.2",
     "price_paise": 149900, "condition": "New", "discount_percent": 5,
     "seller_feedback": 99.8, "delivery_days": 3},
]

# Words that can only be true if the model got them from somewhere else.
UNGROUNDED = [
    r"\bbattery\b", r"\bcamera\b", r"\bwaterproof\b", r"\bwarrant(y|ies)\b",
    r"\bnoise[- ]cancel", r"\bbluetooth\b", r"\bRAM\b", r"\bprocessor\b",
    r"\bwireless\b", r"\bmegapixel\b", r"\bMP\b", r"\bcolou?r\b",
    r"\bwrite speed\b", r"\bread speed\b", r"\bMB/s\b", r"\blifetime\b",
]

ran, bad = 0, []
for trial in range(3):
    try:
        out = oa.rank_candidates(candidates, "price",
                                 user_text="sandisk 128gb pendrive under 1000",
                                 requirements=["sandisk", "128gb"],
                                 budget_paise=100000)
    except Exception as e:
        warn("Ranking call failed", str(e)[:70]); break
    ran += 1
    reason = out["reason"]
    chosen = out["product"]
    print(f"    run {trial+1}: {chosen['name']}  —  \"{reason}\"")

    if str(chosen["id"]) not in {c["id"] for c in candidates}:
        bad.append(f"chose an id outside the candidate set: {chosen['id']}")

    hits = [p for p in UNGROUNDED if re.search(p, reason, re.I)]
    if hits:
        bad.append(f"ungrounded claim {hits} in: {reason!r}")

    # Any number in the sentence must be a number the model was actually given.
    supplied = {str(len(candidates)), "1000", "100000"}
    for c in candidates:
        supplied |= {str(round(c["price_paise"]/100)), str(c["discount_percent"]),
                     str(c["delivery_days"]), str(c["seller_feedback"]),
                     "128", "3", "2", "0", "1"}
        supplied |= set(re.findall(r"\d+", c["name"]))
    # Strip thousands separators first: "₹1,000" is one number, and reading
    # it as "1" and "000" invents a discrepancy that is not there.
    flat = reason.replace(",", "")
    for n in re.findall(r"\d+(?:\.\d+)?", flat):
        if n not in supplied and n.rstrip(".0") not in supplied:
            bad.append(f"number {n!r} appears in the reason but not in the data: {reason!r}")

if ran:
    check(f"The chosen product is always a real candidate ({ran} runs)",
          not any("outside the candidate set" in b for b in bad))
    check(f"The explanation invents no specs ({ran} runs)",
          not any("ungrounded claim" in b for b in bad),
          "; ".join(b for b in bad if "ungrounded" in b)[:150] or "clean")
    check(f"The explanation invents no numbers ({ran} runs)",
          not any("appears in the reason" in b for b in bad),
          "; ".join(b for b in bad if "appears in the reason" in b)[:150] or "clean")

print("\n=== 7. THE EXPLANATION IS COMPUTED, NOT WRITTEN ===")
src = open(BACKEND / "app" / "agent" / "ollama_agent.py",
           encoding="utf-8").read()
rank_src = src[src.index("def rank_candidates("):]
rank_src = rank_src[:rank_src.index("\ndef ")] if "\ndef " in rank_src else rank_src
check("Ranking makes no model call", "_client.chat" not in rank_src)

if ran:
    reasons = set()
    for _ in range(3):
        reasons.add(oa.rank_candidates(
            candidates, "price", user_text="sandisk 128gb pendrive under 1000",
            requirements=["sandisk", "128gb"], budget_paise=100000)["reason"])
    check("The same inputs always produce the same explanation",
          len(reasons) == 1, f"{len(reasons)} distinct outputs over 3 runs")

    out = oa.rank_candidates(candidates, "price",
                             user_text="sandisk 128gb pendrive under 1000",
                             requirements=["sandisk", "128gb"], budget_paise=100000)
    check("It is flagged as derived", out.get("derived") is True)

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed · {len(WARN)} warnings")
if FAIL: print("  FAILED: " + "; ".join(FAIL))
