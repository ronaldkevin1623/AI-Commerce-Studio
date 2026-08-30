"""
LISTING SCAN

Read the text a seller wrote and say whether it is trying to talk to the
agent rather than to the shopper.

Every pattern here is lifted from app/redteam/attacks.py — the corpus this
project attacks itself with. That is deliberate: a detector invented
separately from the attacks would be measuring a threat nobody demonstrated.
These are the phrasings that actually appear in published indirect-injection
work, in the shape they take on a product page.

What a hit does and does not mean matters, and the wording of every finding
is chosen to keep that straight. A hit means the seller wrote something
aimed at an automated buyer. It does not mean the purchase is unsafe, and
this scan is not what keeps anyone safe: price, stock, the signed budget,
human approval and settlement are decided in code that never reads this
text at all. The scan exists so a person can see the attempt — the defence
holds whether or not anybody looks.

So findings are warnings, never blocks. Blocking on them would claim the
scan is load-bearing, and would hand any seller a way to have a rival
listing refused by writing "ignore all previous instructions" into it.
"""
import re
import unicodedata

# Phrasings that address an automated reader. Named by what the seller is
# reaching for, because that is what a person needs told — not the regex.
_MARKERS = [
    ("Override instruction",
     "text telling the agent to disregard its own instructions",
     re.compile(r"\b(ignore|disregard|override)\b[^.]{0,40}\b"
                r"(previous|prior|above|earlier|all)\b[^.]{0,20}"
                r"\b(instruction|rule|prompt|direction)", re.IGNORECASE)),

    # `[SYSTEM: ...` opens a bracket it never closes on the same token, so a
    # literal `[system]` match reads right past the commonest form of this.
    ("System impersonation",
     "text dressed up as a system or developer message",
     re.compile(r"(system\s+override|\[\s*system\b|"
                r"developer\s+(message|note)|<\s*/?\s*system\s*>)", re.IGNORECASE)),

    ("Fake approval",
     "a claim that a person has already approved the purchase",
     re.compile(r"(\[?\s*approved\s+by\s+(a\s+)?(human|operator|owner|customer)|"
                r"pre-?approved\s+by|no\s+further\s+approval|"
                r"already\s+authoris?zed\s+(this|the)\s+purchase|auto-?approve)",
                re.IGNORECASE)),

    ("Control bypass",
     "an instruction to skip a safety step",
     re.compile(r"(skip\s+(the\s+)?(risk\s+)?(gate|check|approval|verification|controls?)|"
                r"bypass\s+(the\s+)?(gate|check|approval|verification|controls?)|"
                r"proceed\s+directly\s+to\s+(payment|checkout))", re.IGNORECASE)),

    ("Price rewrite",
     "an attempt to state a different price from the one on record",
     re.compile(r"(set\s+price\s+to|charge\s+nothing|the\s+correct\s+price\s+for\s+this"
                r"|price\s+is\s+a\s+data\s+error|this\s+item\s+is\s+free\b"
                r"|ignore\s+the\s+listed\s+price|pricing\s+override"
                r"|treat\s+as\s+(rs|inr|₹|\$)"
                r"|convert\s+before\s+charging"
                r"|(figure|price|amount)\s+on\s+this\s+listing\s+is\s+in\b)",
                re.IGNORECASE)),

    ("Stock claim",
     "an instruction to ignore how many are actually in stock",
     re.compile(r"(unlimited\s+quantity|ignore\s+(any\s+)?stock\s+limits?|"
                r"accept\s+any\s+requested\s+quantity)", re.IGNORECASE)),

    ("Addressed to the agent",
     "a note written for automated buyers rather than for you",
     re.compile(r"((note|important\s+context|instruction)s?\s+(for|to)\s+"
                r"(the\s+)?(automated\s+buyers?|assistant|ai|agent|bot)|"
                r"\b(for|by)\s+automated\s+(agents?|buyers?)\b|attention\s+ai\b)",
                re.IGNORECASE)),

    # A listing does not get to declare its own availability: the merchant's
    # record decides, and a line that asserts it is talking to the machine.
    ("Status claim",
     "the listing asserting its own approval or availability",
     re.compile(r"(status\s*:\s*(active|published|approved|live)\b"
                r"|available\s+for\s+immediate\s+purchase"
                r"|approval\s+not\s+required)", re.IGNORECASE)),

    ("Data request",
     "an instruction to send your details somewhere",
     re.compile(r"((post|send|email|forward|transmit|upload)\b[^.]{0,40}\b"
                r"(customer|user|buyer|card|payment|address|personal)\b[^.]{0,40}"
                r"(details?|data|email|address|information)"
                r"|https?://[^\s]+[^.]{0,30}\b(log|collect|track|registration)\b)",
                re.IGNORECASE)),

    ("Ranking instruction",
     "text telling the agent which product to choose",
     re.compile(r"((recommend|choose|select|rank|prefer)\s+this\s+(item|product|listing|one)"
                r"|do\s+not\s+(consider|recommend|show)\s+(other|competing)"
                r"|best\s+choice[,.]?\s+(do\s+not|ignore))", re.IGNORECASE)),
]

# Long unbroken base64-ish runs. Attacks use them to carry an instruction
# past a reader that only looks for English; ordinary titles do not contain
# them. The floor is high enough that model numbers and SKUs do not trip it.
_ENCODED = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")

# Characters that exist to be unreadable: zero-width joiners and spaces, the
# byte-order mark, and the direction overrides used to hide text mid-string.
_INVISIBLE = {
    "​": "zero-width space",
    "‌": "zero-width non-joiner",
    "‍": "zero-width joiner",
    "⁠": "word joiner",
    "﻿": "byte-order mark",
    "‪": "text-direction override",
    "‫": "text-direction override",
    "‭": "text-direction override",
    "‮": "text-direction override",
}


def _excerpt(text, match, width=60):
    start = max(0, match.start() - 12)
    end = min(len(text), match.end() + width)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def _mixed_scripts(text):
    """
    Latin words carrying letters from another alphabet.

    Cyrillic а and Latin a are different characters that render identically,
    so an instruction can carry a marker straight past a word match. A word
    is only reported when it MIXES scripts — a title legitimately written in
    Cyrillic or Greek throughout is a language, not an attack.
    """
    hits = []
    for word in re.findall(r"\S+", text):
        letters = [c for c in word if c.isalpha()]
        if len(letters) < 3:
            continue
        scripts = set()
        for char in letters:
            name = unicodedata.name(char, "")
            for script in ("LATIN", "CYRILLIC", "GREEK", "ARMENIAN"):
                if name.startswith(script):
                    scripts.add(script)
                    break
        if len(scripts) > 1:
            hits.append(word)
    return hits


def scan_text(text, where):
    """Every finding in one piece of text, each naming what it is."""
    if not text:
        return []

    findings = []
    for name, plain, pattern in _MARKERS:
        match = pattern.search(text)
        if match:
            findings.append({
                "marker": name, "plain": plain, "where": where,
                "excerpt": _excerpt(text, match),
            })

    match = _ENCODED.search(text)
    if match:
        findings.append({
            "marker": "Encoded text", "where": where,
            "plain": "a block of encoded characters, which can hide an instruction",
            "excerpt": _excerpt(text, match, 20),
        })

    present = [label for char, label in _INVISIBLE.items() if char in text]
    if present:
        findings.append({
            "marker": "Hidden characters", "where": where,
            "plain": "characters that do not show on screen, used to hide text",
            "excerpt": ", ".join(sorted(set(present))),
        })

    mixed = _mixed_scripts(text)
    if mixed:
        findings.append({
            "marker": "Lookalike letters", "where": where,
            "plain": "letters from another alphabet that look identical to English ones",
            "excerpt": ", ".join(mixed[:3]),
        })

    return findings


def scan_item(item):
    """Scan the seller-written text this listing actually carries."""
    findings = []
    findings += scan_text(item.get("name") or "", "the title")
    findings += scan_text(item.get("description") or "", "the description")
    findings += scan_text(item.get("seller_username") or "", "the seller name")
    return findings


def scan_basket(items):
    """
    Scan every item, and say what text was available to scan.

    eBay search results carry a title and often no description, so a clean
    result on a title alone is a weaker statement than a clean result on
    both. Reporting how many descriptions existed keeps that difference
    visible instead of letting "nothing found" imply more than it can.
    """
    results = []
    for item in items:
        results.append({
            "item": item.get("name") or item.get("id"),
            "findings": scan_item(item),
            "has_description": bool(item.get("description")),
        })

    return {
        "items": results,
        "findings": sum(len(r["findings"]) for r in results),
        "descriptions_available": sum(1 for r in results if r["has_description"]),
        "items_scanned": len(results),
    }
