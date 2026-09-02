"""
WHAT TO PUT IN FRONT OF SOMEONE WHO HAS NOT ASKED YET.

The first version of this concatenated three lists — things you bought,
things matching a search, then whatever was left in the shop. That is not a
recommender. It has no notion of which suggestion is better than another,
so the order was really "whichever query ran first", and calling that a
recommendation was generous.

This scores every candidate against what the person has actually done, and
the score decides the order. Same shape as the ranking the agent uses on a
search: signals measured from behaviour, combined deterministically, and
every point of the total attributable to something you can point at.

THE SIGNALS, AND WHY EACH ONE IS DEFENSIBLE

  due          The consumption model says this is due. Far and away the
               strongest signal available — it is derived from this
               person's own repeat purchases, not from anyone's guess about
               what people like them buy. Scaled by how due it is, so
               something overdue outranks something due next week.

  affinity     Word overlap between the candidate and what this person has
               actually bought and searched for, weighted towards recent
               behaviour. Recency matters because an interest from four
               months ago is weaker evidence than one from yesterday.

  price_fit    How close the price sits to the middle of what they normally
               spend. Someone whose orders cluster at Rs800 is not helped by
               a Rs90,000 phone, however relevant the words are.

  condition    They buy new; a used listing is a worse suggestion. Read
               from their own order history rather than assumed.

  buyable      A small bonus for the one venue that can genuinely fulfil.
               Deliberately small: it is a tie-breaker, not a thumb on the
               scale, and it must never be able to outrank relevance. Being
               easy to sell is not a reason to recommend something.

WHAT IT WILL NOT DO

No invented products, prices or reasons. Where there is no history the
score is honestly zero and the caller is told the basis is "no history yet"
rather than being handed a confident-looking list built from nothing.

Sponsorship is not a signal here and never will be. The retail-media strip
is a separate, labelled thing; a promoted product cannot buy its way into
this row.
"""
import re
import time

DAY = 86400.0

# Weights. Relative sizes are the argument: `due` has to be able to beat a
# strong word match on its own, because a thing you are about to run out of
# is more useful than a thing that merely resembles an old search. `buyable`
# is an order of magnitude below everything else on purpose.
W_DUE = 60.0
W_AFFINITY = 30.0
W_PRICE_FIT = 14.0
W_CONDITION = 6.0
W_BUYABLE = 3.0

# Words that carry no preference information and would otherwise make every
# pair of electronics look related.
_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "your", "you",
    "new", "pack", "set", "size", "pcs", "inch", "cm", "mm", "usb", "type",
    "black", "white", "silver", "blue", "red", "green", "grey", "gray",
}
_WORD = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> set:
    return {w for w in _WORD.findall((text or "").lower())
            if len(w) > 2 and w not in _STOP}


def _due_score(candidate: dict, due_items: list, now: float) -> tuple[float, str]:
    """How overdue this is, if the consumption model tracks it at all."""
    name = _terms(candidate.get("name"))
    if not name:
        return 0.0, ""
    best = (0.0, "")
    for item in due_items:
        tracked = _terms(item.get("name"))
        if not tracked:
            continue
        overlap = len(name & tracked) / max(1, len(tracked))
        if overlap < 0.5:
            continue
        cycle = float(item.get("cycle_days") or 0) or 30.0
        due_at = float(item.get("due_at") or 0)
        if not due_at:
            continue
        # 1.0 exactly on the due date, above it when overdue, tailing off
        # before. Anything more than a full cycle away scores nothing —
        # that is not a recommendation, it is a calendar entry.
        days_out = (due_at - now) / DAY
        if days_out > cycle:
            continue
        urgency = max(0.0, min(1.5, 1.0 - (days_out / cycle)))
        confidence = {"high": 1.0, "medium": 0.65, "low": 0.3}.get(
            item.get("confidence"), 0.3)
        score = urgency * confidence
        if score > best[0]:
            when = ("overdue" if days_out < 0
                    else "due today" if days_out < 1
                    else f"due in {int(days_out)} days")
            best = (score, f"You rebuy this about every {cycle:.0f} days — {when}")
    return best


def _affinity_score(candidate: dict, history: list) -> tuple[float, str]:
    """
    Overlap with what this person has bought and searched for.

    `history` is newest-first; the weight decays down the list so a search
    from this morning counts for more than one from a month ago.
    """
    name = _terms(f"{candidate.get('name')} {candidate.get('category') or ''}")
    if not name or not history:
        return 0.0, ""
    total, best_hit, best_share = 0.0, "", 0.0
    for index, entry in enumerate(history):
        terms = _terms(entry.get("text"))
        if not terms:
            continue
        shared = name & terms
        if not shared:
            continue
        share = len(shared) / len(terms)
        weight = entry.get("weight", 1.0) * (0.85 ** index)
        total += share * weight
        if share > best_share:
            best_share, best_hit = share, entry.get("label") or entry.get("text")
    if not total:
        return 0.0, ""
    return min(1.0, total), (f"Close to {best_hit}" if best_hit else "")


def _price_fit(candidate: dict, profile: dict) -> tuple[float, str]:
    """Closeness to the middle of what they normally spend."""
    median = profile.get("median_paise")
    price = candidate.get("price_paise")
    if not median or not price:
        return 0.0, ""
    ratio = price / median
    # Full marks within half to double the usual spend, falling away
    # outside that. A band rather than a point, because nobody spends the
    # same amount twice.
    if 0.5 <= ratio <= 2.0:
        fit = 1.0 - abs(1.0 - min(ratio, 2.0 - 1 / max(ratio, 0.5))) / 2
        return max(0.4, min(1.0, fit)), "In the range you usually spend"
    if ratio < 0.5:
        return 0.25, ""
    return 0.0, ""


def rank(*, candidates: list, profile: dict, due_items: list,
         history: list, now: float = None) -> list:
    """
    Score, explain and order. Returns candidates with `score`, `why` and a
    `signals` breakdown attached, best first.
    """
    now = now or time.time()
    conditions = {str(c).lower() for c in (profile.get("conditions") or [])}
    scored = []

    for candidate in candidates:
        due, due_why = _due_score(candidate, due_items, now)
        affinity, affinity_why = _affinity_score(candidate, history)
        fit, fit_why = _price_fit(candidate, profile)

        condition = 0.0
        this_condition = str(candidate.get("condition") or "").lower()
        if conditions and this_condition:
            condition = 1.0 if any(c in this_condition or this_condition in c
                                   for c in conditions) else 0.0

        buyable = 1.0 if candidate.get("buyable") else 0.0

        signals = {
            "due": round(due * W_DUE, 2),
            "affinity": round(affinity * W_AFFINITY, 2),
            "price_fit": round(fit * W_PRICE_FIT, 2),
            "condition": round(condition * W_CONDITION, 2),
            "buyable": round(buyable * W_BUYABLE, 2),
        }
        total = round(sum(signals.values()), 2)

        # The reason shown is the signal that actually earned the most, so
        # the sentence on the card and the number behind it cannot disagree.
        why = ""
        for label, text in (("due", due_why), ("affinity", affinity_why),
                            ("price_fit", fit_why)):
            if text and signals[label] == max(signals.values()):
                why = text
                break
        if not why:
            why = due_why or affinity_why or fit_why

        scored.append({**candidate, "score": total, "signals": signals,
                       "why": why})

    # Score decides the order. Having a photograph breaks ties only: a card
    # you can see is more useful than one you cannot, but that is a fact
    # about the card, not about the product, so it must never move anything
    # past something that scored higher.
    scored.sort(key=lambda c: (-c["score"], 0 if c.get("image") else 1,
                               c.get("price_paise") or 0))
    return scored
