"""
CONVERSATION ROUTING — does the agent understand what was said?

Every message a person types takes one of five routes, and taking the wrong
one is how "512gb" fetched SSDs and "why did you pick that one" fetched
books. This exercises the decision across phrasings nobody wrote a rule for,
because the point of routing on structure rather than vocabulary is that it
generalises past the examples it was built from.

Deterministic and offline: no marketplace call, no model. Runs in
milliseconds, so it can be run on every change.
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


from app.agent.router import classify
from app.agent import refine

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def route(msg, previous="bluetooth headphones under 3000", has=True):
    return classify(msg, has_results=has, previous_query=previous)["route"]


print("=== A. Narrowing what is on screen ===")
for msg in ["under 2000", "below 1500", "less than 1000", "cheaper",
            "something cheaper", "too expensive", "only black ones",
            "just the blue one", "in black", "no used ones",
            "nothing refurbished please", "not the refurbished ones",
            "new only", "brand new please", "show me more", "any more",
            "anything else", "other options", "alternatives"]:
    check(f"{msg!r} narrows", route(msg) == "refine", route(msg))

print("\n=== B. A spec is the same product with one value changed ===")
SPEC = [
    ("I need iphone cosmic orange 17pro 256GB under 125000", "512gb",
     "iphone", "512gb"),
    ("I need iphone cosmic orange 17pro 256GB under 125000", "1tb",
     "iphone", "1tb"),
    ("55 inch smart tv under 40000", "65 inch", "tv", "65inch"),
    ("braided usb-c cable 2 metre", "3m", "cable", "3m"),
    ("water bottle 750ml", "1 litre", "bottle", "1litre"),
    ("gaming laptop 16gb ram", "32gb", "laptop", "32gb"),
]
for previous, msg, subject, spec in SPEC:
    parsed = refine.parse(msg, previous)
    amended = refine.amend(previous, (parsed.get("ops") or {}).get("attributes") or [])
    check(f"{msg!r} keeps the subject", subject in amended.lower(), amended)
    check(f"{msg!r} carries the new spec", spec in amended.lower().replace(" ", ""), amended)

# The old value must go, or the search asks for a product that is both.
old_gone = refine.amend("I need iphone cosmic orange 17pro 256GB under 125000", ["512gb"])
check("the replaced spec is gone", "256gb" not in old_gone.lower(), old_gone)
check("the budget survives the swap", "125000" in old_gone, old_gone)

print("\n=== C. Questions about the results, not searches for them ===")
for msg in ["why did you pick that one", "why that one", "how come you chose it",
            "which is better", "which one is better", "what's the difference",
            "what is the difference between these", "compare the top two",
            "is it waterproof", "does it have bluetooth",
            "does the second one have a headphone jack", "is that one new or used",
            "when will it arrive", "how long does delivery take",
            "who is the seller", "what is the seller rating",
            "how many reviews does it have", "tell me more about the first one",
            "what condition is it in", "is there a discount on that"]:
    check(f"{msg!r} is answered", route(msg) == "question", route(msg))

print("\n=== D. A different product is a new search ===")
for msg in ["show me a laptop instead", "I need running shoes",
            "wireless earbuds under 2000", "actually find me a kettle",
            "look for a coffee maker", "search for a monitor",
            "what is a good laptop under 30000", "buy me a phone case",
            "I want a backpack"]:
    check(f"{msg!r} searches", route(msg) == "search", route(msg))

print("\n=== E. Small talk is answered, not searched ===")
for msg in ["hi", "hello", "hey there", "thanks", "thank you", "cheers",
            "ok", "cool", "bye", "how are you", "who are you",
            "what can you do", "are you a bot"]:
    check(f"{msg!r} is an aside", route(msg) == "aside", route(msg))

print("\n=== F. A general question is asked about, never guessed at ===")
for msg in ["what is the capital of France", "who won the world cup",
            "what is the weather tomorrow", "how do i cook rice",
            "what is a good laptop"]:
    check(f"{msg!r} asks rather than searching", route(msg) == "clarify", route(msg))

print("\n=== G. The same message routes the same with or without results ===")
for msg in ["what is the capital of France", "hello", "find me a kettle",
            "what is a good laptop under 30000"]:
    with_results = route(msg)
    without = route(msg, previous="", has=False)
    check(f"{msg!r} is stable", with_results == without,
          f"{with_results} / {without}")

print("\n=== H. A follow-up does not lose the thread ===")
# The reported bug: a price after a photo or text search must narrow it.
check("'under 30000' after a phone search narrows",
      route("under 30000", previous="mobile phone") == "refine")
check("'under 1500' after headphones narrows",
      route("under 1500", previous="bluetooth headphones under 3000") == "refine")

print("\n" + "=" * 62)
print(f"  {passed} passed · {failed} failed")
